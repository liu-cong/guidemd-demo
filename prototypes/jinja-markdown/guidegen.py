#!/usr/bin/env python3
"""CLI launcher — the implementation lives in the guidegen/ package:

  guidegen/matrix.py      dimension matrix parsing (dimensions/rules/ci)
  guidegen/guide.py       core: load guide.yaml, render guide.md.j2, collect steps
  guidegen/plan.py        the CI surface: plan -> bash / yaml / json
  guidegen/validate.py    the PR gate checks
  guidegen/render.py      reading artifacts: readonly-guide.md + variants/
  guidegen/html.py        standalone interactive picker page
  guidegen/docusaurus.py  llm-d.ai pages + VariantSwitcher
  guidegen/cli.py         argparse dispatch (imports lazily per command)

A CI consumer needs only matrix + guide + plan.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from guidegen.cli import main  # noqa: E402  (the package shadows this launcher)

main()
