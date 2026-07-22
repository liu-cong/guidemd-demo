"""The CI surface: format a plan as bash, yaml or json.

A *plan* is the plain dict returned by ``Guide.plan(cell, skips)`` — this
module only formats it; it never touches Jinja or the filesystem. Together
with matrix.py and guide.py this is everything a CI consumer needs.

Example plan (two steps, trimmed):

    {"guide": "optimized-baseline",
     "doc": "guides/optimized-baseline/guide.md.j2",
     "assignment": {"infra_provider": "base", "accelerator": "gpu", ...},
     "steps": [
       {"id": "configure", "src": "<generated:configure>", "meta": {},
        "run": 'export INFRA_PROVIDER="base"\\nexport ACCELERATOR="gpu"'},
       {"id": "install-router", "src": "install-router.md.j2:27",
        "meta": {"dry-run": "skip"},
        "run": "helm install ${GUIDE_NAME} \\\\\\n  ${ROUTER_STANDALONE_CHART} ..."},
     ]}

(There is no plan_json: cli.py just ``json.dumps`` the dict as-is.)
"""

import yaml


def plan_bash(plan):
    """One flat, runnable script — the "CI mimics a human" execution format.

    Steps share a single shell session (``cd``/``export``/``source`` carry
    across), and ``set -euo pipefail`` makes the first failing step fail
    the run. Each step is prefixed with its position, id and tags so a CI
    log points straight back at the source.

    For the example plan above, returns:

        #!/usr/bin/env bash
        # optimized-baseline — generated from guides/optimized-baseline/guide.md.j2
        # assignment: {'infra_provider': 'base', 'accelerator': 'gpu', ...}
        set -euo pipefail

        # --- step 1/2: configure ---
        export INFRA_PROVIDER="base"
        export ACCELERATOR="gpu"

        # --- step 2/2: install-router  [dry-run=skip] ---
        helm install ${GUIDE_NAME} \\
          ${ROUTER_STANDALONE_CHART} ...

    Typical use:  guidegen.py plan <guide> --set ... --skip ci=skip \\
                    --skip dry-run=skip --format bash | bash
    """
    lines = ["#!/usr/bin/env bash",
             f"# {plan['guide']} — generated from {plan['doc']}",
             f"# assignment: {plan['assignment']}",
             "set -euo pipefail"]
    for n, s in enumerate(plan["steps"], 1):
        meta = ("  [" + " ".join(f"{k}={v}" for k, v in s["meta"].items()) + "]"
                if s["meta"] else "")
        lines += ["", f"# --- step {n}/{len(plan['steps'])}: {s['id']}{meta} ---",
                  s["run"]]
    return "\n".join(lines) + "\n"


def plan_yaml(plan):
    """Structured plan for runners that execute steps INDIVIDUALLY — e.g. a
    CI harness that wants per-step timeouts, retries or progress reporting,
    or an agent inspecting what a run would do. (Note: steps still assume
    one shared shell session; a step-at-a-time runner must replay earlier
    ``export``s, e.g. by re-running steps 1..n.)

    The custom dumper forces multi-line strings into literal block scalars
    (``run: |``) so bash bodies stay verbatim and copy-pasteable instead of
    becoming quoted one-liners full of ``\\n``.

    For the example plan above, returns:

        guide: optimized-baseline
        assignment:
          infra_provider: base
          accelerator: gpu
        steps:
        - id: configure
          src: <generated:configure>
          run: |
            export INFRA_PROVIDER="base"
            export ACCELERATOR="gpu"
        - id: install-router
          src: install-router.md.j2:27
          meta:
            dry-run: skip
          run: |
            helm install ${GUIDE_NAME} \\
              ${ROUTER_STANDALONE_CHART} ...
    """
    class LiteralDumper(yaml.SafeDumper):
        pass

    def _str(dumper, value):
        style = "|" if "\n" in value else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)

    LiteralDumper.add_representer(str, _str)
    doc = {"guide": plan["guide"], "assignment": plan["assignment"],
           "steps": [{"id": s["id"], "src": s["src"],
                      **({"meta": s["meta"]} if s["meta"] else {}),
                      "run": s["run"] + "\n"} for s in plan["steps"]]}
    return yaml.dump(doc, Dumper=LiteralDumper, sort_keys=False, width=100)
