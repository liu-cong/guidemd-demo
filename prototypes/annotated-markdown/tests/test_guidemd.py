"""Tests for guidemd.py — golden checks on the example guide plus property
tests over every supported combination, and unit tests (on synthetic guides
in tmp dirs) for each validation rule.

Stdlib-only (unittest); pytest also discovers these natively.

Run from the repo root:  python3 -m unittest discover -s tests -q
"""

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from guidemd import Guide, plan_bash, render_github  # noqa: E402

# Works in both layouts: guides/ (guidemd-demo) and example/ (prototype).
DOC = next(ROOT / d / "optimized-baseline" / "guide.template.md"
           for d in ("guides", "example")
           if (ROOT / d / "optimized-baseline" / "guide.template.md").exists())

# Commands that require (or mutate) a live cluster — none may survive into a
# dry-run plan, which must be runnable on every PR without cluster access.
CLUSTER_COMMANDS = ("kubectl apply", "kubectl delete", "kubectl wait",
                    "kubectl rollout", "kubectl run", "kubectl get",
                    "helm install", "helm upgrade", "helm uninstall")

DRY_RUN_SKIPS = [("ci", "skip"), ("dry-run", "skip")]
E2E_SKIPS = [("ci", "skip"), ("e2e", "skip")]

_GUIDE = None


def example_guide():
    global _GUIDE
    if _GUIDE is None:
        _GUIDE = Guide(DOC)
        assert not _GUIDE.errors, _GUIDE.errors
    return _GUIDE


class ExampleGuideTests(unittest.TestCase):
    """Golden + property tests on guides/optimized-baseline."""

    def setUp(self):
        self.g = example_guide()

    def test_example_has_no_warnings(self):
        self.assertEqual(self.g.warnings, [])

    def test_matrix_shape(self):
        self.assertEqual(len(self.g.matrix.supported), 96)
        self.assertEqual(len(self.g.matrix.ci), 8)
        for cell in self.g.matrix.ci:
            self.assertIn(cell, self.g.matrix.supported)

    def test_gateway_provider_rules(self):
        combos = {(c["infra_provider"], c["router_mode"], c["gateway_provider"])
                  for c in self.g.matrix.supported}
        self.assertNotIn(("base", "gateway", "gke"), combos)  # old incoherent mix
        self.assertIn(("base", "gateway", "istio"), combos)
        self.assertIn(("gke", "gateway", "gke"), combos)
        for _, mode, gp in combos:
            if mode == "standalone":
                self.assertEqual(gp, "none")

    def test_every_cell_renders_clean(self):
        for cell in self.g.matrix.supported:
            text = self.g.render_markdown(cell)
            self.assertNotIn("{{", text, f"unsubstituted placeholder in {cell}")
            self.assertEqual(text.count("```") % 2, 0, f"unbalanced fences in {cell}")

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
            plan = self.g.plan(cell, skips=DRY_RUN_SKIPS)
            for step in plan["steps"]:
                for cmd in CLUSTER_COMMANDS:
                    self.assertNotIn(
                        cmd, step["run"],
                        f"dry-run for {cell} touches the cluster ({step['src']})")

    def test_e2e_plan_contains_real_install_and_assertion(self):
        plan = self.g.plan(self.g.matrix.default_cell(), skips=E2E_SKIPS)
        joined = "\n".join(s["run"] for s in plan["steps"])
        self.assertIn("helm install", joined)
        self.assertIn("curl -fsS", joined)               # verification asserts
        self.assertIn("jq -e", joined)

    def test_plan_steps_carry_source_provenance(self):
        plan = self.g.plan(self.g.matrix.default_cell(), skips=E2E_SKIPS)
        for s in plan["steps"]:
            self.assertIn(".md:", s["src"] or "")
        self.assertTrue(any("common/install-router.md" in s["src"]
                            for s in plan["steps"]))

    def test_readonly_md_is_fresh_and_fully_substituted(self):
        committed = (DOC.parent / "readonly-guide.md").read_text()
        self.assertEqual(committed, render_github(DOC))
        self.assertNotIn("{{", committed)
        self.assertIn("<details>", committed)
        self.assertIn("badge.svg", committed)            # badges generated

    def test_hidden_steps_out_of_readers_in_plans(self):
        cell = self.g.matrix.default_cell()
        self.assertNotIn("helm template", self.g.render_markdown(cell))
        dry = self.g.plan(cell, skips=DRY_RUN_SKIPS)
        self.assertTrue(any("helm template" in s["run"] for s in dry["steps"]))
        committed = (DOC.parent / "readonly-guide.md").read_text()
        self.assertNotIn("helm template", committed)

    def test_import_params_forwarded_through_fragments(self):
        cell = dict(self.g.matrix.default_cell(),
                    router_mode="gateway", gateway_provider="istio")
        text = self.g.render_markdown(cell)
        self.assertIn("kubectl get gateway llm-d-inference-gateway", text)
        self.assertIn("gateway.class=istio", text)

    def test_coverage_check_passes(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "check_coverage.py"),
             str(ROOT / "tests/fixtures/upstream-optimized-baseline.md"),
             str(DOC),
             "--waivers", str(ROOT / "tests/fixtures/coverage-waivers.txt")],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


