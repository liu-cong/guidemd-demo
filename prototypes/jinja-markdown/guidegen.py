#!/usr/bin/env python3
"""guidegen.py — jinja-markdown guide compiler: prose and steps live in ONE
Jinja2 template; structure lives in data. THERE IS NO DOCUMENT PARSER TO
MAINTAIN — Jinja parses the template (including our `{% step %}` tag, which
is ~30 lines registered through Jinja's documented extension API), PyYAML
parses the config.

A guide is two authored files (plus shared partials):

  guide.yaml     dimensions, rules, ci matrix, env constants     (PyYAML)
  guide.md.j2    the guide — markdown prose with Jinja2 logic and
                 INLINE executable steps:

    {% if accelerator == "gpu" %} … {% endif %}       conditionals
    {% include "prereqs.md.j2" %}                     composition
    {{ model }}                                       substitution

    {% step %}                                        an executable step —
    kubectl apply -n ${NAMESPACE} -k ${KUSTOMIZE_DIR} renders as a ```bash
    {% endstep %}                                     fence, recorded for
                                                      the plan
    {% step tags="dry-run=skip" %} … {% endstep %}    plan filtering (keys
                                                      declared in step_tags)
    {% step tags="e2e=skip", hide=true %} … {% endstep %}
                                                      in every plan, hidden
                                                      from readers
    {% step group="select-overlay" %} … {% endstep %} exactly-one-per-cell
                                                      validation
    {% step id="install-router" %} … {% endstep %}    optional stable id
                                                      (default: file:line)

    {{ configure_step() }}    generated step exporting the picked dimension
                              values (${ACCELERATOR}, …) + `env:` constants
    {{ badges() }}            E2E badge block derived from ci: rows

Steps consume dimension values as ENVIRONMENT VARIABLES exported by the
configure step, so step bodies stay copy-pasteable shell; `{{ }}`
substitution inside bodies also works when wanted (bodies are template
content). Execution order is document order: plan = render the template
for a cell, keep the recorded steps, filter by --skip tags. CI still
mimics a reader.

Every step knows its template file:line (captured by Jinja at parse time
— provenance without any custom tracking). Validation renders every
supported cell and checks: undeclared tag keys, group partitions, bash -n
on every step body, hand-written ```bash fences (must come from
{% step %}; use ```console for display-only), typo'd variables
(StrictUndefined), duplicate explicit ids, and readonly-guide.md freshness.

Derived outputs:
  render        one variant's markdown        render-md     committed copy
  render-html   interactive picker page (all variants pre-rendered)
  emit-docusaurus   per-variant .mdx pages for the llm-d.ai site: default
                variant listed + canonical, others `unlisted: true`;
                GitHub alerts converted to Docusaurus admonitions; a
                reference _VariantSwitcher.jsx component and _variants.json
                are emitted alongside
  plan          bash / yaml / json for one cell    matrix    CI job matrix
  validate      the PR gate (--cells: per-variant step counts)
"""

import argparse
import itertools
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import jinja2
import yaml
from jinja2 import nodes
from jinja2.ext import Extension

RENDERED_MD = "readonly-guide.md"
RENDERED_HTML = "readonly-guide.html"
CI_ROW_META = ("badge", "workflow")
RE_TAGVAL = re.compile(r"([\w-]+)=(\S+)")


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


# ================================================================ {% step %}

