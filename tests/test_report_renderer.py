from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "ai-tell-scan"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from ats_core import (  # noqa: E402
    candidate_set_digest,
    finalize,
    review_template,
    scan,
    validate_final_report,
)
from render_report import render, report_key  # noqa: E402


def positive_report() -> dict[str, object]:
    candidate = scan(SKILL / "evals" / "projects" / "react-01")
    review = review_template(candidate, reviewer="renderer-test")
    for decision in review["decisions"]:
        decision["disposition"] = "confirmed"
        decision["rationale"] = (
            "The full visible fixture context confirms this composite treatment."
        )
    report = finalize(candidate, review)
    report["repository"] = {"source": "https://github.com/acme/interface"}
    report["generatedAt"] = "2026-07-17T03:30:45Z"
    return report


class ReportRendererTests(unittest.TestCase):
    def test_repository_entry_point_generates_hosted_candidate_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "candidate.ats-1.json"
            review_path = root / "review.ats-review-1.json"
            command = [
                sys.executable,
                str(ROOT / "bin" / "ats-scan.py"),
                str(SKILL / "evals" / "projects" / "react-01"),
                "--repository-url",
                "https://github.com/acme/interface.git",
                "--generated-at",
                "2026-07-17T03:30:45+00:00",
                "--output",
                str(report_path),
                "--review-template",
                str(review_path),
            ]

            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            review = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual(
                report["repository"]["source"],
                "https://github.com/acme/interface",
            )
            self.assertEqual(report["generatedAt"], "2026-07-17T03:30:45Z")
            self.assertEqual(report["target"]["targetId"], "acme/interface")
            self.assertEqual(review["candidateSetDigest"], report["candidateSetDigest"])

            repeated = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(repeated.returncode, 2)
            self.assertIn("overwrite existing", repeated.stderr)

    def test_checked_example_is_valid_and_reproducible(self) -> None:
        report = json.loads(
            (ROOT / "examples" / "first-tree-web" / "ats-1.json").read_text(
                encoding="utf-8"
            )
        )
        validate_final_report(report)
        key = report_key(report)
        expected = (ROOT / "examples" / "first-tree-web" / "report.html").read_text(
            encoding="utf-8"
        )
        self.assertEqual(render(report, key), expected)

    def test_report_key_is_content_bound_and_ignores_subday_time(self) -> None:
        report = positive_report()
        original = report_key(report)

        same_day = copy.deepcopy(report)
        same_day["generatedAt"] = "2026-07-17T20:59:59Z"
        self.assertEqual(report_key(same_day), original)

        changed = copy.deepcopy(report)
        changed["target"]["label"] = "changed-interface"
        self.assertNotEqual(report_key(changed), original)

    def test_renderer_escapes_every_report_controlled_sink(self) -> None:
        report = positive_report()
        payload = '</style><script>alert("x")</script>'
        candidate = report["candidates"][0]
        candidate["title"] = payload
        candidate["evidence"][0]["excerpt"] = payload
        report["candidateSetDigest"] = candidate_set_digest(report["candidates"])
        report["tells"] = [
            {key: value for key, value in candidate.items() if key != "disposition"}
        ]
        validate_final_report(report)
        rendered = render(report, report_key(report))
        self.assertNotIn(payload, rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;/style&gt;&lt;script&gt;", rendered)
        self.assertIn("Content-Security-Policy", rendered)

    def test_report_key_rejects_noncanonical_or_private_style_sources(self) -> None:
        for source in (
            "/tmp/repo",
            "https://gitlab.com/acme/interface",
            "https://github.com/acme/interface/tree/main",
            "https://github.com/acme/interface?private=true",
        ):
            report = positive_report()
            report["repository"]["source"] = source
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "exact https://github"):
                    report_key(report)

    def test_renderer_cli_is_create_only(self) -> None:
        report = positive_report()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            command = [
                sys.executable,
                str(SCRIPTS / "render_report.py"),
                str(report_path),
                "--out-dir",
                str(root),
            ]
            first = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            key = first.stdout.strip()
            self.assertTrue((root / f"{key}.html").is_file())

            second = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(second.returncode, 2)
            self.assertIn("overwrite existing", second.stderr)

    def test_public_schema_declares_hosted_metadata(self) -> None:
        schema = json.loads((ROOT / "schemas" / "ats-1.schema.json").read_text())
        self.assertIn("repository", schema["properties"])
        self.assertIn("generatedAt", schema["properties"])
        self.assertEqual(
            schema["$id"],
            "https://github.com/agent-team-foundation/ai-tell-scan/schemas/ats-1.schema.json",
        )


if __name__ == "__main__":
    unittest.main()
