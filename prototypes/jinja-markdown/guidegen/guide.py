"""Core: load guide.yaml, render guide.md.j2 for one cell, collect steps.

The {% step %} tag is registered through Jinja's documented extension API —
Jinja's parser handles it and bakes the template file:line into every step
at parse time, so provenance needs no custom tracking. Rendering doubles as
plan extraction: each surviving {% step %} records itself, in document
order, into the collector passed through the render context.
"""

import re
import sys
from pathlib import Path

import jinja2
import yaml
from jinja2 import nodes
from jinja2.ext import Extension

from .matrix import Matrix

RE_TAGVAL = re.compile(r"([\w-]+)=(\S+)")


class StepExtension(Extension):
    """`{% step key=value, … %} body {% endstep %}` — an inline executable
    step: renders as a ```bash fence and is recorded for the plan."""

    tags = {"step"}

    def parse(self, parser):
        lineno = parser.stream.current.lineno
        next(parser.stream)
        src = f"{parser.name or 'guide.md.j2'}:{lineno}"
        kwargs = [nodes.Keyword("src", nodes.Const(src))]
        while parser.stream.current.type != "block_end":
            parser.stream.skip_if("comma")
            name = parser.stream.expect("name").value
            parser.stream.expect("assign")
            kwargs.append(nodes.Keyword(name, parser.parse_expression()))
        body = parser.parse_statements(("name:endstep",), drop_needle=True)
        call = self.call_method("_step", [nodes.ContextReference()], kwargs)
        return nodes.CallBlock(call, [], [], body).set_lineno(lineno)

    def _step(self, context, src, id=None, tags="", group=None, hide=False,
              caller=None):
        run = caller().strip("\n")
        steps = context.get("_steps")
        if steps is not None:
            steps.append({"id": id or src, "src": src,
                          "tags": dict(RE_TAGVAL.findall(tags)),
                          "group": group, "run": run, "hidden": bool(hide)})
        return "" if hide else f"```bash\n{run}\n```"


class Guide:
    def __init__(self, guide_dir):
        self.dir = Path(guide_dir)
        self.errors = []
        meta_path = self.dir / "guide.yaml"
        if not meta_path.is_file():
            sys.exit(f"{guide_dir}: no guide.yaml found")
        self.meta = yaml.safe_load(meta_path.read_text()) or {}
        self.matrix = Matrix(self.meta, self.errors)
        self.env = {str(k): str(v) for k, v in (self.meta.get("env") or {}).items()}
        self.step_tags = {str(t) for t in (self.meta.get("step_tags") or [])}
        self.common_dir = self.dir.parent.parent / "common"
        self.jinja = jinja2.Environment(
            loader=jinja2.FileSystemLoader([str(self.dir), str(self.common_dir)]),
            undefined=jinja2.StrictUndefined,
            extensions=[StepExtension],
            trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)

    def _configure_body(self, cell):
        lines = ["# Your configuration (from the picker / --set flags):"]
        lines += [f'export {d.upper()}="{cell[d]}"' for d in self.matrix.order]
        if self.env:
            lines.append("# Guide constants:")
            lines += [f'export {k}="{v}"' for k, v in self.env.items()]
        return "\n".join(lines)

    def render(self, cell):
        """Render the template for one cell.

        Returns (markdown, collected): collected is the ordered list of step
        records — the plan IS the document order for this cell.
        """
        collected = []

        def configure_step():
            body = self._configure_body(cell)
            collected.append({"id": "configure", "src": "<generated:configure>",
                              "tags": {}, "group": None, "run": body,
                              "hidden": False})
            return f"```bash\n{body}\n```"

        ctx = dict(cell)
        ctx.update(title=self.meta.get("title", self.meta.get("name", "")),
                   configure_step=configure_step, _steps=collected)
        try:
            md = self.jinja.get_template("guide.md.j2").render(**ctx)
        except jinja2.TemplateError as e:
            lineno = getattr(e, "lineno", None)
            name = getattr(e, "name", None) or "guide.md.j2"
            where = f"{name}:{lineno}" if lineno else name
            raise jinja2.TemplateError(f"{where}: {e}") from e
        md = re.sub(r"\n{3,}", "\n\n", md).strip("\n") + "\n"
        return md, collected

    def parse_assignment(self, sets):
        cell = self.matrix.default_cell()
        for item in sets or []:
            k, _, v = item.partition("=")
            if k not in self.matrix.dims or v not in self.matrix.values[k]:
                sys.exit(f"invalid --set {item!r} (dimensions: "
                         + ", ".join(f"{d}={self.matrix.values[d]}"
                                     for d in self.matrix.order) + ")")
            cell[k] = v
        if cell not in self.matrix.supported:
            sys.exit(f"assignment {cell} is not a supported combination under the rules")
        return cell

    def plan(self, cell, skips=None):
        _, collected = self.render(cell)
        steps = [{"id": s["id"], "src": s["src"], "meta": s["tags"], "run": s["run"]}
                 for s in collected
                 if not any(s["tags"].get(k) == v for k, v in (skips or []))]
        return {"guide": self.meta.get("name"), "doc": str(self.dir / "guide.md.j2"),
                "assignment": dict(cell), "steps": steps}