class StepExtension(Extension):
    """`{% step key=value, … %} body {% endstep %}` — an inline executable
    step. Jinja's own parser handles the tag; at parse time we bake in the
    template file:line, so every recorded step carries provenance for free.
    """

    tags = {"step"}

    def parse(self, parser):
        lineno = parser.stream.current.lineno
        next(parser.stream)
        src = f"{parser.name or 'guide.md.j2'}:{lineno}"
        kwargs = [nodes.Keyword("src", nodes.Const(src))]
        while parser.stream.current.type != "block_end":
            parser.stream.skip_if("comma")
            name = parser.stream.expect("name").value
            parser.stream.expect("assign")
            kwargs.append(nodes.Keyword(name, parser.parse_expression()))
        body = parser.parse_statements(("name:endstep",), drop_needle=True)
        call = self.call_method("_step", [nodes.ContextReference()], kwargs)
        return nodes.CallBlock(call, [], [], body).set_lineno(lineno)

    def _step(self, context, src, id=None, tags="", group=None, hide=False,
              caller=None):
        run = caller().strip("\n")
        steps = context.get("_steps")
        if steps is not None:
            steps.append({"id": id or src, "src": src,
                          "tags": dict(RE_TAGVAL.findall(tags)),
                          "group": group, "run": run, "hidden": bool(hide)})
        return "" if hide else f"```bash\n{run}\n```"


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
        self.common_dir = self.dir.parent.parent / "common"
        self.jinja = jinja2.Environment(
            loader=jinja2.FileSystemLoader([str(self.dir), str(self.common_dir)]),
            undefined=jinja2.StrictUndefined,
            extensions=[StepExtension],
            trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)

    # ------------------------------------------------------------ rendering

    def _configure_body(self, cell):
        lines = ["# Your configuration (from the picker / --set flags):"]
        lines += [f'export {d.upper()}="{cell[d]}"' for d in self.matrix.order]
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

        Returns (markdown, collected): collected is the ordered list of step
        records — the plan IS the document order for this cell.
        """
        collected = []

        def configure_step():
            body = self._configure_body(cell)
            collected.append({"id": "configure", "src": "<generated:configure>",
                              "tags": {}, "group": None, "run": body,
                              "hidden": False})
            return f"```bash\n{body}\n```"

        ctx = dict(cell)
        ctx.update(title=self.meta.get("title", self.meta.get("name", "")),
                   configure_step=configure_step, badges=self._badges_md,
                   _steps=collected)
        try:
            md = self.jinja.get_template("guide.md.j2").render(**ctx)
        except jinja2.TemplateError as e:
            lineno = getattr(e, "lineno", None)
            name = getattr(e, "name", None) or "guide.md.j2"
            where = f"{name}:{lineno}" if lineno else name
            raise jinja2.TemplateError(f"{where}: {e}") from e
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
        """Render every supported cell; check tags, fences, groups, ids, bash."""
        bodies = set()
        group_members = {}
        per_cell_selection = []
        for cell in self.matrix.supported:
            try:
                md, collected = self.render(cell)
            except jinja2.TemplateError as e:
                self.errors.append(f"cell {short(cell)}: {e}")
                continue
            sel = {}
            for s in collected:
                bodies.add(s["run"])
                for k in s["tags"]:
                    if k not in self.step_tags:
                        self.errors.append(
                            f"{s['src']}: tag key {k!r} not declared in "
                            f"guide.yaml step_tags {sorted(self.step_tags)}")
                if s["group"]:
                    sel.setdefault(s["group"], set()).add(s["src"])
                    group_members.setdefault(s["group"], set()).add(s["src"])
            per_cell_selection.append((cell, sel))
            explicit = {}
            for s in collected:
                if s["id"] != s["src"] and s["id"] != "configure":
                    explicit.setdefault(s["id"], set()).add(s["src"])
            for sid, srcs in explicit.items():
                if len(srcs) > 1:
                    self.errors.append(f"cell {short(cell)}: step id {sid!r} "
                                       f"used at {sorted(srcs)}")
            shown = sum(1 for s in collected if not s["hidden"])
            fences = len(re.findall(r"^```bash\b", md, re.M))
            if fences != shown:
                self.errors.append(
                    f"cell {short(cell)}: {fences} ```bash fences rendered but "
                    f"{shown} produced by {{% step %}} — a hand-written bash "
                    "fence escapes CI; use ```console for display-only snippets")
        for g in sorted(group_members):
            for cell, sel in per_cell_selection:
                picked = sel.get(g, set())
                if len(picked) != 1:
                    self.errors.append(
                        f"cell {short(cell)}: group {g!r} selected "
                        f"{sorted(picked) or 'nothing'} — every supported cell "
                        "must select exactly one member")
        # dedupe errors produced per-cell for the same step location
        self.errors = list(dict.fromkeys(self.errors))
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
            for body in sorted(bodies):
                f.seek(0)
                f.truncate()
                f.write(body + "\n")
                f.flush()
                r = subprocess.run(["bash", "-n", f.name], capture_output=True)
                if r.returncode != 0:
                    self.errors.append("step body fails bash -n: "
                                       + r.stderr.decode().strip()
                                       + f"\n  body: {body[:80]}…")


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
        lines += ["", f"# --- step {n}/{len(plan['steps'])}: {s['id']}{meta} ---",
                  s["run"]]
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


# ---------------------------------------------------------------- docusaurus

ALERT_MAP = {"NOTE": "note", "TIP": "tip", "IMPORTANT": "info",
             "WARNING": "warning", "CAUTION": "danger"}
RE_ALERT = re.compile(r"^> \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$")


def alerts_to_admonitions(md):
    """GitHub `> [!NOTE]` blockquotes -> Docusaurus `:::note` admonitions."""
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        m = RE_ALERT.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        out.append(f":::{ALERT_MAP[m.group(1)]}")
        i += 1
        while i < len(lines) and lines[i].startswith(">"):
            out.append(lines[i][2:] if lines[i].startswith("> ") else lines[i][1:])
            i += 1
        out.append(":::")
    return "\n".join(out) + "\n"


def variant_slug(cell, order):
    return "-".join(cell[d].replace("/", "").replace(".", "") for d in order)


def emit_docusaurus(guide, out_dir):
    """Per-variant .mdx pages: the default variant is the listed, canonical
    page; every other supported variant is `unlisted: true` (reachable via
    the switcher / deep links, hidden from sidebar, search and sitemap).
    All content is fully static — SEO, docs search and no-JS readers get
    real pages, and the switcher only navigates between them.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    order = guide.matrix.order
    default = guide.matrix.default_cell()
    name = guide.meta.get("name", "guide")
    title = guide.meta.get("title", name)
    slugs = {}
    for cell in guide.matrix.supported:
        md, _ = guide.render(cell)
        body = alerts_to_admonitions(md)
        body = re.sub(r"^# .*\n", "", body, count=1)  # title comes from front matter
        is_default = cell == default
        slug = "index" if is_default else variant_slug(cell, order)
        slugs["|".join(cell[d] for d in order)] = slug
        fm = ["---", f"title: {title}"]
        if not is_default:
            fm += ["unlisted: true"]
        fm += ["---", "",
               "import VariantSwitcher from './_VariantSwitcher';", "",
               f"<VariantSwitcher current={{{json.dumps(dict(cell))}}} />", ""]
        (out / f"{slug}.mdx").write_text("\n".join(fm) + "\n" + body)
    data = {"order": order,
            "dimensions": {d: {"label": s.get("label", d),
                               "values": guide.matrix.values[d]}
                           for d, s in guide.matrix.dims.items()},
            "defaults": guide.matrix.defaults,
            "supported": guide.matrix.supported,
            "ci": guide.matrix.ci, "slugs": slugs}
    (out / "_variants.json").write_text(json.dumps(data, indent=1))
    (out / "_VariantSwitcher.jsx").write_text(VARIANT_SWITCHER)
    return len(guide.matrix.supported)


