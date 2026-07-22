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
        """Called by JINJA'S parser when it hits `{% step %}` at template
        compile time (not at render time).

        Input (template source, say line 27 of install-router.md.j2):

            {% step id="install-router", tags="dry-run=skip" %}
            helm install ${GUIDE_NAME} ...
            {% endstep %}

        Output: a Jinja CallBlock node equivalent to calling
        ``_step(context, src="install-router.md.j2:27",
        id="install-router", tags="dry-run=skip")`` with the body attached
        — i.e. provenance is baked in as a constant while parsing, so
        rendering needs no line tracking at all.
        """
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
        """Called at RENDER time, once per surviving {% step %} block.

        Input: the parse-time constants above plus ``caller()``, which
        yields the rendered body ("helm install ${GUIDE_NAME} ...").

        Side effect — appends one record to the collector that render()
        passed in as the ``_steps`` context variable:

            {"id": "install-router", "src": "install-router.md.j2:27",
             "tags": {"dry-run": "skip"}, "group": None,
             "run": "helm install ${GUIDE_NAME} ...", "hidden": False}

        Returns the markdown readers see — "```bash\\n<body>\\n```" — or ""
        when hide=true (the step exists in every plan but not in any doc).
        """
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
        """The generated step that carries the picked cell into the shell.

        Input:  {"infra_provider": "gke", ..., "accelerator": "tpu/v6", ...}
        Output: '# Your configuration (from the picker / --set flags):\\n'
                'export INFRA_PROVIDER="gke"\\n...\\n'
                'export ACCELERATOR="tpu/v6"\\n...\\n'
                '# Guide constants:\\n'
                'export GUIDE_NAME="optimized-baseline"\\n...'

        This is the ONLY place dimension values become shell state — every
        authored step body stays static, consuming ${VARS}.
        """
        lines = ["# Your configuration (from the picker / --set flags):"]
        lines += [f'export {d.upper()}="{cell[d]}"' for d in self.matrix.order]
        if self.env:
            lines.append("# Guide constants:")
            lines += [f'export {k}="{v}"' for k, v in self.env.items()]
        return "\n".join(lines)

    def render(self, cell):
        """Render the template for one cell — the single source of BOTH
        reader output and executable plan.

        Input:  a complete cell, e.g. {"infra_provider": "base", ...,
                "router_mode": "gateway", "gateway_provider": "istio", ...}

        Output: (markdown, collected)
          markdown   the full guide for exactly that configuration —
                     "# Optimized Baseline\\n\\n## Overview\\n..." with only
                     the surviving branches and ```bash fences
          collected  the ordered step records appended by {% step %} and
                     configure_step() during that same render (see
                     StepExtension._step for the record shape) — the plan
                     IS the document order for this cell
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
        """CLI --set flags -> a complete, validated cell.

        Input:  ["accelerator=tpu/v6", "infra_provider=gke"]   (or None)
        Output: the default cell overridden by the flags, e.g.
                {"infra_provider": "gke", "router_mode": "standalone",
                 "gateway_provider": "none", "accelerator": "tpu/v6", ...}

        Exits with an error for unknown dimensions/values, or when the
        resulting combination is not supported under the rules (e.g.
        --set infra_provider=base --set accelerator=tpu/v6).
        """
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
        """One cell's executable run: render, keep the recorded steps,
        drop the ones whose tags match `skips`.

        Input:  cell  = a supported cell (see parse_assignment)
                skips = [("ci", "skip"), ("dry-run", "skip")]  (or None)

        Output (formatted by plan.py / json.dumps, never executed here):

            {"guide": "optimized-baseline",
             "doc": "guides/optimized-baseline/guide.md.j2",
             "assignment": {...cell...},
             "steps": [{"id": "configure", "src": "<generated:configure>",
                        "meta": {}, "run": 'export ...'},
                       {"id": "install-router",
                        "src": "install-router.md.j2:27",
                        "meta": {"dry-run": "skip"}, "run": "helm ..."}]}

        A step is dropped when any (key, value) in `skips` matches its
        tags — so hidden dry-run stand-ins (e2e=skip) survive here and are
        only excluded from reader output.
        """
        _, collected = self.render(cell)
        steps = [{"id": s["id"], "src": s["src"], "meta": s["tags"], "run": s["run"]}
                 for s in collected
                 if not any(s["tags"].get(k) == v for k, v in (skips or []))]
        return {"guide": self.meta.get("name"), "doc": str(self.dir / "guide.md.j2"),
                "assignment": dict(cell), "steps": steps}
