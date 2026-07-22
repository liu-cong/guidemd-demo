#!/usr/bin/env python3
"""guidegen.py — steps-as-code guide compiler: structure is authored as
structure; prose is a projection. THERE IS NO DOCUMENT PARSER TO MAINTAIN.

A guide is three kinds of files, each parsed by a tool we don't own:

  guide.yaml     dimensions, rules, ci matrix, env constants   (PyYAML)
  steps/*.sh     each step is a REAL shell script — shellcheck-able,
                 individually runnable, diffable. A small comment header
                 declares metadata:
                     # tags: dry-run=skip          plan filtering (opaque)
                     # group: select-overlay       exactly-one-per-cell check
  guide.md.j2    the prose narrative — plain Jinja2 over markdown
                 (Python's 20-year-old standard template engine):
                     {% if accelerator == "gpu" %} …          conditionals
                     {% include "prereqs.md.j2" %}            composition
                     {{ model }}                              substitution
                     {{ step("install-router") }}             pull a step in
                     {{ step("crds-check", hide=True) }}      in plans only
                     {{ configure_step() }}                   generated env
                     {{ badges() }}                           from ci: rows

Dimension values reach scripts as ENVIRONMENT VARIABLES (upper-cased
dimension names: ${ACCELERATOR}, ${MODEL_SERVER}, …), exported by one
generated `configure` step together with the guide's `env:` constants.
Steps never contain template syntax — every .sh file is valid shell as
committed.

Execution order and inclusion are decided by the TEMPLATE (document order,
like a human reading the page): plan = render the template for a cell,
record the step() calls, filter by --skip tags. The doc is the sequence;
CI mimics a reader. Structural properties that needed heuristics in the
annotated-markdown prototype are queries here:

  step identity        the filename (stable ids for free)
  provenance           the file path (and Jinja reports template file:line)
  exhaustiveness       `# group:` — every supported cell must select exactly
                       one distinct member; {% else %} branches make gaps
                       structurally hard to write in the first place
  nothing escapes CI   a rendered ```bash fence not produced by step()
                       fails validation (write ```console for display-only)
  no loss / no drift   readonly-guide.md freshness gate, unused-step and
                       undeclared-tag checks

Derived outputs:
  render     one variant's markdown to stdout      render-md   committed
  render-html  interactive picker page (all variants pre-rendered)
  plan       bash / yaml / json for one cell       matrix      CI job matrix
  validate   the PR gate: schema, all-cells render, groups, tags, bash -n,
             fence policing, freshness; --cells prints per-variant counts
"""

import argparse
import itertools
import json
import re
import subprocess
import sys
from pathlib import Path

import jinja2
import yaml

RENDERED_MD = "readonly-guide.md"
RENDERED_HTML = "readonly-guide.html"
CI_ROW_META = ("badge", "workflow")
RE_TAGVAL = re.compile(r"([\w-]+)=(\S+)")
RE_HEADER = re.compile(r"^#\s*(tags|group):\s*(.*)$")


class GuideError(Exception):
    pass


# ================================================================ matrix
# (identical model to the annotated-markdown prototype — this logic is the
# irreducibly custom part of the problem in ANY host syntax)

