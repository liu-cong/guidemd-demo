# pr1988-guide-yaml — the upstream proposal (snapshot)

A **verbatim snapshot** of the llm-d community proposal
[llm-d/llm-d#1988](https://github.com/llm-d/llm-d/pull/1988), included here
as the baseline the other two prototypes build on. The files are unmodified
(credit and discussion belong to the PR); only this README is ours.

## The model

`guide.yaml` is the machine-readable source of truth; the human `README.md`
is rendered from it through a shared template. A three-script triad keeps
them honest:

```
guides/optimized-baseline/guide.yaml     sections (env / prerequisites /
                                         deploy / verify / benchmark /
                                         cleanup), each a list of steps
                                         with bash `run:` blocks
guides/templates/README.template.md      the rendering skeleton
scripts/guide-check-yaml.py              schema gate
scripts/guide-render.py                  yaml + template -> README.md
scripts/guide-check-readme.py            drift gate (--check in CI)
```

Try it:

```bash
python3 scripts/guide-check-yaml.py guides/optimized-baseline/guide.yaml
python3 scripts/guide-render.py --yaml guides/optimized-baseline/guide.yaml \
  --readme guides/optimized-baseline/README.md --check
python3 scripts/guide-check-readme.py --yaml guides/optimized-baseline/guide.yaml \
  --readme guides/optimized-baseline/README.md
```

## What it gets right (both other prototypes keep all of this)

1. A machine-readable source of truth with the README **derived** from it —
   the correct direction for killing doc/CI drift.
2. The `validate → render → check` triad with `--check` as a CI gate.
3. Incremental adoption (unmarked content untouched).
4. `skip_in: [ci]` separating human-only steps (clone, secrets) from the
   executable path — the ancestor of our `ci=skip` tag.
5. A sane section schema.

## Where it stops short (what the other prototypes change)

1. **The renderer emits the union, not a projection.** `when:` steps become
   *"comment out the above and uncomment the below"* blocks in the rendered
   README — the reader still executes the branching mentally.
2. **Prose can't vary.** Only bash comes from YAML; dimension-specific
   context piles up as always-visible NOTE callouts for every reader.
3. **Dimensions are conflated with runtime env vars** (`ACCELERATOR_TYPE`
   is both a doc-branching axis and an `export`), and nothing declares
   which combinations are actually supported — there is no matrix, no
   rules, no per-variant rendering, and no interactive picker.
4. **CI still scrapes markdown** in places (`llm-d-cicd:skip` wrappers in
   the README), giving two parse paths for one source.

Items 1–3 are exactly what the `dimensions:`/`rules:`/`ci:` matrix model in
[`annotated-markdown`](../annotated-markdown/) and
[`jinja-markdown`](../jinja-markdown/) exists to fix; item 4 is why both
derive CI plans from the source directly and never read the README.
