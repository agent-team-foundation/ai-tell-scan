from __future__ import annotations

import copy
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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
from checkout_public_repo import (  # noqa: E402
    BlobEntry,
    _git_blob_oid,
    _materialize_archive,
    select_entries,
)
from render_report import render, report_key  # noqa: E402
from publish_report import publish  # noqa: E402


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


def reviewed_zero_report() -> dict[str, object]:
    candidate = scan(SKILL / "evals" / "projects" / "react-01")
    review = review_template(candidate, reviewer="renderer-test")
    for decision in review["decisions"]:
        decision["disposition"] = "rejected"
        decision["rationale"] = "The visible fixture context does not confirm the tell."
    report = finalize(candidate, review)
    report["repository"] = {"source": "https://github.com/acme/interface"}
    report["generatedAt"] = "2026-07-17T03:30:45Z"
    return report


def suppressed_report() -> dict[str, object]:
    candidate = scan(SKILL / "evals" / "projects" / "react-01")
    original = candidate["candidates"][0]
    candidate["candidates"] = []
    for index in range(5):
        repeated = copy.deepcopy(original)
        repeated["candidateId"] = f"ats-{index + 1:016x}"
        repeated["line"] = int(original["line"]) + index
        candidate["candidates"].append(repeated)
    candidate["candidateSetDigest"] = candidate_set_digest(candidate["candidates"])
    candidate["summary"]["candidateCount"] = 5
    review = review_template(candidate, reviewer="renderer-test")
    for decision in review["decisions"]:
        decision["disposition"] = "confirmed"
        decision["rationale"] = (
            "The full visible fixture context confirms this composite treatment."
        )
    report = finalize(candidate, review)
    report["repository"] = {"source": "https://github.com/acme/interface"}
    report["generatedAt"] = "2026-07-17T03:30:45Z"
    validate_final_report(report)
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
        self.assertIn('class="skip-link"', rendered)
        self.assertIn('class="action-rail"', rendered)
        self.assertIn("Priority findings", rendered)
        self.assertIn("Read the evidence before the label", rendered)
        self.assertIn("Review with First Tree", rendered)
        self.assertIn('class="hero has-findings"', rendered)
        self.assertIn("Visible defaults confirmed", rendered)
        self.assertIn("after source-context review", rendered)
        self.assertIn('role="columnheader">Priority', rendered)
        self.assertIn("overflow-wrap:anywhere", rendered)
        self.assertNotIn("Share this report", rendered)

        clean = json.loads(
            (ROOT / "examples" / "first-tree-web" / "ats-1.json").read_text(
                encoding="utf-8"
            )
        )
        clean_rendered = render(clean, report_key(clean))
        self.assertIn('class="hero clean-result"', clean_rendered)
        self.assertIn("after deterministic source scan", clean_rendered)
        self.assertIn("No deterministic composite rule crossed", clean_rendered)
        self.assertIn("No source-context review was required", clean_rendered)
        self.assertIn("Keep visible defaults intentional", clean_rendered)
        self.assertNotIn("turn confirmed tells into scoped fixes", clean_rendered)
        self.assertIn('aria-colspan="5"', clean_rendered)

        reviewed_zero = reviewed_zero_report()
        reviewed_zero_rendered = render(reviewed_zero, report_key(reviewed_zero))
        self.assertIn("0 confirmed tells after source-context review", reviewed_zero_rendered)
        self.assertIn("Source-context review rejected every candidate", reviewed_zero_rendered)
        self.assertIn("All candidates were rejected", reviewed_zero_rendered)
        self.assertNotIn("turn confirmed tells into scoped fixes", reviewed_zero_rendered)

        suppressed = suppressed_report()
        suppressed_rendered = render(suppressed, report_key(suppressed))
        self.assertIn("5 confirmed tells", suppressed_rendered)
        self.assertIn("Showing 3 reported findings from 5 confirmed", suppressed_rendered)
        self.assertIn("--accent:#8f2f08", suppressed_rendered)
        self.assertIn("--acid:#3f5200", suppressed_rendered)

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

    def test_publisher_checks_identity_and_uploads_json_before_html(self) -> None:
        report = positive_report()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            completed = [
                subprocess.CompletedProcess(
                    ["gh"],
                    0,
                    json.dumps(
                        {
                            "visibility": "PUBLIC",
                            "url": "https://github.com/acme/interface",
                        }
                    ),
                    "",
                ),
                subprocess.CompletedProcess(["aws", "json"], 0, "", ""),
                subprocess.CompletedProcess(["aws", "html"], 0, "", ""),
            ]
            with patch("publish_report.subprocess.run", side_effect=completed) as run:
                url = publish(report_path, root)

            key = report_key(report)
            self.assertEqual(url, f"https://report.first-tree.ai/{key}.html")
            self.assertEqual(run.call_count, 3)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[0][:4], ["gh", "repo", "view", "https://github.com/acme/interface"])
            self.assertEqual(commands[1][4], f"s3://first-tree-report/{key}.json")
            self.assertEqual(commands[2][4], f"s3://first-tree-report/{key}.html")

    def test_publisher_never_reaches_html_upload_after_json_failure(self) -> None:
        report = positive_report()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            completed = [
                subprocess.CompletedProcess(
                    ["gh"],
                    0,
                    json.dumps(
                        {
                            "visibility": "PUBLIC",
                            "url": "https://github.com/acme/interface",
                        }
                    ),
                    "",
                ),
                subprocess.CompletedProcess(["aws", "json"], 1, "", "denied"),
            ]
            with patch("publish_report.subprocess.run", side_effect=completed) as run:
                with self.assertRaisesRegex(ValueError, "not publishing a URL"):
                    publish(report_path, root)
            self.assertEqual(run.call_count, 2)

    def test_publishing_recipe_never_executes_target_relative_scripts(self) -> None:
        publishing = (SKILL / "references" / "publishing.md").read_text(encoding="utf-8")
        self.assertIn("<skill-dir>/scripts/publish_report.py", publishing)
        self.assertNotIn("python3 -B scripts/", publishing)

        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("<skill-dir>/scripts/checkout_public_repo.py", skill)

    def test_bounded_checkout_selects_only_eligible_source(self) -> None:
        entries = [
            BlobEntry("a" * 40, 20, "package.json"),
            BlobEntry("b" * 40, 30, "src/App.tsx"),
            BlobEntry("c" * 40, 30, "node_modules/pkg/index.ts"),
            BlobEntry("d" * 40, 30, "src/App.test.tsx"),
            BlobEntry("e" * 40, 1_000_001, "src/Huge.tsx"),
            BlobEntry("f" * 40, 10, "../escape.tsx"),
        ]
        self.assertEqual(
            [entry.path for entry in select_entries(entries)],
            ["package.json", "src/App.tsx"],
        )

        with patch("checkout_public_repo.MAX_FILES", 1):
            with self.assertRaisesRegex(ValueError, "Source file limit exceeded"):
                select_entries(entries[:2])

    def test_bounded_archive_materializes_only_verified_selected_blobs(self) -> None:
        selected_content = b"export const App = () => <main />;\n"
        ignored_content = b"not source"
        entry = BlobEntry(
            _git_blob_oid(selected_content), len(selected_content), "src/App.tsx"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            output = root / "output"
            output.mkdir()
            with tarfile.open(archive, "w:gz") as package:
                for name, content in (
                    ("owner-repo-commit/src/App.tsx", selected_content),
                    ("owner-repo-commit/assets/large.bin", ignored_content),
                ):
                    member = tarfile.TarInfo(name)
                    member.size = len(content)
                    package.addfile(member, io.BytesIO(content))

            _materialize_archive(archive, output, [entry])

            self.assertEqual((output / "src" / "App.tsx").read_bytes(), selected_content)
            self.assertFalse((output / "assets" / "large.bin").exists())

    def test_bounded_archive_rejects_metadata_mismatch_and_unsafe_paths(self) -> None:
        content = b"export default 1;\n"
        entry = BlobEntry("0" * 40, len(content), "src/App.tsx")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            output = root / "output"
            output.mkdir()
            with tarfile.open(archive, "w:gz") as package:
                member = tarfile.TarInfo("owner-repo-commit/src/App.tsx")
                member.size = len(content)
                package.addfile(member, io.BytesIO(content))
            with self.assertRaisesRegex(ValueError, "does not match GitHub metadata"):
                _materialize_archive(archive, output, [entry])

            unsafe_archive = root / "unsafe.tar.gz"
            with tarfile.open(unsafe_archive, "w:gz") as package:
                member = tarfile.TarInfo("../escape.tsx")
                member.size = len(content)
                package.addfile(member, io.BytesIO(content))
            with self.assertRaisesRegex(ValueError, "unsafe path"):
                _materialize_archive(unsafe_archive, root / "unused", [])

    def test_public_schema_declares_hosted_metadata(self) -> None:
        schema = json.loads((ROOT / "schemas" / "ats-1.schema.json").read_text())
        self.assertIn("repository", schema["properties"])
        self.assertIn("generatedAt", schema["properties"])
        self.assertEqual(
            schema["$id"],
            "https://github.com/agent-team-foundation/ai-tell-scan/schemas/ats-1.schema.json",
        )

    def test_public_repository_documentation_baseline_is_complete(self) -> None:
        english = (
            "README.md",
            "CONTRIBUTING.md",
            "DEVELOPMENT.md",
            "CODE_OF_CONDUCT.md",
            "SECURITY.md",
        )
        translations = tuple(name.replace(".md", ".zh-CN.md") for name in english)
        for name in (*english, *translations, "LICENSE"):
            with self.subTest(document=name):
                self.assertTrue((ROOT / name).is_file())

        for name, canonical in zip(translations, english, strict=True):
            content = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(translation=name):
                self.assertIn(f"Canonical source: [./{canonical}]", content)
                self.assertRegex(content, r"Last synced with: \d{4}-\d{2}-\d{2}")

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("[简体中文](README.zh-CN.md)", readme)
        for path in (
            ".github/CODEOWNERS",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/ISSUE_TEMPLATE/config.yml",
        ):
            with self.subTest(collaboration_file=path):
                self.assertTrue((ROOT / path).is_file())


if __name__ == "__main__":
    unittest.main()
