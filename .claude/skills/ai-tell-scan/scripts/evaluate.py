#!/usr/bin/env python3
"""Repeatable end-to-end evaluation for AI Tell Scan."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True

from ats_core import RULES, load_json, scan, write_json  # noqa: E402

CandidateKey = tuple[str, str]


def parse_args() -> argparse.Namespace:
    skill_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Evaluate AI Tell Scan on the pinned 30-project gold set."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=skill_root / "evals" / "gold-set.json",
        help="ats-gold-1 manifest (default: bundled corpus)",
    )
    parser.add_argument(
        "--review",
        type=Path,
        default=skill_root / "evals" / "independent-review.json",
        help="Blinded ats-independent-review-1 artifact (default: bundled review)",
    )
    parser.add_argument(
        "--output", type=Path, help="Write ats-eval-1 JSON (default: stdout)"
    )
    return parser.parse_args()


def ratio(numerator: int, denominator: int, empty: float = 1.0) -> float:
    return round(numerator / denominator, 4) if denominator else empty


def _label_key(value: object, project_id: str) -> CandidateKey:
    if not isinstance(value, dict):
        raise ValueError(f"Project {project_id} has a non-object gold label.")
    rule_id = value.get("ruleId")
    relative_file = value.get("file")
    if not isinstance(rule_id, str) or rule_id not in RULES:
        raise ValueError(f"Project {project_id} has an invalid gold ruleId.")
    if (
        not isinstance(relative_file, str)
        or not relative_file
        or Path(relative_file).is_absolute()
        or ".." in Path(relative_file).parts
    ):
        raise ValueError(f"Project {project_id} has an invalid gold file path.")
    return rule_id, relative_file


def validate_manifest(
    manifest: dict[str, object], manifest_path: Path
) -> list[dict[str, object]]:
    if manifest.get("schemaVersion") != "ats-gold-1":
        raise ValueError("Gold manifest is not ats-gold-1.")
    projects = manifest.get("projects")
    if not isinstance(projects, list) or len(projects) != 30:
        raise ValueError("Gold manifest must contain exactly 30 projects.")
    corpus = manifest.get("corpus")
    if not isinstance(corpus, dict) or corpus.get("projectCount") != len(projects):
        raise ValueError("Gold manifest corpus.projectCount must equal 30.")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    seen_root_ids: set[tuple[int, int]] = set()
    corpus_root = manifest_path.parent.resolve()
    normalized: list[dict[str, object]] = []
    for project in projects:
        if not isinstance(project, dict):
            raise ValueError("Gold manifest contains a non-object project.")
        project_id = project.get("id")
        relative_path = project.get("path")
        expected_status = project.get("expectedStatus")
        framework = project.get("framework")
        candidate_labels = project.get("expectedCandidates")
        confirmed_labels = project.get("confirmedCandidates")
        if not isinstance(project_id, str) or not project_id or project_id in seen_ids:
            raise ValueError(f"Invalid or duplicate project id: {project_id}")
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or relative_path in seen_paths
        ):
            raise ValueError(f"Project {project_id} has an invalid or duplicate path.")
        relative_project_path = Path(relative_path)
        if relative_project_path.is_absolute() or ".." in relative_project_path.parts:
            raise ValueError(f"Project {project_id} path must stay inside the corpus.")
        if expected_status not in {"completed", "needs-review", "not-applicable"}:
            raise ValueError(f"Project {project_id} has invalid expectedStatus.")
        if framework not in {"react", "nextjs"}:
            raise ValueError(f"Project {project_id} has invalid framework metadata.")
        if not isinstance(candidate_labels, list) or not isinstance(
            confirmed_labels, list
        ):
            raise ValueError(f"Project {project_id} has incomplete candidate labels.")
        expected_candidates = {
            _label_key(item, project_id) for item in candidate_labels
        }
        expected_confirmed = {_label_key(item, project_id) for item in confirmed_labels}
        if len(expected_candidates) != len(candidate_labels) or len(
            expected_confirmed
        ) != len(confirmed_labels):
            raise ValueError(f"Project {project_id} repeats a confirmed candidate.")
        if not expected_confirmed.issubset(expected_candidates):
            raise ValueError(
                f"Project {project_id} confirms a candidate the scanner should not emit."
            )
        if bool(expected_candidates) != (expected_status == "needs-review"):
            raise ValueError(
                f"Project {project_id} labels do not match its expected status."
            )
        project_root = (corpus_root / relative_project_path).resolve()
        try:
            project_root.relative_to(corpus_root)
        except ValueError as error:
            raise ValueError(
                f"Project {project_id} path escapes the corpus directory."
            ) from error
        if not project_root.is_dir():
            raise ValueError(
                f"Project {project_id} directory does not exist: {project_root}"
            )
        root_stat = project_root.stat()
        root_identity = (root_stat.st_dev, root_stat.st_ino)
        if root_identity in seen_root_ids:
            raise ValueError(f"Project {project_id} resolves to a duplicate directory.")
        for _, relative_file in expected_candidates | expected_confirmed:
            if not (project_root / relative_file).is_file():
                raise ValueError(
                    f"Project {project_id} gold file does not exist: {relative_file}"
                )
        seen_ids.add(project_id)
        seen_paths.add(relative_path)
        seen_root_ids.add(root_identity)
        normalized.append(
            {
                **project,
                "expectedCandidatesNormalized": expected_candidates,
                "expectedConfirmedNormalized": expected_confirmed,
                "root": project_root,
            }
        )

    positive_count = sum(
        bool(project["expectedConfirmedNormalized"]) for project in normalized
    )
    review_negative_count = sum(
        bool(project["expectedCandidatesNormalized"])
        and not bool(project["expectedConfirmedNormalized"])
        for project in normalized
    )
    not_applicable_count = sum(
        project["expectedStatus"] == "not-applicable" for project in normalized
    )
    hard_negative_count = len(normalized) - positive_count - not_applicable_count
    framework_counts = {
        "react": sum(project["framework"] == "react" for project in normalized),
        "nextjs": sum(project["framework"] == "nextjs" for project in normalized),
    }
    composition = corpus.get("composition")
    declared_frameworks = (
        composition.get("frameworks") if isinstance(composition, dict) else None
    )
    declared = (
        composition.get("positiveProjects") if isinstance(composition, dict) else None,
        composition.get("hardNegativeProjects")
        if isinstance(composition, dict)
        else None,
        composition.get("notApplicableProjects")
        if isinstance(composition, dict)
        else None,
    )
    if declared != (positive_count, hard_negative_count, not_applicable_count):
        raise ValueError("Gold manifest composition counts do not match its projects.")
    if (
        not isinstance(composition, dict)
        or composition.get("reviewNegativeProjects") != review_negative_count
    ):
        raise ValueError("Gold manifest review-negative count does not match projects.")
    if declared_frameworks != framework_counts:
        raise ValueError("Gold manifest framework counts do not match its projects.")
    return normalized


def _candidate_key(candidate: dict[str, object]) -> CandidateKey:
    return str(candidate.get("ruleId")), str(candidate.get("file"))


def _key_object(project_id: str, key: CandidateKey) -> dict[str, str]:
    return {"projectId": project_id, "ruleId": key[0], "file": key[1]}


def _source_line(root: Path, relative_file: object, line: object) -> str | None:
    if (
        not isinstance(relative_file, str)
        or not isinstance(line, int)
        or Path(relative_file).is_absolute()
        or ".." in Path(relative_file).parts
    ):
        return None
    source = (root / relative_file).resolve()
    try:
        source.relative_to(root)
        lines = source.read_text(encoding="utf-8").splitlines()
    except (ValueError, OSError, UnicodeDecodeError):
        return None
    if not 1 <= line <= len(lines):
        return None
    return re.sub(r"\s+", " ", lines[line - 1].strip())[:180]


def _evidence_problems(
    project_id: str, root: Path, candidate: dict[str, object]
) -> list[dict[str, object]]:
    candidate_id = candidate.get("candidateId")
    problems: list[dict[str, object]] = []
    if _source_line(root, candidate.get("file"), candidate.get("line")) is None:
        problems.append(
            {
                "projectId": project_id,
                "candidateId": candidate_id,
                "kind": "primary",
                "file": candidate.get("file"),
                "line": candidate.get("line"),
                "reason": "Primary location does not resolve to a source line.",
            }
        )
    evidence = candidate.get("evidence")
    if not isinstance(evidence, list) or len(evidence) < 3:
        problems.append(
            {
                "projectId": project_id,
                "candidateId": candidate_id,
                "kind": "evidence-array",
                "reason": "Candidate must contain at least three evidence records.",
            }
        )
        return problems
    for index, record in enumerate(evidence):
        if not isinstance(record, dict):
            problems.append(
                {
                    "projectId": project_id,
                    "candidateId": candidate_id,
                    "kind": "evidence-record",
                    "index": index,
                    "reason": "Evidence record is not an object.",
                }
            )
            continue
        actual_excerpt = _source_line(root, record.get("file"), record.get("line"))
        if actual_excerpt is None or record.get("excerpt") != actual_excerpt:
            problems.append(
                {
                    "projectId": project_id,
                    "candidateId": candidate_id,
                    "kind": record.get("kind"),
                    "index": index,
                    "file": record.get("file"),
                    "line": record.get("line"),
                    "reason": "Evidence location or excerpt does not match source.",
                }
            )
    return problems


def _validate_review_project(
    review_project: object,
    project_id: str,
    report: dict[str, object],
    candidates: list[dict[str, object]],
) -> tuple[set[CandidateKey], set[CandidateKey], list[str]]:
    problems: list[str] = []
    confirmed: set[CandidateKey] = set()
    rejected: set[CandidateKey] = set()
    if not isinstance(review_project, dict):
        return confirmed, rejected, ["missing blinded project review"]
    actual_status = (
        str(report.get("scan", {}).get("status"))
        if isinstance(report.get("scan"), dict)
        else "missing"
    )
    if review_project.get("scanStatus") != actual_status:
        problems.append("review scanStatus does not match scanner output")
    target = report.get("target")
    if not isinstance(target, dict):
        problems.append("scanner report target binding is malformed")
    else:
        if review_project.get("targetId") != target.get("targetId"):
            problems.append("review targetId does not match scanner output")
        if review_project.get("sourceDigest") != target.get("sourceDigest"):
            problems.append("review sourceDigest does not match scanner output")
    if review_project.get("candidateSetDigest") != report.get("candidateSetDigest"):
        problems.append("review candidateSetDigest does not match scanner output")
    decisions = review_project.get("decisions")
    if not isinstance(decisions, list):
        return confirmed, rejected, problems + ["review decisions is not an array"]

    actual_by_identity = {
        (
            str(candidate.get("ruleId")),
            str(candidate.get("file")),
            int(candidate.get("line", 0)),
        ): candidate
        for candidate in candidates
    }
    seen: set[tuple[str, str, int]] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            problems.append("review contains a non-object decision")
            continue
        identity = (
            str(decision.get("ruleId")),
            str(decision.get("file")),
            int(decision.get("line", 0)),
        )
        if identity in seen:
            problems.append(f"duplicate review decision: {identity}")
            continue
        seen.add(identity)
        if identity not in actual_by_identity:
            problems.append(f"review decision does not match a candidate: {identity}")
            continue
        disposition = decision.get("disposition")
        rationale = decision.get("rationale")
        valid = True
        if disposition not in {"confirmed", "rejected"}:
            problems.append(f"invalid review disposition: {identity}")
            valid = False
        if not isinstance(rationale, str) or len(rationale.strip()) < 12:
            problems.append(f"review rationale is too short: {identity}")
            valid = False
        if valid and disposition == "confirmed":
            confirmed.add((identity[0], identity[1]))
        if valid and disposition == "rejected":
            rejected.add((identity[0], identity[1]))
    missing = sorted(set(actual_by_identity) - seen)
    if missing:
        problems.append(f"review is missing candidate decisions: {missing}")
    return confirmed, rejected, problems


def _metrics(
    predicted: set[CandidateKey], expected: set[CandidateKey]
) -> tuple[set[CandidateKey], set[CandidateKey], set[CandidateKey]]:
    return predicted & expected, predicted - expected, expected - predicted


def evaluate(
    manifest_path: Path, review_path: Path | None = None
) -> tuple[dict[str, object], bool]:
    manifest = load_json(manifest_path)
    projects = validate_manifest(manifest, manifest_path)
    resolved_review_path = (
        review_path or manifest_path.parent / "independent-review.json"
    )
    blinded_review = load_json(resolved_review_path)
    if blinded_review.get("schemaVersion") != "ats-independent-review-1":
        raise ValueError("Independent review is not ats-independent-review-1.")
    if blinded_review.get("blindedToGold") is not True:
        raise ValueError("Independent review must attest that it was blinded to gold.")
    review_tool_version = blinded_review.get("toolVersion")
    if not isinstance(review_tool_version, str) or not review_tool_version:
        raise ValueError("Independent review must bind a toolVersion.")
    review_tool_name = blinded_review.get("toolName")
    if review_tool_name != "ai-tell-scan":
        raise ValueError("Independent review must bind toolName=ai-tell-scan.")
    if (
        not isinstance(blinded_review.get("reviewer"), str)
        or not str(blinded_review["reviewer"]).strip()
    ):
        raise ValueError("Independent review must name its reviewer.")
    usability_findings = blinded_review.get("usabilityFindings")
    if not isinstance(usability_findings, list) or not all(
        isinstance(item, str) and item.strip() for item in usability_findings
    ):
        raise ValueError("Independent review usabilityFindings must be a string array.")
    review_projects = blinded_review.get("projects")
    if not isinstance(review_projects, list):
        raise ValueError("Independent review has no projects array.")
    review_by_id: dict[str, object] = {}
    for item in review_projects:
        if not isinstance(item, dict) or not isinstance(item.get("projectId"), str):
            raise ValueError("Independent review contains an invalid project.")
        project_id = str(item["projectId"])
        if project_id in review_by_id:
            raise ValueError(f"Independent review repeats project {project_id}.")
        review_by_id[project_id] = item

    candidate_tp: list[dict[str, str]] = []
    candidate_fp: list[dict[str, str]] = []
    candidate_fn: list[dict[str, str]] = []
    confirmed_tp: list[dict[str, str]] = []
    confirmed_fp: list[dict[str, str]] = []
    confirmed_fn: list[dict[str, str]] = []
    invalid_evidence: list[dict[str, object]] = []
    status_mismatches: list[dict[str, str]] = []
    framework_mismatches: list[dict[str, str]] = []
    review_problems: list[dict[str, object]] = [
        {"projectId": "<review>", "problem": finding} for finding in usability_findings
    ]
    review_decision_count = 0
    review_rejected_count = 0
    review_negative_candidate_count = 0
    always_confirm_tp = 0
    always_confirm_fp = 0
    result_rows: list[dict[str, object]] = []
    rule_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "candidateTp": 0,
            "candidateFp": 0,
            "candidateFn": 0,
            "confirmedTp": 0,
            "confirmedFp": 0,
            "confirmedFn": 0,
        }
    )

    for project in projects:
        project_id = str(project["id"])
        root = project["root"]
        expected_candidates = project["expectedCandidatesNormalized"]
        expected_confirmed = project["expectedConfirmedNormalized"]
        if (
            not isinstance(root, Path)
            or not isinstance(expected_candidates, set)
            or not isinstance(expected_confirmed, set)
        ):
            raise ValueError(f"Project {project_id} normalization failed.")
        report = scan(root, target_id=project_id)
        raw_candidates = report.get("candidates")
        if not isinstance(raw_candidates, list) or not all(
            isinstance(candidate, dict) for candidate in raw_candidates
        ):
            raise ValueError(f"Project {project_id} produced invalid candidates.")
        candidates = [
            candidate for candidate in raw_candidates if isinstance(candidate, dict)
        ]
        predicted = {_candidate_key(candidate) for candidate in candidates}
        if len(predicted) != len(candidates):
            raise ValueError(f"Project {project_id} emitted duplicate candidate keys.")

        actual_status = (
            str(report.get("scan", {}).get("status"))
            if isinstance(report.get("scan"), dict)
            else "missing"
        )
        expected_status = str(project["expectedStatus"])
        if actual_status != expected_status:
            status_mismatches.append(
                {
                    "projectId": project_id,
                    "expected": expected_status,
                    "actual": actual_status,
                }
            )
        target = report.get("target")
        detected_frameworks = (
            target.get("frameworks") if isinstance(target, dict) else None
        )
        detected_framework = (
            "nextjs"
            if isinstance(detected_frameworks, list) and "nextjs" in detected_frameworks
            else "react"
            if isinstance(detected_frameworks, list) and "react" in detected_frameworks
            else "unsupported"
        )
        expected_framework = str(project["framework"])
        if detected_framework != expected_framework:
            framework_mismatches.append(
                {
                    "projectId": project_id,
                    "expected": expected_framework,
                    "actual": detected_framework,
                }
            )

        confirmed, rejected, project_review_problems = _validate_review_project(
            review_by_id.get(project_id), project_id, report, candidates
        )
        tool = report.get("tool")
        if (
            not isinstance(tool, dict)
            or tool.get("name") != review_tool_name
            or tool.get("version") != review_tool_version
        ):
            project_review_problems.append(
                "review tool name/version does not match scanner output"
            )
        for problem in project_review_problems:
            review_problems.append({"projectId": project_id, "problem": problem})
        review_decision_count += len(confirmed) + len(rejected)
        review_rejected_count += len(rejected)
        review_negative_candidate_count += len(expected_candidates - expected_confirmed)
        always_confirm_tp += len(predicted & expected_confirmed)
        always_confirm_fp += len(predicted - expected_confirmed)
        invalid_evidence.extend(
            problem
            for candidate in candidates
            for problem in _evidence_problems(project_id, root, candidate)
        )

        candidate_sets = _metrics(predicted, expected_candidates)
        confirmed_sets = _metrics(confirmed, expected_confirmed)
        destinations = (
            (candidate_sets[0], candidate_tp, "candidateTp"),
            (candidate_sets[1], candidate_fp, "candidateFp"),
            (candidate_sets[2], candidate_fn, "candidateFn"),
            (confirmed_sets[0], confirmed_tp, "confirmedTp"),
            (confirmed_sets[1], confirmed_fp, "confirmedFp"),
            (confirmed_sets[2], confirmed_fn, "confirmedFn"),
        )
        for keys, destination, counter in destinations:
            for key in sorted(keys):
                destination.append(_key_object(project_id, key))
                rule_counts[key[0]][counter] += 1

        result_rows.append(
            {
                "projectId": project_id,
                "expectedStatus": expected_status,
                "actualStatus": actual_status,
                "expectedConfirmed": [
                    {"ruleId": key[0], "file": key[1]}
                    for key in sorted(expected_confirmed)
                ],
                "expectedCandidates": [
                    {"ruleId": key[0], "file": key[1]}
                    for key in sorted(expected_candidates)
                ],
                "emittedCandidates": [
                    {"ruleId": key[0], "file": key[1]} for key in sorted(predicted)
                ],
                "agentConfirmed": [
                    {"ruleId": key[0], "file": key[1]} for key in sorted(confirmed)
                ],
            }
        )

    unknown_review_projects = sorted(
        set(review_by_id) - {str(item["id"]) for item in projects}
    )
    for project_id in unknown_review_projects:
        review_problems.append(
            {"projectId": project_id, "problem": "unknown project in blinded review"}
        )

    candidate_precision = ratio(
        len(candidate_tp), len(candidate_tp) + len(candidate_fp)
    )
    candidate_recall = ratio(len(candidate_tp), len(candidate_tp) + len(candidate_fn))
    confirmed_precision = ratio(
        len(confirmed_tp), len(confirmed_tp) + len(confirmed_fp)
    )
    confirmed_recall = ratio(len(confirmed_tp), len(confirmed_tp) + len(confirmed_fn))
    always_confirm_precision = ratio(
        always_confirm_tp, always_confirm_tp + always_confirm_fp
    )
    confirmed_f1 = (
        round(
            2
            * confirmed_precision
            * confirmed_recall
            / (confirmed_precision + confirmed_recall),
            4,
        )
        if confirmed_precision + confirmed_recall
        else 0.0
    )
    thresholds = manifest.get("thresholds")
    confirmed_threshold = 0.9
    candidate_threshold = 0.9
    if isinstance(thresholds, dict):
        if isinstance(thresholds.get("confirmedPrecision"), (float, int)):
            confirmed_threshold = float(thresholds["confirmedPrecision"])
        if isinstance(thresholds.get("candidatePrecision"), (float, int)):
            candidate_threshold = float(thresholds["candidatePrecision"])

    per_rule: list[dict[str, object]] = []
    for rule_id in sorted(RULES):
        counts = rule_counts[rule_id]
        per_rule.append(
            {
                "ruleId": rule_id,
                **counts,
                "candidatePrecision": ratio(
                    counts["candidateTp"],
                    counts["candidateTp"] + counts["candidateFp"],
                ),
                "candidateRecall": ratio(
                    counts["candidateTp"],
                    counts["candidateTp"] + counts["candidateFn"],
                ),
                "confirmedPrecision": ratio(
                    counts["confirmedTp"],
                    counts["confirmedTp"] + counts["confirmedFp"],
                ),
                "confirmedRecall": ratio(
                    counts["confirmedTp"],
                    counts["confirmedTp"] + counts["confirmedFn"],
                ),
            }
        )

    passed = (
        candidate_precision >= candidate_threshold
        and confirmed_precision >= confirmed_threshold
        and not candidate_fn
        and not confirmed_fn
        and not status_mismatches
        and not framework_mismatches
        and not invalid_evidence
        and not review_problems
        and review_negative_candidate_count > 0
        and review_rejected_count >= review_negative_candidate_count
        and always_confirm_precision < confirmed_threshold
        and all(row["candidateTp"] + row["candidateFn"] >= 1 for row in per_rule)
    )
    report: dict[str, object] = {
        "schemaVersion": "ats-eval-1",
        "corpus": manifest.get("corpus", {}),
        "review": {
            "schemaVersion": blinded_review.get("schemaVersion"),
            "reviewer": blinded_review.get("reviewer"),
            "blindedToGold": blinded_review.get("blindedToGold"),
        },
        "thresholds": {
            "candidatePrecision": candidate_threshold,
            "confirmedPrecision": confirmed_threshold,
        },
        "summary": {
            "passed": passed,
            "projectCount": len(projects),
            "candidateTp": len(candidate_tp),
            "candidateFp": len(candidate_fp),
            "candidateFn": len(candidate_fn),
            "candidatePrecision": candidate_precision,
            "candidateRecall": candidate_recall,
            "tp": len(confirmed_tp),
            "fp": len(confirmed_fp),
            "fn": len(confirmed_fn),
            "confirmedPrecision": confirmed_precision,
            "confirmedRecall": confirmed_recall,
            "f1": confirmed_f1,
            "statusMismatchCount": len(status_mismatches),
            "frameworkMismatchCount": len(framework_mismatches),
            "invalidEvidenceCount": len(invalid_evidence),
            "reviewProblemCount": len(review_problems),
            "reviewDecisionCount": review_decision_count,
            "reviewRejectedCount": review_rejected_count,
            "reviewNegativeCandidateCount": review_negative_candidate_count,
            "alwaysConfirmPrecision": always_confirm_precision,
        },
        "perRule": per_rule,
        "candidateFalsePositives": candidate_fp,
        "candidateFalseNegatives": candidate_fn,
        "falsePositives": confirmed_fp,
        "falseNegatives": confirmed_fn,
        "statusMismatches": status_mismatches,
        "frameworkMismatches": framework_mismatches,
        "invalidEvidence": invalid_evidence,
        "reviewProblems": review_problems,
        "projects": result_rows,
        "interpretation": {
            "candidateLayer": "Candidate metrics score every emitted (project, ruleId, file) record; duplicate same-rule candidates cannot disappear into a set of rule ids.",
            "agentLayer": "Confirmed metrics apply the committed review produced by an agent that was not given the gold manifest.",
            "limit": "The bundled corpus is controlled and de-identified; passing it is a regression gate, not a population-wide accuracy claim.",
        },
    }
    return report, passed


def main() -> int:
    args = parse_args()
    try:
        report, passed = evaluate(
            args.manifest.expanduser().resolve(), args.review.expanduser().resolve()
        )
        write_json(report, args.output)
    except ValueError as error:
        print(f"ai-tell-scan eval: {error}", file=sys.stderr)
        return 2
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
