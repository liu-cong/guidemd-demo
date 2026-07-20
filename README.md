# guidemd — executable, dimension-aware guides

One authored markdown file per guide. Everything else — the interactive docs
page, the GitHub reading copy, the CI runs — is derived from it and can never
drift from it.

```
guide.template.md ──┬── render-md ───▶ readonly-guide.md    committed GitHub copy
(authored source)   ├── render-html ─▶ readonly-guide.html  interactive picker page
                    ├── plan ────────▶ yaml / bash          executable CI run
                    ├── matrix ──────▶ ci cells             the CI job matrix
                    └── validate ────▶ pass / fail          PR gate
```

## Design principles

1. **One authored source.** A guide is exactly one `guide.template.md`. No
   forks per dimension value, no parallel docs to keep in sync.
2. **Everything else is generated.** Readers and CI consume derived
   artifacts; `validate` blocks any PR where they'd drift from the source.
3. **Explicitly executable.** A `<!-- step -->` marker on a bash block is how
   CI finds scripts. A bash block *without* one fails validation — no command
   can be published untested by accident.
4. **The content is opaque to CI.** CI mimics a human: run the steps top to
   bottom. It interprets no semantics; optional step metadata (`ci=skip`,
   `name=…`) passes through verbatim for runners that want it.
5. **Constraints, not enumeration.** Dimensions are declared in pick order;
   short `rules` narrow later choices from earlier ones. 4 rules turn 336 raw
   combinations into 56 valid ones; a small flattened `ci:` list is the
   tested matrix.
6. **Compose, don't copy.** Shared sections (prereqs, install router,
   verification, benchmark, cleanup) are `import`ed fragments with
   parameters; fragments import fragments, and headings re-base to their
   host section depth automatically.

## Three personas

| Persona | What they touch | What they get |
| --- | --- | --- |
| **Guide writer** | plain markdown + two statements (`when`, `import`); guide-specific env choices; fragments owned per dimension/team | a thin guide (~6 import lines + prose); shared sections maintained once for all guides |
| **Guide reader** | [`readonly-guide.html`](guides/optimized-baseline/readonly-guide.html) on llm-d.ai · [`readonly-guide.md`](guides/optimized-baseline/readonly-guide.md) on GitHub | pickers in dimension order (invalid combos unselectable, deep-linkable URLs) · default path expanded, alternatives in collapsible sections |
| **CI** | `plan --set dim=value … --format yaml\|bash` per matrix cell | an executable, verifiable run derived fresh from the guide — exactly what a human would have typed |

## The entire syntax

```markdown
<!-- when accelerator=gpu model=Qwen/Qwen3-32B -->   conditional region (prose/code);
…                                                    ALL pairs hold; k=v1|v2; nestable
<!-- end -->

<!-- import ../common/verify.md key=value -->        pull a shared fragment (one line)

<!-- step -->                                        the next ```bash fence is a step
<!-- step ci=skip anything=else -->                  …optional opaque metadata

<!-- md-only --> … <!-- end -->                      GitHub copy only, not the web page
{{ accelerator }}                                    the picked value, inline
```

That's all of it. No section schema, no phases, no step ids — steps run in
document order, like a human reading the page.

## Dimensions, rules, tested matrix

```yaml
dimensions:                      # declaration order = pick order; first value = default
  infra_provider: { values: [base, gke] }
  router_mode:    { values: [standalone, gateway] }
  accelerator:    { values: [gpu, amd, xpu, hpu, tpu/v6, tpu/v7, cpu] }
  model_server:   { values: [vllm, sglang, trtllm] }
  model:          { values: [Qwen/Qwen3-32B, openai/gpt-oss-120b] }
  monitoring:     { values: ["off", "on"] }
rules:                           # `when` (earlier dims) narrows `allow` (later dims)
  - when:  { infra_provider: gke }
    allow: { accelerator: [gpu, tpu/v6, tpu/v7] }
ci:                              # tested cells — complete flattened rows, each a CI job
  - { infra_provider: gke, router_mode: standalone, accelerator: tpu/v6, … }
```

The interactive page enforces the order (pick infra first, the accelerator
menu narrows); `plan` rejects unsupported combinations; `validate` flags
values no rule combination can reach.

## Try it

```bash
./guidemd.py validate    guides/optimized-baseline/guide.template.md   # the PR gate
./guidemd.py render-md   guides/optimized-baseline/guide.template.md  # GitHub copy
./guidemd.py render-html guides/optimized-baseline/guide.template.md  # picker page
open guides/optimized-baseline/readonly-guide.html

# CI: the run for one picked configuration
./guidemd.py plan guides/optimized-baseline/guide.template.md \
  --set infra_provider=gke --set accelerator=tpu/v6 --skip ci=skip --format bash | bash -n

# the tested matrix, GitHub Actions form
./guidemd.py matrix --github guides/optimized-baseline/guide.template.md
```

## Layout

- [`guidemd.py`](guidemd.py) — the compiler (Python, stdlib + PyYAML)
- [`guides/optimized-baseline/guide.template.md`](guides/optimized-baseline/guide.template.md) — authored source: a **full-fidelity port of upstream [`guides/optimized-baseline`](https://github.com/llm-d/llm-d/tree/main/guides/optimized-baseline)** (coverage-checked, no loss of information)
- `guides/optimized-baseline/readonly-guide.{md,html}` — generated reading artifacts
- [`guides/common/`](guides/common/) — shared fragments: `prereqs` (parameterized, the whole section), `install-router`, `install-modelserver` (driven by `KUSTOMIZE_DIR`), `get-router-ip`, `verify`, `benchmark`, `cleanup`

- [`demo/slides.html`](demo/slides.html) — presentation deck (open in a browser, arrow keys)
- [`samples/`](samples/) — derived CI artifacts for one look: bash run, yaml run, Actions matrix

Note: markdown was chosen over Jupyter (JSON diffs are hostile to review) and
runme (no conditionals/composition; our step markers could export to it
mechanically if local runner UX is wanted).