VARIANT_SWITCHER = """\
// Reference implementation — pairs with the .mdx pages emitted by
// `guidegen.py emit-docusaurus`. Cascading pickers in dimension order;
// picking a variant NAVIGATES to that variant's own static page, so every
// variant is a real Docusaurus doc (theme, search, versioning included).
import React from 'react';
import {useHistory} from '@docusaurus/router';
import useBaseUrl from '@docusaurus/useBaseUrl';
import data from './_variants.json';

const key = (cell) => data.order.map((d) => cell[d]).join('|');
const availableAt = (k, picks) => {
  const seen = [];
  for (const c of data.supported) {
    if (data.order.slice(0, k).every((d) => c[d] === picks[d]) &&
        !seen.includes(c[data.order[k]])) seen.push(c[data.order[k]]);
  }
  return seen;
};

export default function VariantSwitcher({current}) {
  const history = useHistory();
  const base = useBaseUrl('.');
  const go = (cell) => {
    const slug = data.slugs[key(cell)];
    history.push(slug === 'index' ? base : `${base}/${slug}`);
  };
  const onChange = (dim, value) => {
    const changed = data.order.indexOf(dim);
    const picks = {};
    data.order.forEach((d, k) => {
      const avail = availableAt(k, picks);
      let v = k === changed ? value : current[d];
      if (k > changed || !avail.includes(v))
        v = avail.includes(data.defaults[d]) ? data.defaults[d] : avail[0];
      picks[d] = v;
    });
    go(picks);
  };
  const tested = data.ci.some((c) => data.order.every((d) => c[d] === current[d]));
  const picks = {};
  return (
    <div style={{display: 'flex', gap: '1rem', flexWrap: 'wrap',
                 alignItems: 'flex-end', margin: '1rem 0'}}>
      {data.order.map((dim, k) => {
        const avail = availableAt(k, picks);
        picks[dim] = current[dim];
        return (
          <label key={dim} style={{fontSize: '0.75rem'}}>
            {data.dimensions[dim].label || dim}
            <br />
            <select value={current[dim]} onChange={(e) => onChange(dim, e.target.value)}>
              {data.dimensions[dim].values.map((v) => (
                <option key={v} value={v} disabled={!avail.includes(v)}>{v}</option>
              ))}
            </select>
          </label>
        );
      })}
      <span style={{fontSize: '0.8rem'}}>
        {tested ? '✓ CI-tested configuration' : '⚠ supported, not CI-tested'}
      </span>
    </div>
  );
}
"""


# ---------------------------------------------------------------- HTML page

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
    for name in ("validate", "render", "render-md", "render-html", "plan",
                 "matrix", "emit-docusaurus"):
        p = sub.add_parser(name)
        p.add_argument("guide_dir")
    sub.choices["validate"].add_argument("--cells", action="store_true")
    sub.choices["render-md"].add_argument("--check", action="store_true")
    sub.choices["matrix"].add_argument("--github", action="store_true")
    sub.choices["emit-docusaurus"].add_argument(
        "-o", "--out", help="output dir (default: <guide>/docusaurus)")
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
              f"combinations, {len(g.matrix.ci)} ci cells, {n} steps in the "
              "default plan")
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
    elif args.cmd == "emit-docusaurus":
        g = load(args.guide_dir)
        out = args.out or str(Path(args.guide_dir) / "docusaurus")
        n = emit_docusaurus(g, out)
        print(f"wrote {out}: {n} variant .mdx pages "
              "(+ _variants.json, _VariantSwitcher.jsx)")
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
