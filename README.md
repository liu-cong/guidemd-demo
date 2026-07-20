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
2. **Plain markdown is still a guide.** A file with no front matter and no
   markers validates and renders — nothing is executable until the first
   `<!-- step -->` appears. Migration is incremental; a new experimental
   guide starts as plain markdown and earns annotations as it stabilizes.
3. **Everything else is generated.** Readers and CI consume derived
   artifacts; `validate` blocks any PR where they'd drift from the source.
4. **Explicitly executable.** A `<!-- step -->` marker on a bash block is how
   CI finds scripts. A bash block *without* one fails validation (once the
   guide has any steps) — no command is published untested by accident.
5. **CI is just a special user.** It reads the same guide and runs the steps
   top to bottom, exactly like a human — it interprets no semantics.
   Different CI flavors (dry-run, e2e) are just different users skipping
   different opaque tags, the way a human skips the HF-token step they've
   already done.
6. **Dimensions serve the writer AND the reader.** For writers, adding
   dimension-specific docs used to mean weaving branches through everyone
   else's prose; now a dimension owner writes their `when` blocks and
   fragments in isolation. For readers, the same declaration produces a
   contextual guide — only their configuration, no distraction.
7. **Constraints, not enumeration.** Dimensions are declared in pick order;
   short `rules` narrow later choices from earlier ones. 4 rules turn 336 raw
   combinations into 56 valid ones; a small flattened `ci:` list is the
   tested matrix.
8. **Compose, don't copy.** Shared sections (prereqs, install router,
   verification, benchmark, cleanup) are `import`ed fragments with
   parameters; fragments import fragments, and headings re-base to their
   host section depth automatically.

## Three personas

| Persona | What they touch | What they get |
| --- | --- | --- |
| **Guide writer** | plain markdown + two statements (`when`, `import`); guide-specific env choices; fragments owned per dimension/team | a thin guide (~6 import lines + prose); shared sections maintained once for all guides |
| **Guide reader** | [`readonly-guide.html`](guides/optimized-baseline/readonly-guide.html) on llm-d.ai · [`readonly-guide.md`](guides/optimized-baseline/readonly-guide.md) on GitHub | pickers in dimension order (invalid combos unselectable, deep-linkable URLs) · default path expanded, alternatives in collapsible sections |
| **CI** (a special user) | `plan --set dim=value … --format yaml\|bash` per matrix cell | an executable, verifiable run derived fresh from the guide — exactly what a human would have typed; dry-run on every PR, e2e on the tested matrix |

## The entire syntax

```markdown
<!-- when accelerator=gpu model=Qwen/Qwen3-32B -->   conditional region (prose/code);
…                                                    ALL pairs hold; k=v1|v2; nestable
<!-- end -->

<!-- import ../common/verify.md key=value -->        pull a shared fragment (one line)

<!-- step -->                                        the next ```bash fence is a step
<!-- step ci=skip anything=else -->                  …optional opaque metadata
<!-- step e2e=skip hide=true -->                     …hidden from readers, in every plan

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

## Dry-run vs e2e

Every PR can't afford a real deployment, so CI has two flavors of the same
guide — selected purely by opaque metadata and the generic `--skip` filter,
with **one** presentation attribute (`hide=true`) keeping dry-run stand-ins
out of readers' sight:

| Step marker | Readers see it | Dry-run runs it | E2E runs it |
| --- | :-: | :-: | :-: |
| `<!-- step -->` | ✔ | ✔ | ✔ |
| `<!-- step ci=skip -->` (human-only: clone, HF token) | ✔ | — | — |
| `<!-- step dry-run=skip -->` (real install / wait / benchmark) | ✔ | — | ✔ |
| `<!-- step e2e=skip hide=true -->` (its dry-run equivalent: `helm template`, `kubectl kustomize`, URL check) | — | ✔ | — |

```bash
# every PR, every matrix cell — cheap:
guidemd.py plan guide.template.md --set … --skip ci=skip --skip dry-run=skip --format bash | bash
# nightly / release / label-gated — real:
guidemd.py plan guide.template.md --set … --skip ci=skip --skip e2e=skip    --format bash | bash
```

A step is dry-runnable by default (runs in both). In the example guide, 16 of
the gateway cell's 32 steps survive into dry-run (env wiring, chart and
kustomize rendering, URL checks) and 26 into e2e.

## Limitations

- **Line-level conditionals.** `when` wraps whole lines/blocks; mid-sentence
  variation needs `{{ dim }}` or restructuring. No OR across different
  dimensions in one condition (write two blocks).
- **Opaque metadata cuts both ways.** A typo (`dry-run=skpi`) is not caught —
  the step silently runs everywhere. Conventions need a lint list eventually.
- **Steps assume one shell session.** `cd`/`source`/`export` persist across
  steps; runners must execute a plan as a single script (or replicate state).
- **Generated files are committed.** `readonly-guide.md` inflates diffs and
  can conflict; the fix is always mechanical (`render-md`), and `validate`
  arbitrates.
- **Source shows all branches.** The authored file interleaves every
  dimension's content; a value that would conditionalize most of the prose is
  a sign it should be a separate guide, not a dimension.
- **Import params are a loose contract.** Unresolved `{{ param }}` is caught;
  a passed-but-unused param is not.
- **Dry-run equivalence is on the honor system.** Nothing verifies a hidden
  stand-in actually approximates its real step.

## Try it

```bash
./guidemd.py validate    guides/optimized-baseline/guide.template.md   # the PR gate
./guidemd.py render-md   guides/optimized-baseline/guide.template.md  # GitHub copy
./guidemd.py render-html guides/optimized-baseline/guide.template.md  # picker page
open guides/optimized-baseline/readonly-guide.html

# CI: the dry-run (every PR) and e2e (matrix) runs for one configuration
./guidemd.py plan guides/optimized-baseline/guide.template.md \
  --set infra_provider=gke --set accelerator=tpu/v6 \
  --skip ci=skip --skip dry-run=skip --format bash | bash -n   # dry-run
./guidemd.py plan guides/optimized-baseline/guide.template.md \
  --set infra_provider=gke --set accelerator=tpu/v6 \
  --skip ci=skip --skip e2e=skip --format bash | bash -n       # e2e

# the tested matrix, GitHub Actions form
./guidemd.py matrix --github guides/optimized-baseline/guide.template.md
```

## Layout

- [`guidemd.py`](guidemd.py) — the compiler (Python, stdlib + PyYAML)
- [`guides/optimized-baseline/guide.template.md`](guides/optimized-baseline/guide.template.md) — authored source: a **full-fidelity port of upstream [`guides/optimized-baseline`](https://github.com/llm-d/llm-d/tree/main/guides/optimized-baseline)** (coverage-checked, no loss of information)
- `guides/optimized-baseline/readonly-guide.{md,html}` — generated reading artifacts
- [`guides/common/`](guides/common/) — shared fragments: `prereqs` (parameterized, the whole section), `install-router`, `install-modelserver` (driven by `KUSTOMIZE_DIR`), `get-router-ip`, `verify`, `benchmark`, `cleanup`

- [`demo/slides.html`](demo/slides.html) — presentation deck (open in a browser, arrow keys)
- [`samples/`](samples/) — derived CI artifacts for one look: dry-run + e2e bash runs, yaml run, Actions matrix

Note: markdown was chosen over Jupyter (JSON diffs are hostile to review) and
runme (no conditionals/composition; our step markers could export to it
mechanically if local runner UX is wanted).