TWO_DIMS = """\
step_tags: [ci]
dimensions:
  a: { values: [x, y] }
  b: { values: [p, q] }
"""


class UnitGuideTests(unittest.TestCase):
    """Each validation rule, exercised on small synthetic guides."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def mkguide(self, body, front=""):
        doc = self.tmp / "g.md"
        doc.write_text((f"---\nguide:\n{textwrap.indent(front, '  ')}\n---\n"
                        if front else "") + textwrap.dedent(body))
        return doc

    def test_plain_markdown_is_a_valid_guide(self):
        g = Guide(self.mkguide("# Title\n\nProse only.\n\n```bash\nls\n```\n"))
        self.assertEqual(g.errors, [])                   # no steps yet: fences OK
        self.assertEqual(g.warnings, [])
        self.assertEqual(g.matrix.supported, [{}])       # zero dims = one variant

    def test_unmarked_bash_fence_fails_once_steps_exist(self):
        doc = self.mkguide(
            "<!-- step -->\n```bash\na\n```\n\n```bash\nb\n```\n", TWO_DIMS)
        errs = Guide(doc).errors
        self.assertTrue(any("without a <!-- step -->" in e and "g.md:" in e
                            for e in errs), errs)

    def test_undeclared_step_tag_key_fails(self):
        doc = self.mkguide("<!-- step dry-rn=skip -->\n```bash\na\n```\n", TWO_DIMS)
        self.assertTrue(any("'dry-rn'" in e for e in Guide(doc).errors))

    def test_step_meta_without_declaration_fails(self):
        doc = self.mkguide("<!-- step ci=skip -->\n```bash\na\n```\n",
                           "dimensions:\n  a: { values: [x] }\n")
        self.assertTrue(any("step_tags" in e for e in Guide(doc).errors))

    def test_when_group_gap_warns(self):
        body = """\
        <!-- when a=x -->
        p
        <!-- end -->
        <!-- when a=y b=p -->
        q
        <!-- end -->
        """
        g = Guide(self.mkguide(body, TWO_DIMS))
        self.assertTrue(any("no branch" in w and "a=y" in w
                            for w in g.warnings), g.warnings)  # (y,q) uncovered

    def test_independent_adjacent_pairs_do_not_warn(self):
        body = """\
        <!-- when a=x -->
        1
        <!-- end -->
        <!-- when a=y -->
        2
        <!-- end -->
        <!-- when b=p -->
        3
        <!-- end -->
        <!-- when b=q -->
        4
        <!-- end -->
        """
        self.assertEqual(Guide(self.mkguide(body, TWO_DIMS)).warnings, [])

    def test_dead_region_warns(self):
        front = TWO_DIMS + "rules:\n  - when:  { a: x }\n    allow: { b: [p] }\n"
        body = "<!-- when a=x b=q -->\ndead\n<!-- end -->\n"
        g = Guide(self.mkguide(body, front))
        self.assertTrue(any("dead content" in w for w in g.warnings), g.warnings)

    def test_error_provenance_points_into_fragment(self):
        (self.tmp / "frag.md").write_text("```bash\nnaked\n```\n")
        doc = self.mkguide(
            "<!-- step -->\n```bash\na\n```\n\n<!-- import frag.md -->\n", TWO_DIMS)
        errs = Guide(doc).errors
        self.assertTrue(any("frag.md:1" in e for e in errs), errs)

    def test_unresolved_import_param_fails(self):
        (self.tmp / "frag.md").write_text("uses {{ thing }}\n")
        doc = self.mkguide("<!-- import frag.md -->\n", TWO_DIMS)
        self.assertTrue(any("thing" in e for e in Guide(doc).errors))

    def test_badges_require_repo(self):
        doc = self.mkguide("<!-- badges -->\n", TWO_DIMS)
        self.assertTrue(any("repo" in e for e in Guide(doc).errors))

    def test_unsupported_assignment_rejected(self):
        front = TWO_DIMS + "rules:\n  - when:  { a: y }\n    allow: { b: [q] }\n"
        g = Guide(self.mkguide("hi\n", front))
        self.assertNotIn({"a": "y", "b": "p"}, g.matrix.supported)
        with self.assertRaises(SystemExit):
            g.parse_assignment(["a=y", "b=p"])

    def test_ci_row_must_be_complete_and_supported(self):
        front = TWO_DIMS + "ci:\n  - { a: x }\n"
        errs = Guide(self.mkguide("hi\n", front)).errors
        self.assertTrue(any("complete flattened assignment" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
