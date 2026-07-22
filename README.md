# guidemd — executable, dimension-aware guides for llm-d

One source of truth per guide. Everything else — the interactive docs page,
the GitHub reading copy, the CI runs, the job matrix — is derived from it
and can never drift from it.

This repo holds **two working prototypes of that idea**, built on the same
requirements and validated against each other. They differ in one
fundamental choice: *where the source of truth lives*.

| | [`prototypes/annotated-markdown/`](prototypes/annotated-markdown/) | [`prototypes/steps-as-code/`](prototypes/steps-as-code/) |
| --- | --- | --- |
| Source of truth | **one markdown file** with invisible comment directives (`when` / `import` / `step`) | **structure as structure**: `guide.yaml` (data) + `steps/*.sh` (real scripts) + `guide.md.j2` (Jinja2 prose) |
| Authored file is readable as-is | ✔ — plain markdown, renders on GitHub, zero annotations = valid guide | ✖ — the template has holes; readers get generated artifacts |
| Parser to maintain | ~300 lines of bespoke document parsing (fences, comments, provenance) | **none** — PyYAML, Jinja2, and bash are someone else's parsers |
| Step identity | positional (documented trade-off: no resume, no stable CI history) | filenames — stable ids for free |
| Exhaustiveness safety | heuristic warnings over adjacent `when` groups | explicit `# group:` check + Jinja `{% else %}` makes gaps hard to write |
| Executable steps | bash fences marked in prose; extracted by the compiler | already `.sh` files — shellcheck-able, individually runnable |
| GitHub reading copy | one document, default path expanded, **all** alternatives in collapsed `<details>` | default-configuration document (other variants: interactive page / `render --set`) |
| Migration from existing guides | incremental — annotate a plain README step by step | conversion — explode a guide into data + scripts + template |
| Dependencies | PyYAML | PyYAML + Jinja2 |

**Shared by both:** the ordered-dimensions + rules + constrained-matrix
model (the genuinely novel part — no existing docs tool has it), the
tag-based dry-run/e2e plan split, cluster-free dry-runs, the interactive
picker with CI-tested badges, generated E2E badges from the `ci:` matrix,
and full-fidelity ports of upstream
[`guides/optimized-baseline`](https://github.com/llm-d/llm-d/tree/main/guides/optimized-baseline).

**Validated against each other:** the parity suite in
[`prototypes/steps-as-code/tests/`](prototypes/steps-as-code/tests/test_guidegen.py)
asserts both prototypes produce identical supported matrices (96 variants)
and identical per-cell step counts across all three plan flavors.

## Which one?

- **annotated-markdown** optimizes for the *writer's* single-file,
  prose-first experience and incremental adoption; it pays with a bespoke
  document parser and positional steps.
- **steps-as-code** optimizes for *owning no parser* and for structural
  guarantees (stable step ids, shellcheck, group exhaustiveness); it pays
  by making the authored source a template rather than a document.

A middle path also exists (keep the annotated syntax, replace the regex
guts with `markdown-it-py` tokens — retiring the bespoke parser without
changing the authoring format); it is discussed but not prototyped.

## Quick start

```bash
# annotated-markdown
cd prototypes/annotated-markdown
./guidemd.py validate guides/optimized-baseline/guide.template.md
python3 -m unittest discover -s tests -q

# steps-as-code
cd prototypes/steps-as-code
./guidegen.py validate guides/optimized-baseline
python3 -m unittest discover -s tests -q
```

## Layout

- [`prototypes/annotated-markdown/`](prototypes/annotated-markdown/) — guidemd: one annotated `guide.template.md`, compiler, coverage gate vs upstream, 24 tests
- [`prototypes/steps-as-code/`](prototypes/steps-as-code/) — guidegen: `guide.yaml` + `steps/*.sh` + `guide.md.j2`, compiler, 21 tests incl. cross-prototype parity
- [`demo/slides.html`](demo/slides.html) — presentation deck (annotated-markdown prototype; open in a browser, arrow keys)
