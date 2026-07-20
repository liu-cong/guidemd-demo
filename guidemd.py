#!/usr/bin/env python3
"""guidemd.py — llm-d guide compiler: one authored source, derived everything.

THE SINGLE SOURCE RULE: a guide is exactly ONE authored markdown file
(guide.template.md). Core syntax is just TWO statements — `when` and `import`:

  <!-- when k=v -->     conditional region (prose and/or code); nestable;
  …                     multi-value: k=v1|v2; multi-key: k=v j=w (ALL hold)
  <!-- end -->

  <!-- import PATH [key=value …] -->
                        single line; pulls a shared fragment (path relative
                        to the doc) with {{ key }} params substituted.
                        Fragment headings are DYNAMICALLY RE-BASED: the
                        fragment's top heading lands one level below the
                        nearest heading above the import point, so the same
                        fragment nests correctly under an H2 in one guide
                        and an H3 in another. Fragments may import fragments.

Executable steps are ```bash fences marked with a `<!-- step -->` line —
that marker is HOW CI finds the scripts. Steps run top-to-bottom like a human
would and are identified by position, nothing more. A bash fence without a
step marker is a validation error (nothing escapes CI silently); use a
non-bash fence (```console, ```yaml, …) for display-only snippets. Optional
`key=value` pairs on the marker are metadata, fully OPAQUE to this tool and
carried into the plan verbatim — CI may interpret keys it knows and must
ignore the rest. One presentation attribute is tool-read: `hide=true`
excludes a step from BOTH reader artifacts (readonly-guide.md and the page)
while keeping it in every plan — used for hidden dry-run equivalents of
steps that cannot be dry-run.

The dry-run convention (pure metadata + the generic `plan --skip` filter):

  (no tag)                 shown to readers; runs in dry-run AND e2e
  ci=skip                  shown; a human step CI handles out-of-band
  dry-run=skip             shown; e2e-only (real install, wait, benchmark)
  e2e=skip hide=true       hidden; dry-run equivalent (helm template, …)

  dry-run plan:  plan --set … --skip ci=skip --skip dry-run=skip
  e2e plan:      plan --set … --skip ci=skip --skip e2e=skip

PLAIN MARKDOWN IS STILL A VALID GUIDE: a file with no front matter and no
markers validates and renders (zero dimensions = one variant; nothing is
executable until the first `<!-- step -->` appears). Unmarked bash fences
are only an error once the guide has at least one step marker — so guides
migrate incrementally and experimental guides start as plain markdown.

Dimensions are ORDERED — users pick them top to bottom, and the options for
dimension N+1 are determined by picks 1..N. Instead of enumerating every
supported combination, `rules:` constrain later dimensions given earlier ones:

  dimensions:            # declaration order = pick order; first value = default
    infra_provider: { values: [base, gke] }
    accelerator:    { values: [gpu, amd, tpu/v6] }
  rules:                 # `when` keys must all come BEFORE `allow` keys
    - when:  { infra_provider: gke }
      allow: { accelerator: [gpu, tpu/v6] }
  ci:                    # tested cells (CI matrix); every row is a complete,
    - { infra_provider: base, accelerator: gpu }      # flattened assignment
    - { infra_provider: gke,  accelerator: tpu/v6 }   # of ALL dimensions

Derived outputs (the guide content itself is opaque to all of them):

  render-md     readonly-guide.md — the COMMITTED GitHub reading artifact:
                all imports expanded in place, default path shown, non-default
                `when` regions wrapped in collapsible <details> blocks.
                Generated, never hand-edited; `validate` fails when stale.
  render-html   ONE interactive page: cascading pickers in dimension order,
                URL deep-links — for the docs site build
  plan          executable run for one picked assignment — bash script,
                or structured yaml/json (steps in document order)
  matrix        the CI job matrix (from `ci:`, else all supported combos)
  validate      structural checks + readonly-guide.md freshness (the PR gate)
  render        debug: project one variant to stdout (never committed)

`md-only` regions (<!-- md-only -->…<!-- end -->) appear in readonly-guide.md
but are dropped from the interactive page. `{{ dimension }}` substitutes the
picked value inline (also used for import parameters, resolved at import
expansion).
"""

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

import yaml

RENDERED_MD = "readonly-guide.md"
RENDERED_HTML = "readonly-guide.html"

