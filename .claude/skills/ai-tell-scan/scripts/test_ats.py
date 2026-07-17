#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ats_core import (  # noqa: E402
    candidate_set_digest,
    finalize,
    read_sources,
    review_template,
    scan,
    validate_final_report,
    validate_source_root,
    write_json,
)
from evaluate import evaluate, validate_manifest  # noqa: E402


SKILL_ROOT = Path(__file__).resolve().parent.parent
PROJECTS = SKILL_ROOT / "evals" / "projects"


def reviewed(
    report: dict[str, object], disposition: str = "confirmed"
) -> dict[str, object]:
    review = review_template(report, reviewer="test-agent")
    decisions = review["decisions"]
    assert isinstance(decisions, list)
    for decision in decisions:
        assert isinstance(decision, dict)
        decision["disposition"] = disposition
        decision["rationale"] = (
            "Visible fixture context satisfies the complete composite rule."
        )
    return finalize(report, review)


class AiTellScanTests(unittest.TestCase):
    def test_bundled_30_project_gold_set_passes_precision_gate(self) -> None:
        report, passed = evaluate(SKILL_ROOT / "evals" / "gold-set.json")
        self.assertTrue(passed)
        self.assertEqual(report["summary"]["projectCount"], 30)
        self.assertEqual(report["summary"]["candidateTp"], 23)
        self.assertGreaterEqual(report["summary"]["candidatePrecision"], 0.9)
        self.assertGreaterEqual(report["summary"]["confirmedPrecision"], 0.9)
        self.assertEqual(report["summary"]["fp"], 0)
        self.assertEqual(report["summary"]["fn"], 0)
        self.assertEqual(report["summary"]["reviewProblemCount"], 0)
        self.assertEqual(report["summary"]["reviewDecisionCount"], 23)
        self.assertEqual(report["summary"]["reviewRejectedCount"], 3)
        self.assertLess(report["summary"]["alwaysConfirmPrecision"], 0.9)

    def test_gold_manifest_rejects_escaping_or_duplicate_paths(self) -> None:
        manifest_path = SKILL_ROOT / "evals" / "gold-set.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["projects"][0]["path"] = "../projects/react-01"
        with self.assertRaisesRegex(ValueError, "inside the corpus"):
            validate_manifest(manifest, manifest_path)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["projects"][1]["path"] = manifest["projects"][0]["path"]
        with self.assertRaisesRegex(ValueError, "duplicate path"):
            validate_manifest(manifest, manifest_path)

        case_alias = "PROJECTS/react-01"
        alias_root = manifest_path.parent / case_alias
        try:
            same_directory = alias_root.is_dir() and os.path.samefile(
                alias_root, manifest_path.parent / "projects" / "react-01"
            )
        except OSError:
            same_directory = False
        if same_directory:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["projects"][1]["path"] = case_alias
            with self.assertRaisesRegex(ValueError, "duplicate directory"):
                validate_manifest(manifest, manifest_path)

    def test_positive_scan_has_real_source_line_and_requires_review(self) -> None:
        report = scan(PROJECTS / "react-01")
        self.assertEqual(report["scan"]["status"], "needs-review")
        candidate = report["candidates"][0]
        source = (
            (PROJECTS / "react-01" / candidate["file"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertIn('<h1 className="heroTitle">', source[candidate["line"] - 1])
        css_evidence = [
            item for item in candidate["evidence"] if item["file"] == "src/hero.css"
        ]
        self.assertGreaterEqual(len(css_evidence), 3)
        css_lines = (
            (PROJECTS / "react-01" / "src" / "hero.css")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        for item in css_evidence:
            self.assertEqual(item["excerpt"], css_lines[item["line"] - 1].strip())
        self.assertEqual(report["tells"], [])

    def test_completed_report_passes_executable_validation(self) -> None:
        validate_final_report(reviewed(scan(PROJECTS / "react-01")))

    def test_executable_validation_rejects_malformed_candidate_core_and_evidence(self) -> None:
        valid = reviewed(scan(PROJECTS / "react-01"))
        mutations = {
            "rule id type": lambda candidate: candidate.update({"ruleId": 42}),
            "null title": lambda candidate: candidate.update({"title": None}),
            "unknown severity": lambda candidate: candidate.update({"severity": "critical"}),
            "boolean confidence": lambda candidate: candidate.update({"confidence": True}),
            "boolean line": lambda candidate: candidate.update({"line": True}),
            "empty evidence record": lambda candidate: candidate["evidence"].__setitem__(0, {}),
        }

        for label, mutate in mutations.items():
            with self.subTest(label=label):
                report = json.loads(json.dumps(valid))
                candidate = report["candidates"][0]
                mutate(candidate)
                with self.assertRaisesRegex(ValueError, "candidate|evidence"):
                    validate_final_report(report)

    def test_executable_validation_rejects_malformed_required_envelope(self) -> None:
        valid = reviewed(scan(PROJECTS / "react-01"))
        mutations = {
            "missing target label": lambda report: report["target"].pop("label"),
            "missing source digest": lambda report: report["target"].pop(
                "sourceDigest"
            ),
            "invalid source digest": lambda report: report["target"].update(
                {"sourceDigest": "not-a-sha256"}
            ),
            "duplicate frameworks": lambda report: report["target"].update(
                {"frameworks": ["react", "react"]}
            ),
            "missing scan reason": lambda report: report["scan"].pop("reason"),
            "boolean scan counter": lambda report: report["scan"].update(
                {"filesExamined": True}
            ),
            "negative scan counter": lambda report: report["scan"].update(
                {"uiFilesExamined": -1}
            ),
            "missing scan counter": lambda report: report["scan"].pop(
                "rulesEvaluated"
            ),
            "missing review policy": lambda report: report["review"].pop("policy"),
            "empty reviewer": lambda report: report["review"].update(
                {"reviewer": ""}
            ),
            "boolean summary counter": lambda report: report["summary"].update(
                {"candidateCount": True}
            ),
            "incomplete rescan": lambda report: report.update(
                {
                    "rescan": {
                        "baselineSourceDigest": None,
                        "resolved": [],
                        "persisted": [],
                    }
                }
            ),
        }

        for label, mutate in mutations.items():
            with self.subTest(label=label):
                report = json.loads(json.dumps(valid))
                mutate(report)
                with self.assertRaisesRegex(
                    ValueError, "target|framework|scan|review|summary|rescan"
                ):
                    validate_final_report(report)

    def test_source_reader_fails_closed_at_aggregate_byte_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"react": "19.0.0"}}),
                encoding="utf-8",
            )
            (root / "App.tsx").write_text(
                "export function App() { return <main>Hello</main>; }\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Source byte limit exceeded"):
                read_sources(root, max_total_bytes=16)

    def test_source_reader_fails_closed_at_aggregate_line_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "App.tsx").write_text("one\ntwo\nthree\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Source line limit exceeded"):
                read_sources(root, max_total_lines=2)

    def test_index_and_candidate_limits_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"react": "19.0.0"}}),
                encoding="utf-8",
            )
            (root / "App.tsx").write_text(
                "export function App() { return <main><span>A</span><span>B</span></main>; }\n",
                encoding="utf-8",
            )
            with patch("ats_core.MAX_INDEXED_ELEMENTS", 1):
                with self.assertRaisesRegex(ValueError, "UI element limit exceeded"):
                    scan(root)

            (root / "App.tsx").write_text(
                'import "./styles.css";\nexport function App() { return <main className="one">A</main>; }\n',
                encoding="utf-8",
            )
            (root / "styles.css").write_text(
                ".one { color: red; }\n.two { color: blue; }\n",
                encoding="utf-8",
            )
            with patch("ats_core.MAX_INDEXED_CSS_BLOCKS", 1):
                with self.assertRaisesRegex(ValueError, "CSS block limit exceeded"):
                    scan(root)

        with patch("ats_core.MAX_CANDIDATES", 0):
            with self.assertRaisesRegex(ValueError, "Candidate limit exceeded"):
                scan(PROJECTS / "react-01")

    def test_output_paths_are_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "artifact.json"
            output.write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "overwrite existing"):
                write_json({"ok": True}, output)

            target = root / "target.json"
            target.write_text("target", encoding="utf-8")
            link = root / "artifact-link.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks are unavailable on this platform")
            with self.assertRaisesRegex(ValueError, "overwrite existing"):
                write_json({"ok": True}, link)

    def test_scan_cli_attaches_canonical_hosted_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.json"
            review = Path(directory) / "review.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "scan.py"),
                    str(PROJECTS / "react-01"),
                    "--repository-url",
                    "https://github.com/Acme/interface.git",
                    "--generated-at",
                    "2026-07-17T11:30:45+08:00",
                    "--output",
                    str(output),
                    "--review-template",
                    str(review),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                report["repository"]["source"],
                "https://github.com/Acme/interface",
            )
            self.assertEqual(report["target"]["targetId"], "Acme/interface")
            self.assertEqual(report["generatedAt"], "2026-07-17T03:30:45Z")

    def test_finalize_requires_complete_digest_bound_review(self) -> None:
        report = scan(PROJECTS / "react-13")
        review = review_template(report)
        review["candidateSetDigest"] = "stale"
        with self.assertRaisesRegex(ValueError, "does not match"):
            finalize(report, review)

        review = review_template(report)
        decisions = review["decisions"]
        assert isinstance(decisions, list)
        decisions.pop()
        first = decisions[0]
        assert isinstance(first, dict)
        first["disposition"] = "confirmed"
        first["rationale"] = (
            "The full component context confirms this repeated composition."
        )
        with self.assertRaisesRegex(ValueError, "missing decisions"):
            finalize(report, review)

    def test_finalize_reports_confirmed_tells_and_rejections(self) -> None:
        report = scan(PROJECTS / "react-13")
        review = review_template(report)
        decisions = review["decisions"]
        assert isinstance(decisions, list)
        for index, decision in enumerate(decisions):
            assert isinstance(decision, dict)
            decision["disposition"] = "confirmed" if index == 0 else "rejected"
            decision["rationale"] = (
                "Visible component context supports this decision without inferring authorship."
            )
        result = finalize(report, review)
        self.assertEqual(result["scan"]["status"], "completed")
        self.assertEqual(result["summary"]["confirmedCount"], 1)
        self.assertEqual(result["summary"]["rejectedCount"], 1)
        self.assertEqual(len(result["tells"]), 1)

    def test_review_is_bound_to_the_source_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "same-project"
            shutil.copytree(PROJECTS / "react-01", root)
            original = scan(root)
            stale_review = review_template(original)
            decisions = stale_review["decisions"]
            assert isinstance(decisions, list)
            decision = decisions[0]
            assert isinstance(decision, dict)
            decision["disposition"] = "confirmed"
            decision["rationale"] = (
                "The original page context supports the complete visible composite."
            )
            app = root / "src" / "App.tsx"
            app.write_text(
                app.read_text(encoding="utf-8")
                + "\n// Product-specific brand context.\n",
                encoding="utf-8",
            )
            fresh = scan(root)
            self.assertEqual(
                fresh["candidateSetDigest"], original["candidateSetDigest"]
            )
            with self.assertRaisesRegex(ValueError, "source digest"):
                finalize(fresh, stale_review)

    def test_review_is_bound_to_tool_name(self) -> None:
        report = scan(PROJECTS / "react-01")
        review = review_template(report)
        review["toolName"] = "other-scanner"
        with self.assertRaisesRegex(ValueError, "tool name"):
            finalize(report, review)

    def test_source_root_binding_includes_package_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "same-project"
            shutil.copytree(PROJECTS / "react-01", root)
            report = scan(root)
            (root / "package.json").write_text(
                json.dumps(
                    {"name": "different-project", "dependencies": {"preact": "10.0.0"}}
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "no longer matches"):
                validate_source_root(report, root)

    def test_tampered_candidate_report_is_rejected(self) -> None:
        report = scan(PROJECTS / "react-01")
        review = review_template(report)
        decisions = review["decisions"]
        assert isinstance(decisions, list)
        decision = decisions[0]
        assert isinstance(decision, dict)
        decision["disposition"] = "confirmed"
        decision["rationale"] = (
            "The visible hero context confirms the entire composite signal."
        )
        report["candidates"][0]["line"] = 999
        with self.assertRaisesRegex(ValueError, "contents do not match"):
            finalize(report, review)

    def test_output_inside_target_is_refused(self) -> None:
        root = PROJECTS / "react-01"
        with self.assertRaisesRegex(ValueError, "inside the repository"):
            write_json({"ok": True}, root / "report.json", forbidden_root=root)

    def test_output_guard_handles_case_variant_filesystem_alias(self) -> None:
        root = (PROJECTS / "react-01").resolve()
        case_variant = Path(str(root).replace("/Users/", "/users/", 1))
        try:
            same_directory = case_variant.is_dir() and os.path.samefile(
                case_variant, root
            )
        except OSError:
            same_directory = False
        if not same_directory:
            self.skipTest("Filesystem is case-sensitive or has no case-variant alias.")
        with self.assertRaisesRegex(ValueError, "inside the repository"):
            write_json(
                {"ok": True},
                case_variant / "ai-tell-scan-case-guard.json",
                forbidden_root=root,
            )

    def test_scan_cli_rejects_colliding_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "same.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parent / "scan.py"),
                    str(PROJECTS / "react-01"),
                    "--output",
                    str(output),
                    "--review-template",
                    str(output),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("distinct output paths", result.stderr)
            self.assertFalse(output.exists())

    def test_finalize_cli_refuses_output_inside_target(self) -> None:
        root = PROJECTS / "react-01"
        report = scan(root)
        review = review_template(report)
        decisions = review["decisions"]
        assert isinstance(decisions, list)
        decision = decisions[0]
        assert isinstance(decision, dict)
        decision["disposition"] = "confirmed"
        decision["rationale"] = (
            "The visible fixture context confirms the complete composite."
        )
        with tempfile.TemporaryDirectory() as directory:
            candidate_path = Path(directory) / "candidate.json"
            review_path = Path(directory) / "review.json"
            candidate_path.write_text(json.dumps(report), encoding="utf-8")
            review_path.write_text(json.dumps(review), encoding="utf-8")
            forbidden = root / "ai-tell-scan-report.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parent / "finalize.py"),
                    str(candidate_path),
                    str(review_path),
                    "--target",
                    str(root),
                    "--output",
                    str(forbidden),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("inside the repository", result.stderr)
            self.assertFalse(forbidden.exists())

    def test_react_package_without_ui_is_not_applicable(self) -> None:
        report = scan(PROJECTS / "next-26")
        self.assertEqual(report["scan"]["status"], "not-applicable")
        self.assertEqual(report["summary"]["candidateCount"], 0)

    def test_non_react_repository_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"fastify": "5.0.0"}}), encoding="utf-8"
            )
            (root / "server.ts").write_text(
                "export const ok = true;\n", encoding="utf-8"
            )
            report = scan(root)
        self.assertEqual(report["scan"]["status"], "unsupported")
        self.assertEqual(report["candidates"], [])
        self.assertNotIn('"score":', json.dumps(report).lower())

    def test_plain_html_and_preact_do_not_emit_react_candidates(self) -> None:
        for dependency, filename in (("fastify", "index.html"), ("preact", "Hero.tsx")):
            with (
                self.subTest(dependency=dependency),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                (root / "package.json").write_text(
                    json.dumps({"dependencies": {dependency: "1.0.0"}}),
                    encoding="utf-8",
                )
                (root / filename).write_text(
                    '<h1 className="text-7xl bg-gradient-to-r from-indigo-500 via-violet-500 to-pink-500 bg-clip-text text-transparent">Hello</h1>\n',
                    encoding="utf-8",
                )
                report = scan(root)
            self.assertEqual(report["scan"]["status"], "unsupported")
            self.assertEqual(report["candidates"], [])

    def test_fixture_package_does_not_enable_framework_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"fastify": "5.0.0"}}), encoding="utf-8"
            )
            (root / "App.tsx").write_text(
                'export const App = () => <h1 className="text-7xl bg-gradient-to-r from-indigo-500 via-violet-500 to-pink-500 bg-clip-text text-transparent">Hello</h1>;\n',
                encoding="utf-8",
            )
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "package.json").write_text(
                json.dumps({"dependencies": {"react": "19.0.0"}}), encoding="utf-8"
            )
            report = scan(root)
        self.assertEqual(report["scan"]["status"], "unsupported")
        self.assertEqual(report["candidates"], [])

    def test_react_monorepo_package_does_not_enable_preact_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"fastify": "5.0.0"}}), encoding="utf-8"
            )
            react_package = root / "apps" / "react-shell"
            react_package.mkdir(parents=True)
            (react_package / "package.json").write_text(
                json.dumps({"dependencies": {"react": "19.0.0"}}), encoding="utf-8"
            )
            preact_package = root / "apps" / "preact-app"
            preact_package.mkdir(parents=True)
            (preact_package / "package.json").write_text(
                json.dumps({"dependencies": {"preact": "10.0.0"}}), encoding="utf-8"
            )
            (preact_package / "Hero.tsx").write_text(
                'export const Hero = () => <h1 className="text-7xl bg-gradient-to-r from-indigo-500 via-violet-500 to-pink-500 bg-clip-text text-transparent">Hello</h1>;\n',
                encoding="utf-8",
            )
            report = scan(root)
        self.assertEqual(report["target"]["frameworks"], ["react"])
        self.assertEqual(report["scan"]["status"], "not-applicable")
        self.assertEqual(report["scan"]["uiFilesExamined"], 0)
        self.assertEqual(report["candidates"], [])

    def test_common_test_directories_are_excluded(self) -> None:
        for test_directory in (
            "__tests__",
            "cypress",
            "e2e",
            "playwright",
            "spec",
            "specs",
            "test",
            "tests",
        ):
            with (
                self.subTest(test_directory=test_directory),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                (root / "package.json").write_text(
                    json.dumps({"dependencies": {"react": "19.0.0"}}),
                    encoding="utf-8",
                )
                tests = root / test_directory
                tests.mkdir()
                (tests / "Hero.tsx").write_text(
                    'export const Hero = () => <h1 className="text-7xl bg-gradient-to-r from-indigo-500 via-violet-500 to-pink-500 bg-clip-text text-transparent">Test</h1>;\n',
                    encoding="utf-8",
                )
                report = scan(root)
            self.assertEqual(report["scan"]["status"], "not-applicable")
            self.assertEqual(report["candidates"], [])

    def test_rescan_comparison_marks_removed_rule_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "same-project"
            shutil.copytree(PROJECTS / "react-13", root)
            baseline = reviewed(scan(root))
            app = root / "src" / "App.tsx"
            text = app.read_text(encoding="utf-8")
            for color in ("blue", "violet", "orange"):
                text = text.replace(
                    f"border-{color}-200 bg-{color}-50 p-6 text-{color}-900",
                    "border-slate-200 bg-white p-6 text-slate-900",
                )
            app.write_text(text, encoding="utf-8")
            current_report = scan(root)
            review = review_template(current_report)
            decisions = review["decisions"]
            assert isinstance(decisions, list)
            for decision in decisions:
                assert isinstance(decision, dict)
                decision["disposition"] = "confirmed"
                decision["rationale"] = (
                    "The visible feature grid confirms this composite signal."
                )
            compared = finalize(current_report, review, baseline=baseline)
        resolved_rules = {item["ruleId"] for item in compared["rescan"]["resolved"]}
        self.assertEqual(resolved_rules, {"ats.multicolor-card-wash"})
        self.assertEqual(
            {item["ruleId"] for item in compared["rescan"]["persisted"]},
            {"ats.icon-card-triptych"},
        )

    def test_empty_rescan_can_resolve_every_baseline_tell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "same-project"
            shutil.copytree(PROJECTS / "react-01", root)
            baseline = reviewed(scan(root))
            (root / "src" / "hero.css").write_text(
                ".heroTitle { color: #111827; font-size: 4rem; font-weight: 700; }\n",
                encoding="utf-8",
            )
            clean = scan(root)
            result = finalize(clean, review_template(clean), baseline=baseline)
        self.assertEqual(result["review"]["state"], "not-required")
        self.assertEqual(
            {item["ruleId"] for item in result["rescan"]["resolved"]},
            {"ats.gradient-display-heading"},
        )

    def test_rescan_rejects_unrelated_or_unfinalized_baseline(self) -> None:
        baseline = reviewed(scan(PROJECTS / "react-01"))
        current = scan(PROJECTS / "next-19")
        with self.assertRaisesRegex(ValueError, "targetId"):
            finalize(current, review_template(current), baseline=baseline)

        pending = scan(PROJECTS / "react-01")
        finalized = reviewed(scan(PROJECTS / "react-01"))
        current_report = scan(PROJECTS / "react-01")
        current_review = review_template(current_report)
        current_decisions = current_review["decisions"]
        assert isinstance(current_decisions, list)
        current_decision = current_decisions[0]
        assert isinstance(current_decision, dict)
        current_decision["disposition"] = "confirmed"
        current_decision["rationale"] = (
            "The visible page context confirms the complete composite signal."
        )
        with self.assertRaisesRegex(ValueError, "finalized"):
            finalize(current_report, current_review, baseline=pending)
        self.assertEqual(finalized["review"]["state"], "complete")

    def test_hosted_rescan_requires_the_same_repository_source(self) -> None:
        baseline_candidate = scan(PROJECTS / "react-01", target_id="shared-target")
        baseline_candidate["repository"] = {"source": "https://github.com/acme/one"}
        baseline_candidate["generatedAt"] = "2026-07-17T03:30:45Z"
        baseline = reviewed(baseline_candidate)

        current = scan(PROJECTS / "react-13", target_id="shared-target")
        current["repository"] = {"source": "https://github.com/acme/two"}
        current["generatedAt"] = "2026-07-17T04:30:45Z"
        review = review_template(current)
        for decision in review["decisions"]:
            decision["disposition"] = "confirmed"
            decision["rationale"] = (
                "The visible fixture context satisfies the complete composite rule."
            )

        with self.assertRaisesRegex(ValueError, "repository.source"):
            finalize(current, review, baseline=baseline)

        current.pop("repository")
        current.pop("generatedAt")
        with self.assertRaisesRegex(ValueError, "repository.source"):
            finalize(current, review, baseline=baseline)

    def test_rescan_rejects_internally_inconsistent_baseline(self) -> None:
        baseline = reviewed(scan(PROJECTS / "react-01"))
        baseline["summary"]["confirmedCount"] = 0
        current_report = scan(PROJECTS / "react-01")
        current_review = review_template(current_report)
        decisions = current_review["decisions"]
        assert isinstance(decisions, list)
        decision = decisions[0]
        assert isinstance(decision, dict)
        decision["disposition"] = "confirmed"
        decision["rationale"] = (
            "The visible page context confirms the complete composite signal."
        )
        with self.assertRaisesRegex(ValueError, "internally inconsistent"):
            finalize(current_report, current_review, baseline=baseline)

    def test_rescan_compares_all_confirmed_candidates_not_only_top_three(self) -> None:
        candidate_report = scan(PROJECTS / "react-13")
        candidates = candidate_report["candidates"]
        assert isinstance(candidates, list)
        first_clone = json.loads(json.dumps(candidates[0]))
        first_clone.update(
            {
                "candidateId": "ats-0000000000000001",
                "ruleId": "ats.gradient-display-heading",
                "file": "src/Brand.tsx",
            }
        )
        second_clone = json.loads(json.dumps(candidates[1]))
        second_clone.update(
            {
                "candidateId": "ats-0000000000000002",
                "ruleId": "ats.spring-hover-everywhere",
                "file": "src/Motion.tsx",
            }
        )
        candidates.extend([first_clone, second_clone])
        candidate_report["summary"]["candidateCount"] = 4
        candidate_report["candidateSetDigest"] = candidate_set_digest(candidates)
        baseline = reviewed(candidate_report)
        self.assertEqual(baseline["summary"]["confirmedCount"], 4)
        self.assertEqual(len(baseline["tells"]), 3)
        self.assertEqual(baseline["summary"]["suppressedConfirmedCount"], 1)

        current_report = json.loads(json.dumps(candidate_report))
        removed = current_report["candidates"].pop(0)
        current_report["summary"]["candidateCount"] = 3
        current_report["candidateSetDigest"] = candidate_set_digest(
            current_report["candidates"]
        )
        review = review_template(current_report)
        for decision in review["decisions"]:
            decision["disposition"] = "confirmed"
            decision["rationale"] = (
                "The visible fixture context satisfies the complete composite rule."
            )
        compared = finalize(current_report, review, baseline=baseline)
        self.assertEqual(compared["rescan"]["introduced"], [])
        self.assertEqual(len(compared["rescan"]["persisted"]), 3)
        self.assertEqual(
            {(item["ruleId"], item["file"]) for item in compared["rescan"]["resolved"]},
            {(removed["ruleId"], removed["file"])},
        )

    def test_css_is_joined_only_from_an_explicit_local_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"react": "19.0.0"}}), encoding="utf-8"
            )
            source = root / "src"
            source.mkdir()
            (source / "App.tsx").write_text(
                'import "./styles.css";\nexport function App() { return <h1 className="heroTitle">Hello</h1>; }\n',
                encoding="utf-8",
            )
            (source / "styles.css").write_text(
                ".heroTitle { font-size: 4rem; background: linear-gradient(90deg, indigo, violet); background-clip: text; color: transparent; }\n",
                encoding="utf-8",
            )
            positive = scan(root)
            self.assertEqual(
                {item["ruleId"] for item in positive["candidates"]},
                {"ats.gradient-display-heading"},
            )

            (source / "App.tsx").write_text(
                'export function App() { return <h1 className="heroTitle">Hello</h1>; }\n',
                encoding="utf-8",
            )
            negative = scan(root)
            self.assertEqual(negative["candidates"], [])

            (source / "App.tsx").write_text(
                'const cssDocumentation = "styles.css";\nexport function App() { return <h1 className="heroTitle">Hello</h1>; }\n',
                encoding="utf-8",
            )
            quoted_reference = scan(root)
            self.assertEqual(quoted_reference["candidates"], [])

    def test_nearby_glass_nav_evidence_points_to_child_primitives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"react": "19.0.0"}}), encoding="utf-8"
            )
            (root / "App.tsx").write_text(
                """export function App() {
  return (
    <nav className=\"fixed top-0\">
      <div className=\"rounded-full border bg-white/60 shadow backdrop-blur-xl\">
        <a href=\"/join\">Join</a>
      </div>
    </nav>
  );
}
""",
                encoding="utf-8",
            )
            report = scan(root)
        candidate = next(
            item
            for item in report["candidates"]
            if item["ruleId"] == "ats.glass-floating-nav"
        )
        nearby_kinds = {
            "backdrop-blur",
            "capsule-surface",
            "framed-surface",
            "translucent-surface",
        }
        nearby_evidence = [
            item for item in candidate["evidence"] if item["kind"] in nearby_kinds
        ]
        self.assertEqual({item["kind"] for item in nearby_evidence}, nearby_kinds)
        self.assertEqual({item["line"] for item in nearby_evidence}, {4})
        self.assertTrue(
            all("rounded-full" in item["excerpt"] for item in nearby_evidence)
        )

    def test_metric_evidence_resolves_whitespace_to_metric_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"react": "19.0.0"}}), encoding="utf-8"
            )
            (root / "App.tsx").write_text(
                """export function App() {
  return <section className=\"grid grid-cols-3\">
    <strong>48 k+</strong>
    <strong>97 %</strong>
    <strong>6 x</strong>
  </section>;
}
""",
                encoding="utf-8",
            )
            report = scan(root)
        candidate = next(
            item
            for item in report["candidates"]
            if item["ruleId"] == "ats.round-metric-proof-row"
        )
        metric_evidence = [
            item for item in candidate["evidence"] if item["kind"] == "round-metric"
        ]
        self.assertEqual(len(metric_evidence), 3)
        self.assertEqual({item["line"] for item in metric_evidence}, {3, 4, 5})
        self.assertTrue(all("<strong>" in item["excerpt"] for item in metric_evidence))


if __name__ == "__main__":
    unittest.main()
