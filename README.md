# guidemd — executable, dimension-aware guides for llm-d

One source of truth per guide. Everything else — the docs pages, the GitHub
reading copy, the CI runs, the job matrix — is derived from it and can never
drift from it.

This repo holds **three prototypes**: a snapshot of the upstream community
proposal ([`prototypes/pr1988-guide-yaml/`](prototypes/pr1988-guide-yaml/)
— [llm-d/llm-d#1988](https://github.com/llm-d/llm-d/pull/1988), the
yaml-source/rendered-README baseline this work builds on), and two
successors built on the same requirements and validated against each
other. The successors keep everything #1988 got right (derived docs, the
validate/render/check triad, incremental adoption) and add the
dimensions/rules/ci matrix, per-variant projection, and CI plans derived
from the source instead of scraped from the README. They differ in one
fundamental choice: *what the authored source is*.

| | [`prototypes/pr1988-guide-yaml/`](prototypes/pr1988-guide-yaml/) (baseline) | [`prototypes/annotated-markdown/`](prototypes/annotated-markdown/) | [`prototypes/jinja-markdown/`](prototypes/jinja-markdown/) |
| --- | --- | --- | --- |
| Source of truth | `guide.yaml` (bash steps as YAML data) + a shared README template | **one plain-markdown file** with invisible comment directives (`when` / `import` / `step`) | **one Jinja2 template** + `guide.yaml`: `{% if %}` / `{% include %}` / inline `{% step %}` blocks |
| Authored file readable as-is | ✖ — YAML isn't a doc; readers get the rendered README | ✔ — renders on GitHub; zero annotations = valid guide | prose reads fine, but it's a template — readers get generated artifacts |
| Parser to maintain | ~800 lines across the validate/render/check script triad (custom YAML schema + README checker) | ~300 lines of bespoke document parsing (fences, comments, provenance) | **none** — Jinja parses everything, incl. the `{% step %}` tag via Jinja's extension API |
| Conditionals / composition | `when:` on bash steps only — prose can't vary; no shared fragments | invented directives, this compiler only | standard Jinja — known from Ansible/Helm/Hugo, editor-supported |
| Step identity & provenance | named sections + step position in the YAML | positional; provenance hand-threaded through import expansion | optional `id=`; template `file:line` baked in by Jinja at parse time |
| Exhaustiveness safety | none — no dimensions/rules matrix; invalid combos aren't modeled | heuristic warnings over adjacent `when` groups | explicit `group=` partition check + `{% else %}` makes gaps hard to write |
| GitHub reading copy | **one union README** — every variant's commands with *"comment out / uncomment"* guidance | one document, default path expanded, **all** alternatives in collapsed `<details>` | default document + **configuration table**; CI-tested rows link to pre-rendered `variants/*.md` (website serves all 96) |
| Docusaurus story | none — README synced as today | chunk JSON → custom component (designed, not built) | **`emit-docusaurus` built**: per-variant static `.mdx` pages (default listed, rest `unlisted`), VariantSwitcher navigates between them |
| Migration from existing guides | move each README's bash into `guide.yaml` | incremental — annotate a plain README step by step | conversion — turn a README into a template |
| Dependencies | PyYAML | PyYAML | PyYAML + Jinja2 |

**Shared by both:** the ordered-dimensions + rules + constrained-matrix
model (the genuinely novel part — no existing docs tool has it), the
tag-based dry-run/e2e plan split, cluster-free dry-runs, and full-fidelity
ports of upstream
[`guides/optimized-baseline`](https://github.com/llm-d/llm-d/tree/main/guides/optimized-baseline).
(CI-tested badges and generated E2E badge blocks live in the
annotated-markdown prototype; jinja-markdown was deliberately trimmed to
the bare minimum — those come back later if it wins.)

**Validated against each other:** the parity suite in
[`prototypes/jinja-markdown/tests/`](prototypes/jinja-markdown/tests/test_guidegen.py)
asserts both prototypes produce identical supported matrices (96 variants)
and identical per-cell step counts across all three plan flavors.

## Which one?

- **pr1988-guide-yaml** is the upstream baseline, kept verbatim for
  comparison — both successors preserve its derived-docs direction and CI
  gate while fixing its union-not-projection rendering, invariant prose,
  and missing supported-combinations model.
- **annotated-markdown** optimizes for the *writer's* plain-markdown,
  single-readable-file experience and incremental adoption; it pays with a
  bespoke document parser and positional steps.
- **jinja-markdown** optimizes for *owning no parser* and for structural
  guarantees (provenance, ids, group exhaustiveness, strict variables) on
  a language writers may already know; it pays by making the authored
  source a template rather than a document.

A middle path also exists (keep the annotated syntax, replace the regex
guts with `markdown-it-py` tokens — retiring the bespoke parser without
changing the authoring format); it is discussed but not prototyped.

## Quick start

```bash
# annotated-markdown
cd prototypes/annotated-markdown
./guidemd.py validate guides/optimized-baseline/guide.template.md
python3 -m unittest discover -s tests -q

# jinja-markdown
cd prototypes/jinja-markdown
./guidegen.py validate guides/optimized-baseline
./guidegen.py emit-docusaurus guides/optimized-baseline
python3 -m unittest discover -s tests -q
```

## Layout

- [`prototypes/pr1988-guide-yaml/`](prototypes/pr1988-guide-yaml/) — verbatim snapshot of upstream [PR #1988](https://github.com/llm-d/llm-d/pull/1988): `guide.yaml` → rendered README, with the validate/render/check script triad
- [`prototypes/annotated-markdown/`](prototypes/annotated-markdown/) — guidemd: one annotated `guide.template.md`, compiler, coverage gate vs upstream, 24 tests
- [`prototypes/jinja-markdown/`](prototypes/jinja-markdown/) — guidegen: `guide.yaml` + `guide.md.j2` with inline `{% step %}` blocks, compiler package, Docusaurus emitter, 26 tests incl. cross-prototype parity
- [`demo/slides.html`](demo/slides.html) — presentation deck (annotated-markdown prototype; open in a browser, arrow keys)
