"""Tests for guidegen.py — golden checks on the ported guide, property tests
over every supported combination, unit tests per validation rule, and a
cross-prototype parity suite against the annotated-markdown prototype.

Run from prototypes/jinja-markdown:  python3 -m unittest discover -s tests -q
"""

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from guidegen import Guide, alerts_to_admonitions, plan_bash, render_github  # noqa: E402

GUIDE_DIR = ROOT / "guides" / "optimized-baseline"

CLUSTER_COMMANDS = ("kubectl apply", "kubectl delete", "kubectl wait",
                    "kubectl rollout", "kubectl run", "kubectl get",
                    "helm install", "helm upgrade", "helm uninstall")
DRY_RUN_SKIPS = [("ci", "skip"), ("dry-run", "skip")]
E2E_SKIPS = [("ci", "skip"), ("e2e", "skip")]

_GUIDE = None


def guide():
    global _GUIDE
    if _GUIDE is None:
        _GUIDE = Guide(GUIDE_DIR)
        _GUIDE.validate_cells()
        assert not _GUIDE.errors, _GUIDE.errors
    return _GUIDE


class PortedGuideTests(unittest.TestCase):

    def setUp(self):
        self.g = guide()

    def test_no_warnings(self):
        self.assertEqual(self.g.warnings, [])

    def test_matrix_shape(self):
        self.assertEqual(len(self.g.matrix.supported), 96)
        self.assertEqual(len(self.g.matrix.ci), 8)

    def test_every_cell_renders_clean(self):
        for cell in self.g.matrix.supported:
            md, _ = self.g.render(cell)
            self.assertNotIn("{%", md, f"unrendered jinja in {cell}")
            self.assertEqual(md.count("```") % 2, 0, f"unbalanced fences in {cell}")

    def test_every_cell_plan_is_valid_bash(self):
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "plan.sh"
            for cell in self.g.matrix.supported:
                for skips in (DRY_RUN_SKIPS, E2E_SKIPS):
                    script.write_text(plan_bash(self.g.plan(cell, skips=skips)))
                    r = subprocess.run(["bash", "-n", str(script)],
                                       capture_output=True)
                    self.assertEqual(r.returncode, 0,
                                     f"{cell} {skips}: {r.stderr.decode()}")

    def test_dry_run_plans_need_no_cluster(self):
        for cell in self.g.matrix.supported:
            for step in self.g.plan(cell, skips=DRY_RUN_SKIPS)["steps"]:
                for cmd in CLUSTER_COMMANDS:
                    self.assertNotIn(cmd, step["run"],
                                     f"dry-run for {cell} touches the cluster "
                                     f"({step['src']})")

    def test_steps_carry_template_provenance(self):
        plan = self.g.plan(self.g.matrix.default_cell(), skips=E2E_SKIPS)
        srcs = [s["src"] for s in plan["steps"] if s["id"] != "configure"]
        self.assertTrue(all(".md.j2:" in s for s in srcs), srcs)
        self.assertTrue(any(s.startswith("install-router.md.j2:") for s in srcs))

    def test_optional_ids_present_where_declared(self):
        plan = self.g.plan(self.g.matrix.default_cell(), skips=E2E_SKIPS)
        ids = [s["id"] for s in plan["steps"]]
        self.assertIn("install-router", ids)
        self.assertIn("verify-request", ids)

    def test_configure_step_exports_dimensions_and_env(self):
        cell = dict(self.g.matrix.default_cell(),
                    router_mode="gateway", gateway_provider="istio")
        plan = self.g.plan(cell)
        conf = next(s for s in plan["steps"] if s["id"] == "configure")
        self.assertIn('export GATEWAY_PROVIDER="istio"', conf["run"])
        self.assertIn('export GUIDE_NAME="optimized-baseline"', conf["run"])
        joined = "\n".join(s["run"] for s in plan["steps"])
        self.assertIn("gateway.class=${GATEWAY_PROVIDER}", joined)

    def test_readonly_md_fresh(self):
        committed = (GUIDE_DIR / "readonly-guide.md").read_text()
        self.assertEqual(committed, render_github(self.g))
        self.assertIn("badge.svg", committed)

    def test_hidden_steps_out_of_docs_in_plans(self):
        cell = self.g.matrix.default_cell()
        md, _ = self.g.render(cell)
        self.assertNotIn("helm template", md)
        dry = self.g.plan(cell, skips=DRY_RUN_SKIPS)
        self.assertTrue(any("helm template" in s["run"] for s in dry["steps"]))

    def test_docusaurus_emit(self):
        out = GUIDE_DIR / "docusaurus"
        pages = list(out.glob("*.mdx"))
        self.assertEqual(len(pages), 96)
        index = (out / "index.mdx").read_text()
        self.assertNotIn("unlisted", index)          # default page is listed
        self.assertIn(":::note", index)              # alerts converted
        self.assertNotIn("> [!", index)
        self.assertIn("<VariantSwitcher", index)
        other = next(p for p in pages if p.name != "index.mdx").read_text()
        self.assertIn("unlisted: true", other)
        self.assertTrue((out / "_variants.json").exists())
        self.assertTrue((out / "_VariantSwitcher.jsx").exists())

    def test_alerts_to_admonitions(self):
        md = "> [!IMPORTANT]\n> stay alert\n> two lines\n\nafter\n"
        out = alerts_to_admonitions(md)
        self.assertIn(":::info\nstay alert\ntwo lines\n:::", out)


