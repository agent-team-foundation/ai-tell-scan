#!/usr/bin/env python3
"""Fail-closed publication for an eligible hosted AI Tell Scan report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from ats_core import load_json, validate_final_report, write_text  # noqa: E402
from render_report import REPORT_BASE, render, report_key  # noqa: E402


BUCKET = "s3://first-tree-report"


def _checked_run(
    command: list[str], *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except FileNotFoundError as error:
        raise ValueError(f"Required command is unavailable: {command[0]}") from error


def _verify_public_repository(source: str) -> None:
    result = _checked_run(
        ["gh", "repo", "view", source, "--json", "visibility,url"]
    )
    if result.returncode != 0:
        raise ValueError(
            "Could not verify public repository visibility; not publishing."
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(
            "GitHub visibility response was invalid; not publishing."
        ) from error
    if not isinstance(payload, dict):
        raise ValueError("GitHub visibility response was invalid; not publishing.")
    canonical_url = payload.get("url")
    if (
        payload.get("visibility") != "PUBLIC"
        or not isinstance(canonical_url, str)
        or canonical_url.rstrip("/").lower() != source.lower()
    ):
        raise ValueError(
            "Repository is not the matching public GitHub repository; not publishing."
        )


def _aws_environment() -> dict[str, str]:
    environment = dict(os.environ)
    credentials = Path("/home/ubuntu/.aws/credentials")
    config = Path("/home/ubuntu/.aws/config")
    if credentials.is_file():
        environment["AWS_SHARED_CREDENTIALS_FILE"] = str(credentials)
        environment["AWS_CONFIG_FILE"] = str(config)
    return environment


def _upload(
    source: Path,
    destination: str,
    content_type: str,
    environment: dict[str, str],
) -> None:
    result = _checked_run(
        [
            "aws",
            "s3",
            "cp",
            str(source),
            destination,
            "--content-type",
            content_type,
            "--only-show-errors",
        ],
        env=environment,
    )
    if result.returncode != 0:
        raise ValueError(
            f"Hosted upload failed for {destination}; not publishing a URL."
        )


def publish(report_path: Path, out_dir: Path) -> str:
    report = load_json(report_path)
    validate_final_report(report)
    repository = report.get("repository")
    if not isinstance(repository, dict) or not isinstance(
        repository.get("source"), str
    ):
        raise ValueError("Hosted publication requires repository.source.")
    source = repository["source"]
    _verify_public_repository(source)

    key = report_key(report)
    html_path = out_dir.expanduser().resolve() / f"{key}.html"
    write_text(render(report, key), html_path)

    environment = _aws_environment()
    _upload(report_path, f"{BUCKET}/{key}.json", "application/json", environment)
    _upload(html_path, f"{BUCKET}/{key}.html", "text/html", environment)
    return f"{REPORT_BASE}/{key}.html"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish an eligible hosted-trial ats-1 report."
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        url = publish(args.report, args.out_dir)
    except ValueError as error:
        print(f"ai-tell-scan: {error}", file=sys.stderr)
        return 2
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
