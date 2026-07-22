"""Command dispatch. Each subcommand imports only what it needs, so a CI
consumer running `plan` / `matrix` never touches the reading-artifact,
HTML or website modules."""

import argparse
import json
import sys
from pathlib import Path

from .guide import Guide
from .matrix import short


def load(guide_dir, deep=True):
    g = Guide(guide_dir)
    errors = list(g.errors)
    if deep and not errors:
        from .validate import validate_cells
        errors += validate_cells(g)
    if errors:
        for e in errors:
            print(f"ERROR: {guide_dir}: {e}", file=sys.stderr)
        sys.exit(1)
    return g


def main():
    ap = argparse.ArgumentParser(prog="guidegen.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "render", "render-md", "render-html", "plan",
                 "matrix", "emit-docusaurus"):
        p = sub.add_parser(name)
        p.add_argument("guide_dir")
    sub.choices["render-md"].add_argument("--check", action="store_true")
    sub.choices["matrix"].add_argument("--github", action="store_true")
    sub.choices["emit-docusaurus"].add_argument(
        "-o", "--out", help="output dir (default: <guide>/docusaurus)")
    for name in ("render", "plan"):
        sub.choices[name].add_argument("--set", action="append", metavar="dim=value")
    sub.choices["plan"].add_argument("--format", choices=["bash", "yaml", "json"],
                                     default="yaml")
    sub.choices["plan"].add_argument("--skip", action="append", metavar="key=value")
    args = ap.parse_args()

    if args.cmd == "validate":
        from . import render
        g = load(args.guide_dir)
        problems = render.check(g)
        if problems:
            for p in problems:
                print(f"ERROR: {p}", file=sys.stderr)
            sys.exit("run guidegen.py render-md to refresh the reading artifacts")
        n = len(g.plan(g.matrix.default_cell())["steps"])
        print(f"OK: {args.guide_dir} — {len(g.matrix.supported)} supported "
              f"combinations, {len(g.matrix.ci)} ci cells, {n} steps in the "
              "default plan, reading artifacts fresh")
    elif args.cmd == "render":
        g = load(args.guide_dir, deep=False)
        md, _ = g.render(g.parse_assignment(args.set))
        sys.stdout.write(md)
    elif args.cmd == "render-md":
        from . import render
        g = load(args.guide_dir)
        if args.check:
            problems = render.check(g)
            if problems:
                for p in problems:
                    print(p, file=sys.stderr)
                sys.exit(f"STALE: run guidegen.py render-md {args.guide_dir}")
            print("OK: reading artifacts up to date")
        else:
            written, total, pruned = render.write(g)
            print(f"wrote {written}/{total} reading artifacts"
                  + (f", pruned {pruned} orphan(s)" if pruned else ""))
    elif args.cmd == "render-html":
        from .html import render_html
        g = load(args.guide_dir)
        out = Path(args.guide_dir) / "readonly-guide.html"
        out.write_text(render_html(g))
        print(f"wrote {out} ({len(g.matrix.supported)} variants pre-rendered)")
    elif args.cmd == "emit-docusaurus":
        from .docusaurus import emit_docusaurus
        g = load(args.guide_dir)
        out = args.out or str(Path(args.guide_dir) / "docusaurus")
        n = emit_docusaurus(g, out)
        print(f"wrote {out}: {n} variant .mdx pages "
              "(+ _variants.json, _VariantSwitcher.jsx)")
    elif args.cmd == "plan":
        from .plan import plan_bash, plan_yaml
        g = load(args.guide_dir, deep=False)
        skips = []
        for item in args.skip or []:
            k, _, v = item.partition("=")
            if g.step_tags and k not in g.step_tags:
                sys.exit(f"--skip {item!r}: {k!r} is not a declared step tag "
                         f"{sorted(g.step_tags)}")
            skips.append((k, v))
        plan = g.plan(g.parse_assignment(args.set), skips=skips)
        if args.format == "json":
            print(json.dumps(plan, indent=2))
        elif args.format == "yaml":
            sys.stdout.write(plan_yaml(plan))
        else:
            sys.stdout.write(plan_bash(plan))
    elif args.cmd == "matrix":
        g = load(args.guide_dir, deep=False)
        cells = g.matrix.ci or g.matrix.supported
        entries = [{"guide": g.meta.get("name"), **c} for c in cells]
        if args.github:
            print(json.dumps({"include": entries}))
        else:
            for e in entries:
                dims = [f"{k}={v}" for k, v in e.items() if k != "guide"]
                print(f"{e['guide']:22s} {' '.join(dims)}")
