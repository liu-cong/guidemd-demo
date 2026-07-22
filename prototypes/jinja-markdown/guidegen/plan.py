"""The CI surface: format a plan (from Guide.plan) as bash, yaml or json.

This is everything a CI consumer needs beyond guide.py — no reading
artifacts, no HTML, no website code.
"""

import yaml


def plan_bash(plan):
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
