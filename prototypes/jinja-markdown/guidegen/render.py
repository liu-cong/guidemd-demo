"""Reading artifacts for GitHub / local checkouts.

  readonly-guide.md   the DEFAULT configuration, with a configuration table
                      listing every supported combination; the CI-covered
                      ones link to pre-rendered copies
  variants/<slug>.md  one fully rendered guide per non-default CI cell —
                      readable with zero tooling. Combinations outside the
                      CI matrix are served by the website / `render --set`
                      (the interactive page and Docusaurus output still
                      cover all supported combinations).

Everything is generated; `check()` reports staleness and orphans so the PR
gate can enforce freshness.
"""

import re
from pathlib import Path

from .matrix import short, variant_slug

RENDERED_MD = "readonly-guide.md"
VARIANTS_DIR = "variants"


def _banner(what):
    return (f"<!-- GENERATED FILE — DO NOT EDIT. {what} "
            "Regenerate with: guidegen.py render-md <guide dir> -->")


def _config_table(guide):
    """The pick-your-configuration table linking to pre-rendered variants."""
    m = guide.matrix
    default = m.default_cell()
    labels = [m.dims[d].get("label", d) for d in m.order]
    lines = [
        "## Configurations",
        "",
        "This document shows the **default configuration**. Every CI-tested",
        "configuration has a pre-rendered guide:",
        "",
        "| " + " | ".join(labels) + " | Guide |",
        "|" + "---|" * (len(labels) + 1),
    ]
    for cell in m.ci:
        row = " | ".join(cell[d] for d in m.order)
        if cell == default:
            link = "**this document**"
        else:
            link = f"[open]({VARIANTS_DIR}/{variant_slug(cell, m.order)}.md)"
        lines.append(f"| {row} | {link} |")
    lines += [
        "",
        f"The other supported combinations ({len(m.supported) - len(m.ci)} of "
        f"{len(m.supported)}) are served by the interactive page, or render "
        "yours locally: `guidegen.py render <guide dir> --set dim=value …`.",
    ]
    return "\n".join(lines)


def render_index(guide):
    """readonly-guide.md: default variant + the configuration table."""
    cell = guide.matrix.default_cell()
    md, _ = guide.render(cell)
    table = _config_table(guide) + "\n"
    # insert the table right below the top-level heading
    m = re.match(r"^(# .*\n)", md)
    if m:
        md = md[:m.end()] + "\n" + table + md[m.end():]
    else:
        md = table + "\n" + md
    return _banner("Default configuration.") + "\n" + md


def render_variant(guide, cell):
    md, _ = guide.render(cell)
    head = (f"> **Configuration:** {short(cell)} — "
            f"[all configurations](../{RENDERED_MD})\n")
    return _banner(f"Variant: {short(cell)}.") + "\n" + head + "\n" + md


def expected(guide):
    """{path: content} for every reading artifact of this guide.

    Pre-rendered variants are committed only for the CI-covered cells —
    the website surfaces (render-html / emit-docusaurus) still cover all
    supported combinations.
    """
    out = {Path(guide.dir) / RENDERED_MD: render_index(guide)}
    default = guide.matrix.default_cell()
    for cell in guide.matrix.ci:
        if cell == default:
            continue
        slug = variant_slug(cell, guide.matrix.order)
        out[Path(guide.dir) / VARIANTS_DIR / f"{slug}.md"] = \
            render_variant(guide, cell)
    return out


def write(guide):
    """Write all reading artifacts; prune orphaned variant files."""
    files = expected(guide)
    (Path(guide.dir) / VARIANTS_DIR).mkdir(exist_ok=True)
    written = 0
    for path, content in files.items():
        if not path.exists() or path.read_text() != content:
            path.write_text(content)
            written += 1
    pruned = 0
    keep = {p.name for p in files if p.parent.name == VARIANTS_DIR}
    for stray in (Path(guide.dir) / VARIANTS_DIR).glob("*.md"):
        if stray.name not in keep:
            stray.unlink()
            pruned += 1
    return written, len(files), pruned


def check(guide):
    """Freshness gate: stale/missing artifacts and orphaned variants."""
    problems = []
    files = expected(guide)
    for path, content in files.items():
        if not path.exists():
            problems.append(f"missing: {path}")
        elif path.read_text() != content:
            problems.append(f"stale: {path}")
    keep = {p.name for p in files if p.parent.name == VARIANTS_DIR}
    vdir = Path(guide.dir) / VARIANTS_DIR
    if vdir.is_dir():
        for stray in vdir.glob("*.md"):
            if stray.name not in keep:
                problems.append(f"orphaned variant: {stray}")
    return problems