RE_WHEN = re.compile(r"^\s*<!--\s*when\s+(.+?)\s*-->\s*$")
RE_MDONLY = re.compile(r"^\s*<!--\s*md-only\s*-->\s*$")
RE_END = re.compile(r"^\s*<!--\s*end\s*-->\s*$")
RE_STEP = re.compile(r"^\s*<!--\s*step\b(.*?)\s*-->\s*$")
RE_FENCE = re.compile(r"^\s*```(\S*)\s*$")
RE_SUBST = re.compile(r"\{\{\s*(\w+)\s*\}\}")
RE_ATTR = re.compile(r'([\w-]+)=("[^"]*"|[^\s]+)')
RE_IMPORT = re.compile(r"^\s*<!--\s*import\s+(\S+)((?:\s+[\w-]+=(?:\"[^\"]*\"|\S+))*)\s*-->\s*$")
RE_HEADING = re.compile(r"^(#{1,6})\s")

MD_ONLY = "__md_only__"


def parse_attrs(expr):
    return {k: v.strip('"') for k, v in RE_ATTR.findall(expr)}


def parse_conds(expr):
    return {k: v.split("|") for k, v in parse_attrs(expr).items()}


def matches(conds, cell):
    return all(cell.get(k) in v for k, v in conds.items() if k != MD_ONLY)


def subst(text, mapping):
    return RE_SUBST.sub(lambda m: str(mapping.get(m.group(1), m.group(0))), text)


# ================================================================ front matter

