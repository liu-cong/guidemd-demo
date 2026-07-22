"""The PR gate: render every supported cell and check the invariants.

Returns errors as a list; nothing here is needed by CI consumers.
"""

import re
import subprocess
import tempfile

from .matrix import short


def validate_cells(guide):
    """Tag keys, duplicate ids, fence policing, group partitions, bash -n."""
    errors = []
    bodies = set()
    group_members = {}
    per_cell_selection = []
    for cell in guide.matrix.supported:
        try:
            md, collected = guide.render(cell)
        except Exception as e:  # jinja2.TemplateError with location prefixed
            errors.append(f"cell {short(cell)}: {e}")
            continue
        sel = {}
        for s in collected:
            bodies.add(s["run"])
            for k in s["tags"]:
                if k not in guide.step_tags:
                    errors.append(
                        f"{s['src']}: tag key {k!r} not declared in "
                        f"guide.yaml step_tags {sorted(guide.step_tags)}")
            if s["group"]:
                sel.setdefault(s["group"], set()).add(s["src"])
                group_members.setdefault(s["group"], set()).add(s["src"])
        per_cell_selection.append((cell, sel))
        explicit = {}
        for s in collected:
            if s["id"] != s["src"] and s["id"] != "configure":
                explicit.setdefault(s["id"], set()).add(s["src"])
        for sid, srcs in explicit.items():
            if len(srcs) > 1:
                errors.append(f"cell {short(cell)}: step id {sid!r} "
                              f"used at {sorted(srcs)}")
        shown = sum(1 for s in collected if not s["hidden"])
        fences = len(re.findall(r"^```bash\b", md, re.M))
        if fences != shown:
            errors.append(
                f"cell {short(cell)}: {fences} ```bash fences rendered but "
                f"{shown} produced by {{% step %}} — a hand-written bash "
                "fence escapes CI; use ```console for display-only snippets")
    for g in sorted(group_members):
        for cell, sel in per_cell_selection:
            picked = sel.get(g, set())
            if len(picked) != 1:
                errors.append(
                    f"cell {short(cell)}: group {g!r} selected "
                    f"{sorted(picked) or 'nothing'} — every supported cell "
                    "must select exactly one member")
    errors = list(dict.fromkeys(errors))
    with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
        for body in sorted(bodies):
            f.seek(0)
            f.truncate()
            f.write(body + "\n")
            f.flush()
            r = subprocess.run(["bash", "-n", f.name], capture_output=True)
            if r.returncode != 0:
                errors.append("step body fails bash -n: "
                              + r.stderr.decode().strip()
                              + f"\n  body: {body[:80]}…")
    return errors