class CrossPrototypeParityTests(unittest.TestCase):
    """The two prototypes must describe the SAME guide: identical matrices
    and identical per-cell step counts for every plan flavor."""

    @classmethod
    def setUpClass(cls):
        am_root = ROOT.parent / "annotated-markdown"
        sys.path.insert(0, str(am_root))
        import guidemd
        cls.am = guidemd.Guide(
            am_root / "guides" / "optimized-baseline" / "guide.template.md")
        assert not cls.am.errors, cls.am.errors
        cls.jm = guide()

    def test_same_supported_matrix(self):
        self.assertEqual(self.am.matrix.supported, self.jm.matrix.supported)
        self.assertEqual(self.am.matrix.ci, self.jm.matrix.ci)

    def test_same_step_counts_everywhere(self):
        for cell in self.am.matrix.supported:
            for skips in (None, DRY_RUN_SKIPS, E2E_SKIPS):
                a = len(self.am.plan(cell, skips=skips)["steps"])
                j = len(self.jm.plan(cell, skips=skips)["steps"])
                self.assertEqual(a, j, f"{cell} skips={skips}")


TWO_DIMS = textwrap.dedent("""\
    name: t
    step_tags: [ci]
    dimensions:
      a: { values: [x, y] }
      b: { values: [p, q] }
""")


class UnitTests(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        base = Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        (base / "common").mkdir(parents=True)   # partial search dir
        self.gdir = base / "guides" / "g"
        self.gdir.mkdir(parents=True)

    def mkguide(self, template, yaml_text=TWO_DIMS):
        (self.gdir / "guide.yaml").write_text(yaml_text)
        (self.gdir / "guide.md.j2").write_text(textwrap.dedent(template))
        return Guide(self.gdir)

    def test_inline_step_collected_and_rendered(self):
        g = self.mkguide('{% step %}\nls -la\n{% endstep %}\n')
        md, collected = g.render(g.matrix.default_cell())
        self.assertIn("```bash\nls -la\n```", md)
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0]["src"], "guide.md.j2:1")

    def test_undeclared_tag_fails(self):
        g = self.mkguide('{% step tags="dry-rn=skip" %}\nls\n{% endstep %}\n')
        g.validate_cells()
        self.assertTrue(any("'dry-rn'" in e for e in g.errors), g.errors)

    def test_handwritten_bash_fence_fails(self):
        g = self.mkguide('```bash\nescaped\n```\n')
        g.validate_cells()
        self.assertTrue(any("escapes CI" in e for e in g.errors), g.errors)

    def test_console_fence_is_fine(self):
        g = self.mkguide('```console\ndisplay only\n```\n')
        g.validate_cells()
        self.assertEqual(g.errors, [])

    def test_group_must_partition(self):
        g = self.mkguide(textwrap.dedent("""\
            {% if a == "x" %}
            {% step group="g1" %}
            one
            {% endstep %}
            {% endif %}
        """))
        g.validate_cells()
        self.assertTrue(any("group 'g1'" in e and "nothing" in e
                            for e in g.errors), g.errors)

    def test_else_branch_partitions_cleanly(self):
        g = self.mkguide(textwrap.dedent("""\
            {% if a == "x" %}
            {% step group="g1" %}
            one
            {% endstep %}
            {% else %}
            {% step group="g1" %}
            two
            {% endstep %}
            {% endif %}
        """))
        g.validate_cells()
        self.assertEqual(g.errors, [])

    def test_duplicate_explicit_id_fails(self):
        g = self.mkguide(textwrap.dedent("""\
            {% step id="s" %}
            one
            {% endstep %}
            {% step id="s" %}
            two
            {% endstep %}
        """))
        g.validate_cells()
        self.assertTrue(any("step id 's'" in e for e in g.errors), g.errors)

    def test_typoed_variable_fails(self):
        g = self.mkguide('{{ acelerator }}\n')  # StrictUndefined
        g.validate_cells()
        self.assertTrue(any("acelerator" in e for e in g.errors), g.errors)

    def test_bad_bash_body_fails(self):
        g = self.mkguide('{% step %}\nif then fi (\n{% endstep %}\n')
        g.validate_cells()
        self.assertTrue(any("bash -n" in e for e in g.errors), g.errors)

    def test_unsupported_assignment_rejected(self):
        y = TWO_DIMS + "rules:\n  - when:  { a: y }\n    allow: { b: [q] }\n"
        g = self.mkguide("hi\n", yaml_text=y)
        with self.assertRaises(SystemExit):
            g.parse_assignment(["a=y", "b=p"])


if __name__ == "__main__":
    unittest.main()