def split_front_matter(text, path):
    """Front matter is optional: a plain markdown file is a valid guide."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1))
    if not isinstance(meta, dict) or "guide" not in meta:
        sys.exit(f"{path}: front matter must contain a top-level `guide:` key")
    return meta["guide"], text[m.end():]


class Matrix:
    """Ordered dimensions + rules -> the enumerated supported set."""

    def __init__(self, meta, errors):
        self.dims = meta.get("dimensions") or {}
        self.order = list(self.dims)  # zero dimensions = plain guide, one variant
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
            when, allow = rule["when"], rule["allow"]
            for part, name in ((when, "when"), (allow, "allow")):
                for k, vals in part.items():
                    if k not in self.dims:
                        errors.append(f"rule {n}: {name} references unknown dimension {k!r}")
                    elif not set(vals) <= set(self.values[k]):
                        errors.append(f"rule {n}: {name} {k} has undeclared values")
            if when and allow:
                if max(idx.get(k, 0) for k in when) >= min(idx.get(k, 0) for k in allow):
                    errors.append(f"rule {n}: `when` dimensions must all come before "
                                  "`allow` dimensions in declaration order")

        self.supported = self._enumerate() if not errors else []
        for d in self.order:
            used = {c[d] for c in self.supported}
            for v in self.values.get(d, []):
                if self.supported and v not in used:
                    errors.append(f"dimension {d}: value {v!r} is not reachable under "
                                  "the rules (dead value)")

        self.ci = []
        for n, row in enumerate(meta.get("ci") or [], 1):
            cell = {k: str(v) for k, v in (row or {}).items()}
            if set(cell) != set(self.dims):
                missing = set(self.dims) - set(cell)
                extra = set(cell) - set(self.dims)
                errors.append(f"ci[{n}]: each row must be a complete flattened assignment "
                              f"of ALL dimensions"
                              + (f" — missing {sorted(missing)}" if missing else "")
                              + (f" — unknown {sorted(extra)}" if extra else ""))
            elif cell not in self.supported:
                errors.append(f"ci[{n}]: {cell} is not a supported combination")
            else:
                self.ci.append(cell)

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


# ================================================================ imports

def rebase_headings(text, parent_level):
    """Shift the fragment's headings so its top level sits under the parent.

    The fragment's minimum heading level becomes parent_level + 1; deeper
    headings shift by the same delta (internal hierarchy preserved, clamped
    at h6). Lines inside code fences are never touched. No headings → no-op.
    """
    lines = text.splitlines()
    in_fence = False
    levels = []
    for line in lines:
        if RE_FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and RE_HEADING.match(line):
            levels.append(len(RE_HEADING.match(line).group(1)))
    if not levels:
        return text
    delta = parent_level + 1 - min(levels)
    if delta == 0:
        return text
    out, in_fence = [], False
    for line in lines:
        if RE_FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        m = RE_HEADING.match(line) if not in_fence else None
        if m:
            n = min(6, max(1, len(m.group(1)) + delta))
            out.append("#" * n + line[len(m.group(1)):])
        else:
            out.append(line)
    return "\n".join(out)


def expand_fragment(doc_path, imp_path, attr_str, seen=()):
    """Fragment text, fully expanded (fragments may import fragments)."""
    frag_file = (Path(doc_path).parent / imp_path).resolve()
    if not frag_file.is_file():
        sys.exit(f"{doc_path}: import {imp_path}: file not found")
    if frag_file in seen:
        sys.exit(f"{imp_path}: import cycle detected via {doc_path}")
    text = frag_file.read_text()
    if text.startswith("---\n"):
        sys.exit(f"{imp_path}: fragments must not have front matter")
    expanded = expand_imports(frag_file, text.splitlines(),
                              seen=(*seen, frag_file), parent=None)
    return subst("\n".join(expanded).strip("\n"), parse_attrs(attr_str))


def expand_imports(doc_path, lines, seen=(), parent=1):
    """Replace every single-line import directive with its fragment content.

    Fragment headings are re-based against the nearest heading above the
    import point (`parent=None`: unknown until a heading is seen — imports
    before any heading are inlined as authored).
    """
    out, in_fence = [], False
    for line in lines:
        if RE_FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and RE_HEADING.match(line):
            parent = len(RE_HEADING.match(line).group(1))
        m = RE_IMPORT.match(line) if not in_fence else None
        if not m:
            out.append(line)
            continue
        frag = expand_fragment(doc_path, m.group(1), m.group(2), seen=seen)
        if parent is not None:
            frag = rebase_headings(frag, parent)
        out.extend(frag.splitlines())
    return out


# ================================================================ rendered-guide.md

def wrap_alternatives(lines, matrix):
    """Wrap when-regions not visible at the default cell in <details>."""
    default = matrix.default_cell()
    out, stack = [], []
    in_fence = False
    for line in lines:
        if RE_FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence:
            m = RE_WHEN.match(line)
            if m:
                conds = parse_conds(m.group(1))
                alt = not matches(conds, default)
                stack.append(alt)
                out.append(line)
                if alt:
                    label = ", ".join(
                        f"{matrix.dims.get(k, {}).get('label', k)}: {'|'.join(v)}"
                        for k, v in conds.items())
                    out.append(f"<details><summary><em>Alternative — {label}</em></summary>")
                    out.append("")
                continue
            if RE_MDONLY.match(line):
                stack.append(False)
                out.append(line)
                continue
            if RE_END.match(line):
                if stack and stack.pop():
                    if out and out[-1].strip():
                        out.append("")
                    out.append("</details>")
                out.append(line)
                continue
        out.append(line)
    return out


def strip_hidden(lines):
    """Drop hide=true step markers and their bash fences from reader output."""
    out, i = [], 0
    while i < len(lines):
        m = RE_STEP.match(lines[i])
        if m and parse_attrs(m.group(1)).get("hide") == "true":
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and RE_FENCE.match(lines[i]):
                i += 1
                while i < len(lines) and not RE_FENCE.match(lines[i]):
                    i += 1
                i += 1  # closing fence
            continue
        out.append(lines[i])
        i += 1
    return out


def render_github(path):
    """The committed GitHub artifact: imports expanded, alternatives folded."""
    text = Path(path).read_text()
    meta, body = split_front_matter(text, path)
    errors = []
    matrix = Matrix(meta, errors)
    if errors:
        for e in errors:
            print(f"ERROR: {path}: {e}", file=sys.stderr)
        sys.exit(1)
    lines = expand_imports(path, body.splitlines())
    lines = strip_hidden(lines)
    lines = wrap_alternatives(lines, matrix)
    banner = (f"<!-- GENERATED FILE — DO NOT EDIT."
              f" Source: {Path(path).name}; regenerate with:"
              f" guidemd.py render-md {Path(path).name} -->")
    return banner + "\n" + re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n") + "\n"


def rendered_path(doc):
    return Path(doc).parent / RENDERED_MD


# ================================================================ guide parsing

class Guide:
    """Parsed guide: matrix + chunks (imports expanded in memory).

    A chunk is {'md': str, 'conds': {dim: [values]}, 'step': None | {...}}.
    Contiguous prose under identical conditions merges into one chunk; every
    marked bash fence is its own step chunk. Document order is execution
    order.
    """

    def __init__(self, path):
        self.path = Path(path)
        text = self.path.read_text()
        self.meta, body = split_front_matter(text, path)
        self.meta.setdefault("name", self.path.stem)
        self.errors = []
        self.matrix = Matrix(self.meta, self.errors)
        self.chunks = []
        self._parse(expand_imports(self.path, body.splitlines()))
        bad_refs = {r for c in self.chunks for r in RE_SUBST.findall(c["md"])
                    if r not in self.matrix.dims}
        for r in sorted(bad_refs):
            self.errors.append(
                f"'{{{{ {r} }}}}' is not a dimension — unresolved import parameter?")

    def _flatten(self, stack):
        merged = {}
        for conds in stack:
            for k, v in conds.items():
                merged[k] = [x for x in v if x in merged.get(k, v)]
        return merged

    def _emit_md(self, line, conds):
        last = self.chunks[-1] if self.chunks else None
        if last and last["step"] is None and last["conds"] == conds:
            last["md"] += "\n" + line
        else:
            self.chunks.append({"md": line, "conds": conds, "step": None})

    def _parse(self, lines):
        dims = self.matrix.dims
        self._unmarked = []
        stack, pending = [], None
        in_fence = fence_is_step = False
        fence_body = []

        for lineno, line in enumerate(lines, 1):
            fence = RE_FENCE.match(line)
            if in_fence:
                if fence and not fence.group(1):
                    in_fence = False
                    if fence_is_step:
                        attrs = pending or {}
                        self.chunks.append({
                            "md": "```bash\n" + "\n".join(fence_body) + "\n```",
                            "conds": self._flatten(stack),
                            "step": {"hidden": attrs.get("hide") == "true",
                                     "meta": {k: v for k, v in attrs.items()
                                              if k != "hide"}},
                        })
                        pending = None
                    else:
                        self._emit_md(line, self._flatten(stack))
                elif fence_is_step:
                    fence_body.append(line)
                else:
                    self._emit_md(line, self._flatten(stack))
                continue

            m = RE_WHEN.match(line)
            if m:
                conds = parse_conds(m.group(1))
                for k, vals in conds.items():
                    if k not in dims:
                        self.errors.append(f"line {lineno}: unknown dimension {k!r}")
                    elif not set(vals) <= set(self.matrix.values[k]):
                        self.errors.append(f"line {lineno}: undeclared value in {k}={vals}")
                stack.append(conds)
                continue
            if RE_MDONLY.match(line):
                stack.append({MD_ONLY: ["md"]})
                continue
            if RE_END.match(line):
                if not stack:
                    self.errors.append(f"line {lineno}: <!-- end --> without an open block")
                else:
                    stack.pop()
                continue
            m = RE_STEP.match(line)
            if m:
                pending = parse_attrs(m.group(1))
                continue
            if fence:
                in_fence = True
                fence_is_step = fence.group(1) == "bash" and pending is not None
                fence_body = []
                if fence.group(1) == "bash" and pending is None:
                    self._unmarked.append(lineno)
                if not fence_is_step:
                    if pending:
                        self.errors.append(
                            f"line {lineno}: <!-- step --> must precede a ```bash fence")
                        pending = None
                    self._emit_md(line, self._flatten(stack))
                continue
            if pending and line.strip():
                self.errors.append(f"line {lineno}: <!-- step --> must precede a ```bash fence")
                pending = None
            self._emit_md(line, self._flatten(stack))

        if stack:
            self.errors.append("unclosed <!-- when --> / <!-- md-only --> block at end of file")
        if any(c["step"] for c in self.chunks):
            for lineno in self._unmarked:
                self.errors.append(
                    f"line {lineno}: bash fence without a <!-- step --> marker "
                    "(unreachable by CI; use a non-bash fence for display-only snippets)")
        # zero step markers = plain / not-yet-annotated guide: bash fences allowed

    # ------------------------------------------------------------ outputs

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

    def render_markdown(self, cell):
        out = []
        for c in self.chunks:
            if not matches(c["conds"], cell):
                continue
            if c["step"] and c["step"]["hidden"]:
                continue
            out.append(subst(c["md"], cell))
        return re.sub(r"\n{3,}", "\n\n", "\n".join(out) + "\n")

    def plan(self, cell, skips=None):
        steps = []
        for c in self.chunks:
            s = c["step"]
            if not s or not matches(c["conds"], cell):
                continue
            if any(s["meta"].get(k) == v for k, v in (skips or [])):
                continue
            run = re.sub(r"^```bash\n|\n```$", "", subst(c["md"], cell))
            steps.append({"run": run, "meta": s["meta"]})
        return {"guide": self.meta["name"], "doc": str(self.path),
                "assignment": dict(cell), "steps": steps}


def plan_bash(plan):
    lines = ["#!/usr/bin/env bash",
             f"# {plan['guide']} — generated from {plan['doc']}",
             f"# assignment: {plan['assignment']}",
             "set -euo pipefail"]
    for n, s in enumerate(plan["steps"], 1):
        meta = ("  [" + " ".join(f"{k}={v}" for k, v in s["meta"].items()) + "]"
                if s["meta"] else "")
        lines += ["", f"# --- step {n}/{len(plan['steps'])}{meta} ---", s["run"]]
    return "\n".join(lines) + "\n"


def plan_yaml(plan):
    class LiteralDumper(yaml.SafeDumper):
        pass

    def _str(dumper, value):
        style = "|" if "\n" in value else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)

    LiteralDumper.add_representer(str, _str)
    doc = {"guide": plan["guide"], "assignment": plan["assignment"],
           "steps": [{**({"meta": s["meta"]} if s["meta"] else {}),
                      "run": s["run"] + "\n"} for s in plan["steps"]]}
    return yaml.dump(doc, Dumper=LiteralDumper, sort_keys=False, width=100)


# ================================================================ HTML

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITLE@@ — llm-d guide</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<style>
  :root { --accent: #7c3aed; --border: #e2e2e8; --muted: #6b6b76; }
  body { font: 16px/1.6 -apple-system, "Segoe UI", sans-serif; margin: 0; color: #1a1a22; }
  header { position: sticky; top: 0; background: #fff; border-bottom: 1px solid var(--border);
           padding: 0.75rem 2rem; display: flex; gap: 1.2rem; align-items: center;
           flex-wrap: wrap; z-index: 10; }
  header h1 { font-size: 1rem; margin: 0 1rem 0 0; }
  .dim label { display: block; font-size: 0.7rem; text-transform: uppercase;
               letter-spacing: 0.05em; color: var(--muted); }
  .dim select { font-size: 0.9rem; padding: 0.25rem 0.5rem; border: 1px solid var(--border);
                border-radius: 6px; background: #fff; }
  #cell-badge { margin-left: auto; font-size: 0.8rem; color: var(--muted); }
  #cell-badge code { background: #f4f2fb; color: var(--accent); padding: 0.15rem 0.5rem;
                     border-radius: 6px; }
  main { max-width: 860px; margin: 0 auto; padding: 1rem 2rem 4rem; }
  main pre { background: #16161d; color: #e8e8f0; padding: 1rem; border-radius: 8px;
             overflow-x: auto; font-size: 0.85rem; line-height: 1.5; }
  main code { font-family: ui-monospace, "SF Mono", Menlo, monospace; }
  main :not(pre) > code { background: #f4f2fb; padding: 0.1rem 0.35rem; border-radius: 4px;
                          font-size: 0.85em; }
  main blockquote { border-left: 3px solid var(--accent); margin: 1rem 0;
                    padding: 0.25rem 1rem; background: #faf9fd; color: #3a3a44; }
  main h2 { border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; margin-top: 2.5rem; }
  main table { border-collapse: collapse; }
  main th, main td { border: 1px solid var(--border); padding: 0.35rem 0.7rem; }
  .step { border-left: 3px solid var(--accent); padding-left: 1rem; margin: 1rem 0; }
  .step-head { font-size: 0.72rem; color: var(--muted); display: flex; gap: 0.6rem;
               align-items: baseline; }
</style>
</head>
<body>
<header id="picker"><h1>@@TITLE@@</h1></header>
<main id="content"></main>
<script>
const GUIDE = @@DATA@@;

const ORDER = GUIDE.order;                       // pick dimensions in this order
const SUPPORTED = GUIDE.supported;               // enumerated valid combinations
const substitute = (t, cell) => t.replace(/\\{\\{\\s*(\\w+)\\s*\\}\\}/g,
  (m, k) => cell[k] !== undefined ? cell[k] : m);
const visible = (conds, cell) =>
  Object.entries(conds).every(([k, vals]) => vals.includes(cell[k]));
const prefixMatch = (c, picks, upto) =>
  ORDER.slice(0, upto).every(d => c[d] === picks[d]);
const availableAt = (k, picks) => {              // options for dim k given picks 0..k-1
  const seen = [];
  for (const c of SUPPORTED)
    if (prefixMatch(c, picks, k) && !seen.includes(c[ORDER[k]])) seen.push(c[ORDER[k]]);
  return seen;
};

// ---- cascading picker (dimension order enforced) ----
const header = document.getElementById('picker');
const selects = {};
ORDER.forEach((dim, k) => {
  const spec = GUIDE.dimensions[dim];
  const wrap = document.createElement('div');
  wrap.className = 'dim';
  const label = document.createElement('label');
  label.textContent = spec.label || dim;
  const sel = document.createElement('select');
  for (const v of spec.values) {
    const opt = document.createElement('option');
    opt.value = String(v); opt.textContent = String(v);
    sel.appendChild(opt);
  }
  sel.addEventListener('change', () => cascade(k));
  wrap.append(label, sel);
  header.appendChild(wrap);
  selects[dim] = sel;
});
const badge = document.createElement('div');
badge.id = 'cell-badge';
header.appendChild(badge);

function cascade(changed) {
  // keep picks up to `changed`, then re-derive every later dimension
  const picks = {};
  ORDER.forEach((dim, k) => {
    const avail = availableAt(k, picks);
    let v = selects[dim].value;
    if (k > changed || !avail.includes(v))
      v = avail.includes(GUIDE.defaults[dim]) && k > changed ? GUIDE.defaults[dim]
        : avail.includes(v) ? v : (avail.includes(GUIDE.defaults[dim]) ? GUIDE.defaults[dim] : avail[0]);
    picks[dim] = v;
  });
  show(picks);
}

function refreshOptions(cell) {
  const picks = {};
  ORDER.forEach((dim, k) => {
    const avail = availableAt(k, picks);
    for (const opt of selects[dim].options) opt.disabled = !avail.includes(opt.value);
    picks[dim] = cell[dim];
  });
}

// ---- content shells (built once; re-filled per selection) ----
const main = document.getElementById('content');
const shells = GUIDE.chunks.map(chunk => {
  const host = document.createElement('div');
  if (chunk.step) host.className = 'step';
  main.appendChild(host);
  const metaTxt = chunk.step ? Object.entries(chunk.step.meta || {})
    .map(([k, v]) => k + '=' + v).join(' ') : '';
  if (metaTxt) {
    const head = document.createElement('div');
    head.className = 'step-head';
    head.textContent = metaTxt;
    host.appendChild(head);
  }
  const body = document.createElement('div');
  host.appendChild(body);
  return { host, body };
});

function show(cell, updateUrl = true) {
  ORDER.forEach(d => { selects[d].value = cell[d]; });
  refreshOptions(cell);
  GUIDE.chunks.forEach((chunk, i) => {
    const on = visible(chunk.conds, cell);
    shells[i].host.style.display = on ? '' : 'none';
    if (!on) return;
    const md = substitute(chunk.md, cell);
    if (window.marked) shells[i].body.innerHTML = marked.parse(md);
    else { shells[i].body.textContent = md; shells[i].body.style.whiteSpace = 'pre-wrap'; }
  });
  badge.innerHTML = 'variant: <code>' +
    ORDER.map(d => cell[d].replace('/', '')).join('-') + '</code>';
  if (updateUrl) history.replaceState(null, '', '?' + new URLSearchParams(cell));
}

const params = new URLSearchParams(location.search);
const wanted = Object.fromEntries(ORDER.map(d =>
  [d, params.get(d) || GUIDE.defaults[d]]));
const initial = SUPPORTED.find(c => ORDER.every(d => c[d] === wanted[d]))
  || SUPPORTED.find(c => ORDER.every(d => c[d] === GUIDE.defaults[d]))
  || SUPPORTED[0];
show({ ...initial }, false);
</script>
</body>
</html>
"""