class Matrix:
    def __init__(self, meta, errors):
        self.dims = meta.get("dimensions") or {}
        self.order = list(self.dims)
        self.values = {d: [str(v) for v in (s.get("values") or [])]
                       for d, s in self.dims.items()}
        self.defaults = {}
        for d, s in self.dims.items():
            if not self.values[d]:
                errors.append(f"dimension {d}: needs a non-empty values list")
                continue
            default = str(s.get("default", self.values[d][0]))
            if default not in self.values[d]:
                errors.append(f"dimension {d}: default {default!r} not in values")
            self.defaults[d] = default

        def aslist(v):
            return [str(x) for x in v] if isinstance(v, list) else [str(v)]

        self.rules = [{"when": {k: aslist(v) for k, v in (r.get("when") or {}).items()},
                       "allow": {k: aslist(v) for k, v in (r.get("allow") or {}).items()}}
                      for r in meta.get("rules") or []]
        idx = {d: i for i, d in enumerate(self.order)}
        for n, rule in enumerate(self.rules, 1):
            for part, name in ((rule["when"], "when"), (rule["allow"], "allow")):
                for k, vals in part.items():
                    if k not in self.dims:
                        errors.append(f"rule {n}: {name} references unknown dimension {k!r}")
                    elif not set(vals) <= set(self.values[k]):
                        errors.append(f"rule {n}: {name} {k} has undeclared values")
            if rule["when"] and rule["allow"]:
                if max(idx.get(k, 0) for k in rule["when"]) >= \
                   min(idx.get(k, 0) for k in rule["allow"]):
                    errors.append(f"rule {n}: `when` dimensions must all come before "
                                  "`allow` dimensions in declaration order")

        self.supported = self._enumerate() if not errors else []
        for d in self.order:
            used = {c[d] for c in self.supported}
            for v in self.values.get(d, []):
                if self.supported and v not in used:
                    errors.append(f"dimension {d}: value {v!r} is not reachable "
                                  "under the rules (dead value)")

        self.ci, self.ci_rows = [], []
        for n, row in enumerate(meta.get("ci") or [], 1):
            row = dict(row or {})
            extras = {k: str(row.pop(k)) for k in CI_ROW_META if k in row}
            cell = {k: str(v) for k, v in row.items()}
            if set(cell) != set(self.dims):
                missing = set(self.dims) - set(cell)
                extra = set(cell) - set(self.dims)
                errors.append(f"ci[{n}]: each row must be a complete flattened "
                              f"assignment of ALL dimensions"
                              + (f" — missing {sorted(missing)}" if missing else "")
                              + (f" — unknown {sorted(extra)}" if extra else ""))
            elif cell not in self.supported:
                errors.append(f"ci[{n}]: {cell} is not a supported combination")
            else:
                self.ci.append(cell)
                self.ci_rows.append({**extras, "cell": cell})

    def _enumerate(self):
        out = []
        for combo in itertools.product(*(self.values[d] for d in self.order)):
            cell = dict(zip(self.order, combo))
            ok = True
            for rule in self.rules:
                if all(cell[k] in v for k, v in rule["when"].items()):
                    if not all(cell[k] in v for k, v in rule["allow"].items()):
                        ok = False
                        break
            if ok:
                out.append(cell)
        return out

    def default_cell(self):
        if dict(self.defaults) in self.supported:
            return dict(self.defaults)
        return dict(self.supported[0]) if self.supported else dict(self.defaults)


# ================================================================ steps

class Step:
    """One steps/*.sh file: metadata header + plain shell body.

    Header = contiguous `# tags: …` / `# group: …` comment lines after the
    optional shebang. The displayed/executed body is the file minus shebang
    and header — everything else, comments included, is the writer's.
    """

    def __init__(self, path):
        self.path = path
        self.id = path.stem
        self.tags, self.group = {}, None
        lines = path.read_text().splitlines()
        if lines and lines[0].startswith("#!"):
            lines = lines[1:]
        while lines:
            m = RE_HEADER.match(lines[0])
            if not m:
                break
            if m.group(1) == "tags":
                self.tags.update(dict(RE_TAGVAL.findall(m.group(2))))
            else:
                self.group = m.group(2).strip()
            lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
        self.body = "\n".join(lines).rstrip("\n")


def env_name(dim):
    return dim.upper()


# ================================================================ guide

