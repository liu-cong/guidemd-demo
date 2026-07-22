# jinja-markdown — one Jinja2 template, zero owned parsers

The second prototype answers the question the first one raised: *what if
there were nothing to parse?* A guide is **two authored files** — data and
a template — each handled by a tool nobody here maintains:

```
guides/optimized-baseline/
  guide.yaml        dimensions, rules, ci matrix, env constants   (PyYAML)
  guide.md.j2       the guide: markdown prose + Jinja2 logic +
                    INLINE executable steps                       (Jinja2)
common/
  *.md.j2           shared prose partials ({% include %})
```

The tool is a small package of single-purpose modules — consumers take
only what they need (CI needs just the first three):

```
guidegen/matrix.py      dimension matrix parsing (dimensions/rules/ci)
guidegen/guide.py       core: load guide.yaml, render guide.md.j2, collect steps
guidegen/plan.py        the CI surface: plan -> bash / yaml / json
guidegen/validate.py    the PR gate checks
guidegen/render.py      reading artifacts: readonly-guide.md + variants/
guidegen/html.py        standalone interactive picker page
guidegen/docusaurus.py  llm-d.ai pages + VariantSwitcher
guidegen/cli.py         dispatch (lazy imports per subcommand)
```

It owns **no document parser** — Jinja parses the template, including our
one custom tag, `{% step %}`, registered through Jinja's documented
extension API (~30 lines that *use* Jinja's parser, not replace it). What
remains custom is the matrix/rules/plan logic that is custom in any design.

## The authoring model

```jinja
{% if accelerator == "gpu" %} … {% elif … %} … {% else %} … {% endif %}
{% include "prereqs.md.j2" %}
{{ model }}

{% step tags="dry-run=skip" %}
kubectl apply -f https://…/${GAIE_VERSION}/v1-manifests.yaml
{% endstep %}
{% step tags="e2e=skip", hide=true %}
curl -sfL https://…/${GAIE_VERSION}/v1-manifests.yaml -o /dev/null
{% endstep %}

{% step group="select-overlay" %} … {% endstep %}   exactly-one-per-cell check
{% step id="install-router", … %} … {% endstep %}   optional stable id
{{ configure_step() }}                              generated env exports
```

Steps are written **inline where they belong in the narrative** — no
separate files, no import indirection. A step renders as a ```bash fence
for readers and is recorded for the plan in the same pass: plan = render
the template for a cell, keep the recorded steps, filter by `--skip` tags.
Execution order is document order; CI still mimics a reader.

Dimension values reach steps as **environment variables** (`${ACCELERATOR}`,
`${GATEWAY_PROVIDER}`, …) exported by one generated `configure` step
together with the guide's `env:` constants — bodies stay copy-pasteable
shell. `{{ }}` substitution inside bodies also works when preferred.

## What the design gives structurally

| concern | mechanism |
| --- | --- |
| provenance | Jinja bakes template `file:line` into every step at parse time |
| step identity | optional `id="…"` (validated unique); default is `file:line` |
| exhaustiveness | `group=` → every supported cell must select exactly one member; `{% else %}` makes gaps hard to write at all |
| nothing escapes CI | a rendered ```bash fence not produced by `{% step %}` fails validation (use ```console for display-only) |
| typo'd variables | Jinja `StrictUndefined` — render error, not silent text |
| typo'd tags | keys checked against `step_tags:` in guide.yaml |
| shell sanity | `bash -n` over every step body of every variant |

Validated equivalence: the **cross-prototype parity suite** asserts
identical supported matrices and identical per-cell step counts vs the
annotated-markdown prototype across 96 variants × 3 plan flavors
([tests/test_guidegen.py](tests/test_guidegen.py)).

## Reading on GitHub / at a checkout

`render-md` produces the zero-tooling reading surface, freshness-gated by
`validate`:

- **`readonly-guide.md`** — the default configuration, with a
  **configuration table** right under the title: every supported
  combination in a collapsed `<details>` block, each row linking to its
  pre-rendered copy.
- **`variants/<slug>.md`** — one fully rendered guide per non-default
  combination (95 files), each personalized end to end and linking back to
  the index. Orphaned variants (combinations that stop being supported)
  are pruned on regeneration and flagged by the freshness check.

So a reader who never leaves GitHub — or is browsing a local checkout with
no Python — opens the table, clicks their row, and gets exactly their
guide. Tool users can instead run
`./guidegen.py render guides/optimized-baseline --set accelerator=tpu/v6`.

## Docusaurus integration (`emit-docusaurus`)

llm-d.ai currently copies guide markdown into its Docusaurus build. This
prototype keeps that pipeline shape — it just changes what gets copied:

```bash
./guidegen.py emit-docusaurus guides/optimized-baseline
```

emits, per guide:

- **`index.mdx`** — the default configuration, a normal listed doc page
  (sidebar, search, SEO, versioning all standard Docusaurus)
- **one `.mdx` per other supported variant** with `unlisted: true` —
  a real static page (theme + deep-linkable + no-JS readable), but hidden
  from the sidebar, search index and sitemap, so 95 variants don't spam
  navigation
- **`_VariantSwitcher.jsx`** — cascading pickers in dimension order;
  picking a variant *navigates* to that variant's own static page (no
  client-side markdown rendering at all)
- **`_variants.json`** — the support matrix + slugs
  (underscore-prefixed files are ignored by Docusaurus's page loader)

GitHub `> [!NOTE]` alerts are converted to `:::note` admonitions on the
way out. The site's sync step runs `emit-docusaurus` against the llm-d
repo at the pinned release tag and copies the output directory — the same
copy-at-build model the website already uses for markdown. Remaining
site-side work: repo-relative link rewriting (the existing sync already
does this for today's guides) and a decision on whether unlisted variants
should be search-indexed.

## The honest costs

- **The authored template is not a readable document.** Prose reads fine,
  but Jinja tags interleave with it; the reading artifacts are generated
  (`readonly-guide.md` = default configuration, the interactive page, the
  Docusaurus pages). The annotated prototype's single GitHub document with
  *all* variants in collapsed `<details>` has no equivalent here.
- **Writers must learn Jinja basics** — `{% if %}`, `{% include %}`,
  `{% step %}`. Familiar to anyone who has touched Ansible/Helm/Hugo, but
  it is a template language, not plain markdown; `{% raw %}` discipline is
  needed if prose ever contains literal braces.
- **Jinja2 is a real dependency** (the annotated prototype needs only
  PyYAML).
- **Plain markdown is not a valid guide here** — migration means
  converting a README into a template, not sprinkling annotations on it.

## Try it

```bash
./guidegen.py validate    guides/optimized-baseline            # the PR gate
./guidegen.py render-md   guides/optimized-baseline            # index + variants/ (GitHub copy)
./guidegen.py render-html guides/optimized-baseline            # picker page (96 variants)
./guidegen.py emit-docusaurus guides/optimized-baseline        # llm-d.ai pages + switcher
./guidegen.py render      guides/optimized-baseline --set accelerator=tpu/v6

./guidegen.py plan guides/optimized-baseline \
  --set router_mode=gateway --set gateway_provider=istio \
  --skip ci=skip --skip dry-run=skip --format bash             # cluster-free dry-run
./guidegen.py plan guides/optimized-baseline \
  --skip ci=skip --skip e2e=skip --format yaml                 # e2e, structured

./guidegen.py matrix --github guides/optimized-baseline        # the 8 tested cells
python3 -m unittest discover -s tests -q                       # 26 tests incl. parity
```
