# guidemd — executable, dimension-aware guides for llm-d

One source of truth per guide. Everything else — the docs pages, the GitHub
reading copy, the CI runs, the job matrix — is derived from it and can never
drift from it.

This repo holds **two working prototypes of that idea**, built on the same
requirements and validated against each other. They differ in one
fundamental choice: *what the authored source is*.

| | [`prototypes/annotated-markdown/`](prototypes/annotated-markdown/) | [`prototypes/jinja-markdown/`](prototypes/jinja-markdown/) |
| --- | --- | --- |
| Source of truth | **one plain-markdown file** with invisible comment directives (`when` / `import` / `step`) | **one Jinja2 template** + `guide.yaml`: `{% if %}` / `{% include %}` / inline `{% step %}` blocks |
| Authored file readable as-is | ✔ — renders on GitHub; zero annotations = valid guide | prose reads fine, but it's a template — readers get generated artifacts |
| Parser to maintain | ~300 lines of bespoke document parsing (fences, comments, provenance) | **none** — Jinja parses everything, incl. the `{% step %}` tag via Jinja's extension API |
| Conditionals / composition | invented directives, this compiler only | standard Jinja — known from Ansible/Helm/Hugo, editor-supported |
| Step identity & provenance | positional; provenance hand-threaded through import expansion | optional `id=`; template `file:line` baked in by Jinja at parse time |
| Exhaustiveness safety | heuristic warnings over adjacent `when` groups | explicit `group=` partition check + `{% else %}` makes gaps hard to write |
| GitHub reading copy | one document, default path expanded, **all** alternatives in collapsed `<details>` | default-configuration document (variants: interactive page / Docusaurus pages) |
| Docusaurus story | chunk JSON → custom component (designed, not built) | **`emit-docusaurus` built**: per-variant static `.mdx` pages (default listed, rest `unlisted`), VariantSwitcher navigates between them |
| Migration from existing guides | incremental — annotate a plain README step by step | conversion — turn a README into a template |
| Dependencies | PyYAML | PyYAML + Jinja2 |

**Shared by both:** the ordered-dimensions + rules + constrained-matrix
model (the genuinely novel part — no existing docs tool has it), the
tag-based dry-run/e2e plan split, cluster-free dry-runs, CI-tested badges
per variant, generated E2E badges from the `ci:` matrix, and full-fidelity
ports of upstream
[`guides/optimized-baseline`](https://github.com/llm-d/llm-d/tree/main/guides/optimized-baseline).

**Validated against each other:** the parity suite in
[`prototypes/jinja-markdown/tests/`](prototypes/jinja-markdown/tests/test_guidegen.py)
asserts both prototypes produce identical supported matrices (96 variants)
and identical per-cell step counts across all three plan flavors.

## Which one?

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

- [`prototypes/annotated-markdown/`](prototypes/annotated-markdown/) — guidemd: one annotated `guide.template.md`, compiler, coverage gate vs upstream, 24 tests
- [`prototypes/jinja-markdown/`](prototypes/jinja-markdown/) — guidegen: `guide.yaml` + `guide.md.j2` with inline `{% step %}` blocks, compiler, Docusaurus emitter, 24 tests incl. cross-prototype parity
- [`demo/slides.html`](demo/slides.html) — presentation deck (annotated-markdown prototype; open in a browser, arrow keys)