class Guide:
    def __init__(self, guide_dir):
        self.dir = Path(guide_dir)
        self.errors, self.warnings = [], []
        meta_path = self.dir / "guide.yaml"
        if not meta_path.is_file():
            sys.exit(f"{guide_dir}: no guide.yaml found")
        self.meta = yaml.safe_load(meta_path.read_text()) or {}
        self.matrix = Matrix(self.meta, self.errors)
        self.env = {str(k): str(v) for k, v in (self.meta.get("env") or {}).items()}
        self.step_tags = {str(t) for t in (self.meta.get("step_tags") or [])}

        # steps: guide-local steps/ override shared ../../common/steps/
        self.common_dir = self.dir.parent.parent / "common"
        self.steps = {}
        for d in (self.common_dir / "steps", self.dir / "steps"):
            if d.is_dir():
                for f in sorted(d.glob("*.sh")):
                    self.steps[f.stem] = Step(f)
        for s in self.steps.values():
            for k in s.tags:
                if k not in self.step_tags:
                    self.errors.append(
                        f"{self.rel(s.path)}: tag key {k!r} not declared in "
                        f"guide.yaml step_tags {sorted(self.step_tags)}")

        self.jinja = jinja2.Environment(
            loader=jinja2.FileSystemLoader([str(self.dir), str(self.common_dir)]),
            undefined=jinja2.StrictUndefined,
            trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)

    def rel(self, path):
        try:
            return str(Path(path).relative_to(self.dir.parent.parent))
        except ValueError:
            return str(path)

    # ------------------------------------------------------------ rendering

    def _configure_body(self, cell):
        lines = ["# Your configuration (from the picker / --set flags):"]
        lines += [f'export {env_name(d)}="{cell[d]}"' for d in self.matrix.order]
        if self.env:
            lines.append("# Guide constants:")
            lines += [f'export {k}="{v}"' for k, v in self.env.items()]
        return "\n".join(lines)

    def _badges_md(self):
        repo = self.meta.get("repo")
        out = []
        for row in self.matrix.ci_rows:
            wf = row.get("workflow")
            if not wf:
                continue
            label = row.get("badge") or " ".join(row["cell"][d] for d in self.matrix.order)
            base = f"https://github.com/{repo}/actions/workflows/{wf}"
            out.append(f"[![{label}]({base}/badge.svg)]({base})")
        return "\n".join(out)

    def render(self, cell):
        """Render the template for one cell.

        Returns (markdown, collected) where collected is the ordered list of
        step records — the plan IS the document order for this cell.
        """
        collected = []

        def step(step_id, hide=False):
            s = self.steps.get(step_id)
            if s is None:
                raise GuideError(f"step({step_id!r}): no such step — known: "
                                 + ", ".join(sorted(self.steps)))
            collected.append({"id": s.id, "src": self.rel(s.path),
                              "tags": s.tags, "group": s.group,
                              "run": s.body, "hidden": bool(hide)})
            return "" if hide else f"```bash\n{s.body}\n```"

        def configure_step():
            body = self._configure_body(cell)
            collected.append({"id": "configure", "src": "<generated:configure>",
                              "tags": {}, "group": None, "run": body,
                              "hidden": False})
            return f"```bash\n{body}\n```"

        ctx = dict(cell)
        ctx.update(title=self.meta.get("title", self.meta.get("name", "")),
                   step=step, configure_step=configure_step,
                   badges=self._badges_md)
        try:
            md = self.jinja.get_template("guide.md.j2").render(**ctx)
        except (jinja2.TemplateError, GuideError) as e:
            tb = getattr(e, "lineno", None)
            name = getattr(e, "name", None) or "guide.md.j2"
            where = f"{name}:{tb}" if tb else name
            raise GuideError(f"{where}: {e}") from e
        md = re.sub(r"\n{3,}", "\n\n", md).strip("\n") + "\n"
        return md, collected

    def parse_assignment(self, sets):
        cell = self.matrix.default_cell()
        for item in sets or []:
            k, _, v = item.partition("=")
            if k not in self.matrix.dims or v not in self.matrix.values[k]:
                sys.exit(f"invalid --set {item!r} (dimensions: "
                         + ", ".join(f"{d}={self.matrix.values[d]}"
                                     for d in self.matrix.order) + ")")
            cell[k] = v
        if cell not in self.matrix.supported:
            sys.exit(f"assignment {cell} is not a supported combination under the rules")
        return cell

    def plan(self, cell, skips=None):
        _, collected = self.render(cell)
        steps = [{"id": s["id"], "src": s["src"], "meta": s["tags"], "run": s["run"]}
                 for s in collected
                 if not any(s["tags"].get(k) == v for k, v in (skips or []))]
        return {"guide": self.meta.get("name"), "doc": str(self.dir / "guide.md.j2"),
                "assignment": dict(cell), "steps": steps}

    # ------------------------------------------------------------ validation

    def validate_cells(self):
        """Render every supported cell; check fences, groups, usage."""
        used = set()
        groups = {}
        for s in self.steps.values():
            if s.group:
                groups.setdefault(s.group, set()).add(s.id)
        for cell in self.matrix.supported:
            try:
                md, collected = self.render(cell)
            except GuideError as e:
                self.errors.append(f"cell {short(cell)}: {e}")
                continue
            used.update(s["id"] for s in collected)
            shown = sum(1 for s in collected if not s["hidden"])
            fences = len(re.findall(r"^```bash\b", md, re.M))
            if fences != shown:
                self.errors.append(
                    f"cell {short(cell)}: {fences} ```bash fences rendered but "
                    f"{shown} produced by step() — a hand-written bash fence "
                    "escapes CI; use ```console for display-only snippets")
            for g, members in groups.items():
                picked = {s["id"] for s in collected} & members
                if len(picked) != 1:
                    self.errors.append(
                        f"cell {short(cell)}: group {g!r} selected "
                        f"{sorted(picked) or 'nothing'} — every supported cell "
                        "must select exactly one member")
        for sid, s in sorted(self.steps.items()):
            if sid not in used:
                self.warnings.append(f"{self.rel(s.path)}: step is never "
                                     "referenced by the template (dead file)")
        for s in self.steps.values():
            r = subprocess.run(["bash", "-n", str(s.path)], capture_output=True)
            if r.returncode != 0:
                self.errors.append(f"{self.rel(s.path)}: bash -n failed: "
                                   + r.stderr.decode().strip())


