# guidemd — executable, dimension-aware guides for llm-d

One source of truth per guide. Everything else — the docs pages, the GitHub
reading copy, the CI runs, the job matrix — is derived from it and can never
drift from it.

## Background

The current pain points for llm-d guides include:

**For guide readers:**

- Monolithic guides covering multiple dimensions (e.g., infra provider,
  accelerator, model server) are distracting for users focused on a specific
  configuration.
- Determining support status or locating test results for specific
  configuration combinations (e.g., "Can I run PD disaggregation with RDMA on
  TPU using SGLang?") is difficult.

**For guide writers:**

- Significant portions of most guides contain duplicated content (such as
  router installation steps), leading to consistency drift over time.
- No structured mechanism exists to add dimension-specific content (e.g.,
  adding a [model streamer](https://github.com/llm-d/llm-d/issues/1284) for
  GKE TPU) without cluttering the entire guide.

**For llm-d CI:**

- The lack of a defined contract between the guide and the CI pipeline makes
  "magical parsing" fragile, often requiring hacky patches to accommodate
  guide updates.

## Requirements

*Priority definitions — P0: required; P1: highly desirable but negotiable;
P2: nice to have.*

**For guide readers**

- **P0:** Provide an interactive, contextual guide on llm-d.ai where users
  select a configuration (infra provider, accelerator, etc.) to view curated,
  applicable content.
  - The same configuration links to related test status, benchmark results,
    and known issues.
- **P1:** Maintain a readable guide format on GitHub or in local editors.

**For guide writers**

- **P0:** Implement a structured mechanism to add dimension-specific content
  without adding noise to irrelevant configurations.
- **P1:** Maintain common sections in a single source and import them as
  needed.

**For llm-d CI**

- **P0:** Automatically derive executable, verifiable runs from the guide for
  any supported dimension combination to prevent drift between documentation
  and CI.
- **P1:** Ensure validation is affordable on every PR via default dry-runs,
  with full end-to-end testing per matrix cell executed on a schedule or on
  demand.

## Non-goals

- Modifying the llm-d stack installation process. The proposed solution is
  agnostic to the installation method.
- Facilitating highly customized installations. The focus remains on
  out-of-the-box recipes provided by llm-d well-lit path guides with minimal
  customization (e.g., modifying the installation namespace).

## Design principles

1. **Single source of truth:** Avoid forks per dimension value or parallel
   documentation tracks.
2. **Automated generation:** Readers and CI consume derived artifacts. A
   `validate` gate prevents PR merges if drift occurs.
3. **CI as a standard user:** The CI pipeline executes guide steps
   sequentially without interpreting custom semantics.
4. **Structured guide dimensions:** Dimensions allow owners to author
   branches in isolation while providing readers with a distraction-free
   contextual guide. CI configuration is auto-generated for a particular
   configuration. All supported and CI-validated configurations are
   declarative.
5. **Composition over duplication:** Shared sections are managed as imported
   fragments with parameters.

## Design space

Balancing an interactive reading experience, an intuitive writing workflow,
and maintainable tooling is challenging. This repository holds multiple
proof-of-concepts (PoCs) — none is perfect.

Our asks:

- Let's align on the requirements first before jumping to any solutions.
- Acknowledge that any chosen solution will incur non-trivial costs,
  requiring project leader alignment and commitment.

## The prototypes

Three PoCs: a snapshot of 
([`prototypes/pr1988-guide-yaml/`](prototypes/pr1988-guide-yaml/) —
[llm-d/llm-d#1988](https://github.com/llm-d/llm-d/pull/1988), focusing on rendering
the Markdown guide and CI run from a single guide.yaml source containing runnable steps.
It serves the "CI" persona requirements only and doesn't touch the guide prose.

The two successors built on the requirements above and extended to support dynamic prose rendering and 
reusable imports. They differ in *what the authored source is* — annotated plain markdown
([`prototypes/annotated-markdown/`](prototypes/annotated-markdown/)) vs. a
Jinja2 template + data file
([`prototypes/jinja-markdown/`](prototypes/jinja-markdown/)).

### Requirements coverage

| Requirement | [`pr1988-guide-yaml`](prototypes/pr1988-guide-yaml/) (baseline) | [`annotated-markdown`](prototypes/annotated-markdown/) | [`jinja-markdown`](prototypes/jinja-markdown/) |
| --- | --- | --- | --- |
| **Reader P0** · interactive contextual guide | ✖ | ✔ | ✔ |
| **Reader P0** · configuration ↔ test status | ✖ | ✔ | ✔  |
| **Reader P1** · readable on GitHub / locally |  ✔ (similar to today) |  ✔ (similar to today) |  ✔(but needs a CI job to pre generate readable markdowns) |
| **Writer P0** · dimension-specific content without noise | ✖  `when:` on bash steps only — prose cannot vary | ✔ `<!-- when -->` regions over prose and code | ✔ `{% if %}` over anything; `{% else %}` makes coverage gaps hard to write |
| **Writer P1** · common sections maintained once | ✖ none | ✔ `<!-- import -->` fragments with parameters, automatic heading re-basing | ✔ `{% include %}` partials (Jinja macros where parameters are needed) |
| **CI P0** · derived executable, verifiable runs | ✔ | ✔ `plan` derived from the source; steps tagged, tag keys declared | ✔ `plan` is the *same render* as the docs; stable step ids + template `file:line` provenance |
| **CI P1** · affordable per-PR validation | ✔ (can be extended to support dry-run) | ✔  | ✔  |

### Other trade-offs

| | `pr1988-guide-yaml` (baseline) | `annotated-markdown` | `jinja-markdown` |
| --- | --- | --- | --- |
| Source of truth | `guide.yaml` (bash steps as YAML data) + a shared README template | **one plain-markdown file** with invisible comment directives (`when` / `import` / `step`) | **one Jinja2 template** + `guide.yaml`: `{% if %}` / `{% include %}` / inline `{% step %}` blocks |
| Parser to maintain | ~800 lines across the validate/render/check script triad | ~300 lines of bespoke document parsing (fences, comments, provenance) | **none** — Jinja parses everything, incl. the `{% step %}` tag via Jinja's extension API |
| Syntax familiarity | plain YAML, custom schema | custom invisible comment directives (`when` / `import` / `step`) | standard Jinja — known from Ansible/Helm/Hugo, editor-supported |
| Step identity & provenance | named sections + step position in the YAML | positional; provenance hand-threaded through import expansion | optional `id=`; template `file:line` baked in by Jinja at parse time |
| Authoring flow | two files: write runs in YAML, then place them into the README — tedious for a 20-step guide, though scriptable | single file — steps written in-place in the narrative | single file — steps written in-place in the narrative |
| Steps as structured data | ✔ inherent — key/value YAML, easy to parse/lint and feed to downstream consumers directly | derived — compiler emits the plan as yaml/json/bash | derived — render emits the plan as yaml/json/bash |
| CI overrides & dry-run extension | natural per-step fields: a run can carry its dry-run variant; values or whole blocks substitutable per combination by key | `dry-run=skip` tags + hidden stand-in steps; value substitution via `{{ dim }}` | same tag convention; values via dimensions-as-env-vars (`configure` step) or `{{ }}` |
| Validation of step content | schema validation + YAML↔markdown cross-check for idempotency | fence policing, declared tags, freshness gate | fence policing, declared tags, group partition check, `StrictUndefined`, `bash -n`, freshness gate |

### The fundamental split: YAML-source vs markdown-source

Behind the table sits one philosophical fork — where do the runnable steps
live?

**Where the YAML approach wins**

- Runnable steps are *born* structured: a plain key/value file that is easy
  to parse, lint, schema-validate, and feed to downstream consumers (CI)
  directly — with independent validation of YAML and markdown plus a
  cross-check between them for idempotency.
- Per-step extension is natural: a run step can carry its dry-run variant,
  and CI can override simple values or whole blocks per combination by key.
- Multiple machine viewpoints for free: execution-only YAML, or a fully
  annotated generated script.

**Where the markdown approach wins**

- Single-file authoring: with 20 steps, writing each run in YAML and then
  finding the right insertion point back in the markdown is a constant
  context switch; in markdown the step is written where it belongs in the
  narrative.
- Conditions apply to **any block, not just runnable steps** — conditional
  prose is a writer P0, and a YAML-side `when:` can never reach prose.
- The generated picker page presents the supported combinations statically —
  readers see their configuration instead of deciphering conditionals
  themselves.

**Costs both sides pay, and how the PoCs respond**

- Every option invents *something*: the YAML approach invents a schema (a
  language expressed in data); annotated-markdown invents comment directives
  plus a parser; jinja-markdown avoids owning a parser but still defines
  conventions (`{% step %}`, tags, groups).
- "Markdown can't override by key/value" — true for annotated-markdown as
  built; the jinja PoC substitutes values via dimensions-as-env-vars and
  `{{ }}`, and block-level substitution is an `{% if %}` branch.
- "Markdown lacks reproducibility validation" — partially answered by the
  current gates (fence policing, group partitions, `bash -n`, artifact
  freshness); schema-level validation of step *content* remains a genuine
  YAML strength.
- "Placing YAML step ids into a long README is tedious" — scriptable in
  principle, but it stays a two-file workflow.

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
