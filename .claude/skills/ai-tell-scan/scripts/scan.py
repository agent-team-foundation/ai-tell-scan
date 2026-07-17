#!/usr/bin/env python3
"""Create an ats-1 candidate report without modifying the scanned repository."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

from ats_core import (  # noqa: E402
    review_template,
    scan,
    validate_new_output_path,
    write_json,
)


GITHUB_REPOSITORY_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def canonical_repository_url(value: str) -> tuple[str, str]:
    match = GITHUB_REPOSITORY_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(
            "Repository URL must be https://github.com/<owner>/<repo>."
        )
    owner = match.group("owner")
    repo = match.group("repo")
    if not owner.strip(".") or not repo.strip("."):
        raise ValueError("Repository owner and name cannot be dot-only segments.")
    return f"https://github.com/{owner}/{repo}", f"{owner}/{repo}"


def canonical_generated_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("generated-at must be an ISO-8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError("generated-at must include a timezone.")
    return (
        parsed.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan React/Next.js source for composite AI-template UI tells."
    )
    parser.add_argument("root", type=Path, help="React or Next.js repository root")
    parser.add_argument(
        "--target-id",
        help="Stable project identity used to bind later rescans (default: package name or root directory name)",
    )
    parser.add_argument(
        "--repository-url",
        help="Canonical public GitHub URL embedded for an eligible hosted trial",
    )
    parser.add_argument(
        "--generated-at",
        help="ISO-8601 report time (default: current UTC when --repository-url is set)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write ats-1 JSON outside the scanned repository (default: stdout)",
    )
    parser.add_argument(
        "--review-template",
        type=Path,
        help="Write an ats-review-1 decision template outside the scanned repository",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=5000,
        help="Fail when more than this many source files are in scope",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = args.root.expanduser().resolve()
        if (
            args.output is not None
            and args.review_template is not None
            and args.output.expanduser().resolve()
            == args.review_template.expanduser().resolve()
        ):
            raise ValueError(
                "Candidate report and review template need distinct output paths."
            )
        for path in (args.output, args.review_template):
            if path is not None:
                validate_new_output_path(path, forbidden_root=root)

        repository_url = None
        repository_id = None
        if args.repository_url is not None:
            repository_url, repository_id = canonical_repository_url(
                args.repository_url
            )
        if args.generated_at is not None and repository_url is None:
            raise ValueError("--generated-at requires --repository-url.")
        generated_at = None
        if repository_url is not None:
            generated_at = canonical_generated_at(
                args.generated_at
                or datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
            )

        report = scan(
            root,
            max_files=args.max_files,
            target_id=args.target_id or repository_id,
        )
        if repository_url is not None and generated_at is not None:
            report["repository"] = {"source": repository_url}
            report["generatedAt"] = generated_at
        write_json(report, args.output, forbidden_root=root)
        if args.review_template is not None:
            write_json(
                review_template(report), args.review_template, forbidden_root=root
            )
    except ValueError as error:
        print(f"ai-tell-scan: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