def short(cell):
    return " ".join(f"{k}={v}" for k, v in cell.items())


# ================================================================ emitters

def render_github(guide):
    cell = guide.matrix.default_cell()
    md, _ = guide.render(cell)
    banner = ("<!-- GENERATED FILE — DO NOT EDIT. Rendered for the DEFAULT "
              f"configuration ({short(cell)}). Other variants: guidegen.py "
              "render --set …, or the interactive page. -->")
    return banner + "\n" + md


def plan_bash(plan):
    lines = ["#!/usr/bin/env bash",
             f"# {plan['guide']} — generated from {plan['doc']}",
             f"# assignment: {plan['assignment']}",
             "set -euo pipefail"]
    for n, s in enumerate(plan["steps"], 1):
        meta = ("  [" + " ".join(f"{k}={v}" for k, v in s["meta"].items()) + "]"
                if s["meta"] else "")
        lines += ["", f"# --- step {n}/{len(plan['steps'])}: {s['id']}{meta}"
                      f"  ({s['src']}) ---", s["run"]]
    return "\n".join(lines) + "\n"


def plan_yaml(plan):
    class LiteralDumper(yaml.SafeDumper):
        pass

    def _str(dumper, value):
        style = "|" if "\n" in value else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)

    LiteralDumper.add_representer(str, _str)
    doc = {"guide": plan["guide"], "assignment": plan["assignment"],
           "steps": [{"id": s["id"], "src": s["src"],
                      **({"meta": s["meta"]} if s["meta"] else {}),
                      "run": s["run"] + "\n"} for s in plan["steps"]]}
    return yaml.dump(doc, Dumper=LiteralDumper, sort_keys=False, width=100)


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITLE@@ — llm-d guide</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<style>
  :root { --accent: #0e7490; --border: #e2e2e8; --muted: #6b6b76; }
  body { font: 16px/1.6 -apple-system, "Segoe UI", sans-serif; margin: 0; color: #1a1a22; }
  header { position: sticky; top: 0; background: #fff; border-bottom: 1px solid var(--border);
           padding: 0.75rem 2rem; display: flex; gap: 1.2rem; align-items: center;
           flex-wrap: wrap; z-index: 10; }
  header h1 { font-size: 1rem; margin: 0 1rem 0 0; }
  .dim label { display: block; font-size: 0.7rem; text-transform: uppercase;
               letter-spacing: 0.05em; color: var(--muted); }
  .dim select { font-size: 0.9rem; padding: 0.25rem 0.5rem; border: 1px solid var(--border);
                border-radius: 6px; background: #fff; }
  #tested { margin-left: auto; font-size: 0.8rem; }
  #tested .yes { color: #15803d; } #tested .no { color: #b45309; }
  main { max-width: 860px; margin: 0 auto; padding: 1rem 2rem 4rem; }
  main pre { background: #16161d; color: #e8e8f0; padding: 1rem; border-radius: 8px;
             overflow-x: auto; font-size: 0.85rem; line-height: 1.5; }
  main code { font-family: ui-monospace, "SF Mono", Menlo, monospace; }
  main :not(pre) > code { background: #ecfeff; padding: 0.1rem 0.35rem; border-radius: 4px;
                          font-size: 0.85em; }
  main blockquote { border-left: 3px solid var(--accent); margin: 1rem 0;
                    padding: 0.25rem 1rem; background: #f8fdfe; color: #3a3a44; }
  main h2 { border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; margin-top: 2.5rem; }
  main table { border-collapse: collapse; }
  main th, main td { border: 1px solid var(--border); padding: 0.35rem 0.7rem; }
</style>
</head>
<body>
<header id="picker"><h1>@@TITLE@@</h1></header>
<main id="content"></main>
<script>
const GUIDE = @@DATA@@;
const ORDER = GUIDE.order, SUPPORTED = GUIDE.supported;
const key = c => ORDER.map(d => c[d]).join('|');
const prefixMatch = (c, picks, upto) => ORDER.slice(0, upto).every(d => c[d] === picks[d]);
const availableAt = (k, picks) => {
  const seen = [];
  for (const c of SUPPORTED)
    if (prefixMatch(c, picks, k) && !seen.includes(c[ORDER[k]])) seen.push(c[ORDER[k]]);
  return seen;
};
const header = document.getElementById('picker'), selects = {};
ORDER.forEach((dim, k) => {
  const spec = GUIDE.dimensions[dim], wrap = document.createElement('div');
  wrap.className = 'dim';
  const label = document.createElement('label');
  label.textContent = spec.label || dim;
  const sel = document.createElement('select');
  for (const v of spec.values) {
    const o = document.createElement('option');
    o.value = String(v); o.textContent = String(v); sel.appendChild(o);
  }
  sel.addEventListener('change', () => cascade(k));
  wrap.append(label, sel); header.appendChild(wrap); selects[dim] = sel;
});
const tested = document.createElement('div');
tested.id = 'tested'; header.appendChild(tested);
function cascade(changed) {
  const picks = {};
  ORDER.forEach((dim, k) => {
    const avail = availableAt(k, picks);
    let v = selects[dim].value;
    if (k > changed || !avail.includes(v))
      v = avail.includes(GUIDE.defaults[dim]) ? GUIDE.defaults[dim] : avail[0];
    picks[dim] = v;
  });
  show(picks);
}
function show(cell, updateUrl = true) {
  ORDER.forEach(d => { selects[d].value = cell[d]; });
  const picks = {};
  ORDER.forEach((dim, k) => {
    const avail = availableAt(k, picks);
    for (const o of selects[dim].options) o.disabled = !avail.includes(o.value);
    picks[dim] = cell[dim];
  });
  document.getElementById('content').innerHTML = marked.parse(GUIDE.docs[key(cell)]);
  const isTested = GUIDE.ci.some(c => ORDER.every(d => c[d] === cell[d]));
  tested.innerHTML = isTested ? '<span class="yes">✓ CI-tested configuration</span>'
                              : '<span class="no">⚠ supported, not CI-tested</span>';
  if (updateUrl) history.replaceState(null, '', '?' + new URLSearchParams(cell));
}
const params = new URLSearchParams(location.search);
const wanted = Object.fromEntries(ORDER.map(d => [d, params.get(d) || GUIDE.defaults[d]]));
const initial = SUPPORTED.find(c => ORDER.every(d => c[d] === wanted[d]))
  || SUPPORTED.find(c => ORDER.every(d => c[d] === GUIDE.defaults[d])) || SUPPORTED[0];
show({ ...initial }, false);
</script>
</body>
</html>
"""


def render_html(guide):
    docs = {}
    for cell in guide.matrix.supported:
        md, _ = guide.render(cell)
        docs["|".join(cell[d] for d in guide.matrix.order)] = md
    data = json.dumps({
        "order": guide.matrix.order,
        "dimensions": {d: {"label": s.get("label", d), "values": guide.matrix.values[d]}
                       for d, s in guide.matrix.dims.items()},
        "defaults": guide.matrix.defaults,
        "supported": guide.matrix.supported,
        "ci": guide.matrix.ci,
        "docs": docs,
    }).replace("</", "<\\/")
    title = guide.meta.get("title", guide.meta.get("name", ""))
    return HTML_PAGE.replace("@@TITLE@@", title).replace("@@DATA@@", data)


# ================================================================ CLI

def load(guide_dir, deep=True):
    g = Guide(guide_dir)
    if deep and not g.errors:
        g.validate_cells()
    for w in g.warnings:
        print(f"WARNING: {guide_dir}: {w}", file=sys.stderr)
    if g.errors:
        for e in g.errors:
            print(f"ERROR: {guide_dir}: {e}", file=sys.stderr)
        sys.exit(1)
    return g


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "render", "render-md", "render-html", "plan", "matrix"):
        p = sub.add_parser(name)
        p.add_argument("guide_dir")
    sub.choices["validate"].add_argument("--cells", action="store_true")
    sub.choices["render-md"].add_argument("--check", action="store_true")
    sub.choices["matrix"].add_argument("--github", action="store_true")
    for name in ("render", "plan"):
        sub.choices[name].add_argument("--set", action="append", metavar="dim=value")
    sub.choices["plan"].add_argument("--format", choices=["bash", "yaml", "json"],
                                     default="yaml")
    sub.choices["plan"].add_argument("--skip", action="append", metavar="key=value")
    args = ap.parse_args()

    if args.cmd == "validate":
        g = load(args.guide_dir)
        out = Path(args.guide_dir) / RENDERED_MD
        if not out.exists() or out.read_text() != render_github(g):
            sys.exit(f"ERROR: {args.guide_dir}: {RENDERED_MD} is missing or stale — "
                     "run guidegen.py render-md")
        n = len(g.plan(g.matrix.default_cell())["steps"])
        print(f"OK: {args.guide_dir} — {len(g.matrix.supported)} supported "
              f"combinations, {len(g.matrix.ci)} ci cells, {len(g.steps)} step "
              f"files, {n} steps in the default plan")
        if args.cells:
            for cell in g.matrix.supported:
                count = len(g.plan(cell)["steps"])
                mark = "  [ci]" if cell in g.matrix.ci else ""
                print(f"  {count:3d} steps  {short(cell)}{mark}")
    elif args.cmd == "render":
        g = load(args.guide_dir, deep=False)
        md, _ = g.render(g.parse_assignment(args.set))
        sys.stdout.write(md)
    elif args.cmd == "render-md":
        g = load(args.guide_dir)
        new = render_github(g)
        out = Path(args.guide_dir) / RENDERED_MD
        if args.check:
            if not out.exists() or out.read_text() != new:
                sys.exit(f"STALE: run guidegen.py render-md {args.guide_dir}")
            print(f"OK: {out} up to date")
        else:
            out.write_text(new)
            print(f"wrote {out}")
    elif args.cmd == "render-html":
        g = load(args.guide_dir)
        out = Path(args.guide_dir) / RENDERED_HTML
        out.write_text(render_html(g))
        print(f"wrote {out} ({len(g.matrix.supported)} variants pre-rendered)")
    elif args.cmd == "plan":
        g = load(args.guide_dir, deep=False)
        skips = []
        for item in args.skip or []:
            k, _, v = item.partition("=")
            if g.step_tags and k not in g.step_tags:
                sys.exit(f"--skip {item!r}: {k!r} is not a declared step tag "
                         f"{sorted(g.step_tags)}")
            skips.append((k, v))
        plan = g.plan(g.parse_assignment(args.set), skips=skips)
        if args.format == "json":
            print(json.dumps(plan, indent=2))
        elif args.format == "yaml":
            sys.stdout.write(plan_yaml(plan))
        else:
            sys.stdout.write(plan_bash(plan))
    elif args.cmd == "matrix":
        g = load(args.guide_dir, deep=False)
        cells = g.matrix.ci or g.matrix.supported
        entries = [{"guide": g.meta.get("name"), **c} for c in cells]
        if args.github:
            print(json.dumps({"include": entries}))
        else:
            for e in entries:
                dims = [f"{k}={v}" for k, v in e.items() if k != "guide"]
                print(f"{e['guide']:22s} {' '.join(dims)}")


if __name__ == "__main__":
    main()
