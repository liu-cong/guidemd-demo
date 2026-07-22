# steps-as-code — structure is authored as structure; prose is a projection

The second prototype answers the question the first one raised: *what if
there were nothing to parse?* Instead of annotating one markdown file and
excavating structure out of it, the guide is authored as three kinds of
files, each parsed by a tool nobody here maintains:

```
guides/optimized-baseline/
  guide.yaml        dimensions, rules, ci matrix, env constants     (PyYAML)
  steps/*.sh        guide-specific steps — REAL shell scripts       (bash)
  guide.md.j2       the prose narrative — Jinja2 over markdown      (Jinja2)
common/
  steps/*.sh        shared steps (install router, verify, cleanup…)
  *.md.j2           shared prose partials ({% include %})
```

**There is no document parser.** `guidegen.py` (~600 lines, half of it the
HTML page) is matrix logic, a Jinja environment, and emitters. The annotated
prototype's hardest 300 lines — fence tracking, comment scanning, provenance
threading — have no equivalent here because the problems they solve don't
exist.

## How it fits together

- **Dimension values are environment variables.** One generated `configure`
  step exports `${ACCELERATOR}`, `${GATEWAY_PROVIDER}`, … plus the guide's
  `env:` constants. Step scripts consume plain `$VARS` — every `.sh` file is
  valid, shellcheck-able shell exactly as committed, with zero template
  syntax. (This is also how the upstream guides already think: everything is
  `${NAMESPACE}`, `${REPO_ROOT}`, …)
- **The template is the document AND the plan.** `{{ step("install-router") }}`
  renders the fence in docs and records the step during a collect pass —
  plan = render for a cell, keep the recorded steps, filter by `--skip`
  tags. Execution order is document order; CI still mimics a reader.
- **Conditionals are Jinja.** `{% if accelerator == "gpu" %} … {% elif %} …
  {% else %}` — and the `else` branch makes the "add a dimension value
  later, silently lose commands" trap structurally hard to write, where the
  annotated prototype needed a heuristic warning to catch it.
- **Composition is `{% include %}`** (Jinja macros where parameters are
  needed). Partials are written at their target heading depth.

## What the inversion dissolves

Problems the annotated prototype needed bespoke machinery for become
queries or disappear:

| annotated-markdown | steps-as-code |
| --- | --- |
| positional steps (no ids — a documented trade-off) | **filenames are stable ids**: resume, flake history, readable plans (`step 9/25: install-router-gateway`) |
| provenance threaded through import expansion | the step **is** a file; Jinja reports template file:line natively |
| adjacency heuristic + connected components to warn about `when`-group gaps | explicit `# group:` headers — validate checks *every supported cell selects exactly one member*; `{% else %}` prevents most gaps at authoring time |
| unmarked-bash-fence detection via document parsing | rendered fences are counted against `step()` calls — a hand-written ```` ```bash ```` fence fails validation |
| `{{ }}` substitution + typo checks (custom) | Jinja `StrictUndefined` — a typo'd variable is a render error |
| shellcheck: possible in principle | trivial: the steps are already `.sh` files |

Validated equivalence: the **cross-prototype parity suite** loads both
compilers and asserts identical supported matrices and identical per-cell
step counts for all 96 variants × 3 plan flavors
([tests/test_guidegen.py](tests/test_guidegen.py)).

## The honest costs

- **The authored template is not a readable guide.** `guide.md.j2` has holes
  where steps go. The reading artifact is generated — `readonly-guide.md`
  (default configuration) and the interactive page. The annotated prototype's
  folded-`<details>` GitHub copy showing *all* variants in one document has
  no equivalent here; per-variant rendering replaces it.
- **A guide is many files, not one.** Reviewing "what does the TPU variant
  do" means the template plus the step files it references. Ownership
  mapping (CODEOWNERS per file) gets better; single-file readability gets
  worse.
- **Jinja is a real dependency** (the annotated prototype needs only PyYAML)
  and Jinja-in-markdown needs `{% raw %}` discipline if prose ever contains
  literal braces.
- **Two-pass authoring.** Adding a step = create the file + reference it in
  the template. The unused-step warning and unknown-id error catch the two
  ways to forget.

## Try it

```bash
./guidegen.py validate    guides/optimized-baseline            # the PR gate
./guidegen.py validate --cells guides/optimized-baseline       # per-variant step counts
./guidegen.py render-md   guides/optimized-baseline            # committed GitHub copy
./guidegen.py render-html guides/optimized-baseline            # picker page (96 variants)
./guidegen.py render      guides/optimized-baseline --set accelerator=tpu/v6  # one variant

# CI plans — same tag conventions as the annotated prototype
./guidegen.py plan guides/optimized-baseline \
  --set router_mode=gateway --set gateway_provider=istio \
  --skip ci=skip --skip dry-run=skip --format bash            # cluster-free dry-run
./guidegen.py plan guides/optimized-baseline \
  --skip ci=skip --skip e2e=skip --format yaml                # e2e, structured

./guidegen.py matrix --github guides/optimized-baseline       # the 8 tested cells
python3 -m unittest discover -s tests -q                      # 21 tests incl. parity
```