def render_html(guide):
    data = json.dumps({
        "title": guide.meta.get("title", guide.meta["name"]),
        "order": guide.matrix.order,
        "dimensions": {d: {"label": s.get("label", d), "values": guide.matrix.values[d]}
                       for d, s in guide.matrix.dims.items()},
        "defaults": guide.matrix.defaults,
        "supported": guide.matrix.supported,
        "chunks": [{"md": c["md"], "conds": c["conds"], "step": c["step"]}
                   for c in guide.chunks
                   if MD_ONLY not in c["conds"]
                   and not (c["step"] and c["step"]["hidden"])],
    }).replace("</", "<\\/")
    return (HTML_PAGE
            .replace("@@TITLE@@", guide.meta.get("title", guide.meta["name"]))
            .replace("@@DATA@@", data))


# ================================================================ CLI

def load(path):
    g = Guide(path)
    if g.errors:
        for e in g.errors:
            print(f"ERROR: {path}: {e}", file=sys.stderr)
        sys.exit(1)
    return g


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "matrix", "render-md"):
        p = sub.add_parser(name)
        p.add_argument("docs", nargs="+")
    sub.choices["matrix"].add_argument("--github", action="store_true")
    sub.choices["render-md"].add_argument("--check", action="store_true",
                                          help="exit non-zero if readonly-guide.md is stale")
    for name in ("render", "plan", "render-html"):
        p = sub.add_parser(name)
        p.add_argument("docs", nargs=1)
    sub.choices["render-html"].add_argument(
        "-o", "--out", help="output HTML file (default: <doc dir>/readonly-guide.html)")
    for name in ("render", "plan"):
        sub.choices[name].add_argument("--set", action="append", metavar="dim=value")
    sub.choices["plan"].add_argument("--format", choices=["bash", "yaml", "json"],
                                     default="yaml")
    sub.choices["plan"].add_argument("--skip", action="append", metavar="key=value",
                                     help="drop steps whose metadata matches (e.g. ci=skip)")
    args = ap.parse_args()

    if args.cmd == "render-md":
        stale = []
        for doc in args.docs:
            load(doc)  # structural gate before rendering
            new = render_github(doc)
            out = rendered_path(doc)
            if not out.exists() or out.read_text() != new:
                stale.append(str(out))
                if not args.check:
                    out.write_text(new)
                    print(f"wrote {out}")
            elif not args.check:
                print(f"up to date {out}")
        if args.check and stale:
            sys.exit("STALE (run guidemd.py render-md): " + ", ".join(stale))
        if args.check:
            print(f"OK: readonly-guide.md up to date for {len(args.docs)} doc(s)")
    elif args.cmd == "validate":
        failed = False
        for doc in args.docs:
            g = load(doc)
            out = rendered_path(doc)
            if not out.exists() or out.read_text() != render_github(doc):
                print(f"ERROR: {doc}: {RENDERED_MD} is missing or stale — "
                      "run guidemd.py render-md", file=sys.stderr)
                failed = True
                continue
            n = sum(1 for c in g.chunks if c["step"])
            print(f"OK: {doc} — {len(g.matrix.supported)} supported combinations, "
                  f"{len(g.matrix.ci)} ci cells, {n} steps")
        if failed:
            sys.exit(1)
    elif args.cmd == "matrix":
        entries = []
        for doc in args.docs:
            g = load(doc)
            cells = g.matrix.ci or g.matrix.supported
            if not g.matrix.ci:
                print(f"note: {doc} has no `ci:` list — matrix is ALL "
                      f"{len(cells)} supported combinations", file=sys.stderr)
            for cell in cells:
                entries.append({"doc": doc, "guide": g.meta["name"], **cell})
        if args.github:
            print(json.dumps({"include": entries}))
        else:
            for e in entries:
                dims = [f"{k}={v}" for k, v in e.items() if k not in ("doc", "guide")]
                print(f"{e['guide']:22s} {' '.join(dims)}")
    elif args.cmd == "render-html":
        g = load(args.docs[0])
        out = Path(args.out) if args.out else Path(args.docs[0]).parent / RENDERED_HTML
        out.write_text(render_html(g))
        print(f"wrote {out} ({len(g.matrix.supported)} supported combinations)")
    elif args.cmd == "render":
        g = load(args.docs[0])
        sys.stdout.write(g.render_markdown(g.parse_assignment(args.set)))
    elif args.cmd == "plan":
        g = load(args.docs[0])
        skips = []
        for item in args.skip or []:
            k, _, v = item.partition("=")
            skips.append((k, v))
        plan = g.plan(g.parse_assignment(args.set), skips=skips)
        if args.format == "json":
            print(json.dumps(plan, indent=2))
        elif args.format == "yaml":
            sys.stdout.write(plan_yaml(plan))
        else:
            sys.stdout.write(plan_bash(plan))


if __name__ == "__main__":
    main()
