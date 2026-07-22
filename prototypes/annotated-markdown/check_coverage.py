#!/usr/bin/env python3
"""check_coverage.py — "no loss of information" gate for a ported guide.

Verifies that adopting guidemd caused no content loss relative to the
upstream markdown guide it replaces:

  1. COMMANDS  every non-comment bash line in the upstream doc must appear
               (whitespace-normalized) in the bash blocks of at least one
               supported variant's rendered guide.
  2. HEADINGS  every upstream heading (normalized text, level ignored) must
               appear in at least one supported variant's rendered guide.

Intentional deviations (renamed variables, hardened commands, structure
moved into dimensions) are recorded in a WAIVERS file next to the upstream
fixture: one Python regex per line, matched against the normalized upstream
line; `#` starts a comment. A waiver that matches nothing is an error too —
stale waivers must be pruned.

Usage:
  ./check_coverage.py UPSTREAM.md GUIDE.template.md [--waivers WAIVERS.txt]

Exit status: 0 = full coverage; 1 = something upstream is not covered.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guidemd import RE_FENCE, Guide  # noqa: E402

RE_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")


def norm(line):
    return re.sub(r"\s+", " ", line).strip()


def bash_lines(text, langs=("bash",)):
    """Normalized, non-comment lines inside command fences.

    Upstream is measured on ```bash only; the ported corpus also counts
    display-only command fences (```console …) — information preserved as a
    non-executable snippet still counts as preserved.
    """
    out, in_cmd = [], False
    for line in text.splitlines():
        m = RE_FENCE.match(line)
        if m:
            in_cmd = m.group(1) in langs if not in_cmd else False
            continue
        if not in_cmd:
            continue
        n = norm(line)
        if n and not n.startswith("#"):
            out.append(n)
    return out


def headings(text):
    out, in_fence = [], False
    for line in text.splitlines():
        if RE_FENCE.match(line):
            in_fence = not in_fence
            continue
        m = RE_HEAD.match(line) if not in_fence else None
        if m:
            out.append(norm(re.sub(r"[0-9]+\.\s*", "", m.group(2))).lower())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("upstream")
    ap.add_argument("guide")
    ap.add_argument("--waivers", help="regex-per-line waiver file")
    args = ap.parse_args()

    guide = Guide(args.guide)
    if guide.errors:
        for e in guide.errors:
            print(f"ERROR: {args.guide}: {e}", file=sys.stderr)
        sys.exit(1)

    waivers = []
    if args.waivers:
        for raw in Path(args.waivers).read_text().splitlines():
            src = raw.split("#", 1)[0].strip()
            if src:
                waivers.append((src, re.compile(src)))

    # Union of every supported variant's rendered guide (the reader corpus).
    corpus_cmds, corpus_heads = set(), set()
    for cell in guide.matrix.supported or [guide.matrix.default_cell()]:
        rendered = guide.render_markdown(cell)
        corpus_cmds.update(bash_lines(rendered, langs=("bash", "console", "sh", "shell")))
        corpus_heads.update(headings(rendered))

    up = Path(args.upstream).read_text()
    missing, waived, used = [], [], set()
    for line in bash_lines(up):
        if line in corpus_cmds:
            continue
        hit = next((src for src, rx in waivers if rx.search(line)), None)
        if hit:
            waived.append(line)
            used.add(hit)
        else:
            missing.append(("command", line))
    for head in headings(up):
        if not any(head in h for h in corpus_heads):
            hit = next((src for src, rx in waivers if rx.search(head)), None)
            if hit:
                used.add(hit)
            else:
                missing.append(("heading", head))

    stale = [src for src, _ in waivers if src not in used]
    total = len(bash_lines(up)) + len(headings(up))
    print(f"coverage: {total - len(missing) - len(waived)}/{total} upstream items "
          f"verbatim, {len(waived)} waived, {len(missing)} MISSING "
          f"({len(guide.matrix.supported)} variants searched)")
    for kind, item in missing:
        print(f"MISSING {kind}: {item}", file=sys.stderr)
    for src in stale:
        print(f"STALE WAIVER (matches nothing): {src}", file=sys.stderr)
    sys.exit(1 if missing or stale else 0)


if __name__ == "__main__":
    main()
