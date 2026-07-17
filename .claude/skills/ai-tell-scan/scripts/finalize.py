#!/usr/bin/env python3
"""Apply an agent context review to an ats-1 candidate report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from ats_core import finalize, load_json, validate_source_root, write_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize an ats-1 report from explicit candidate decisions."
    )
    parser.add_argument("candidate_report", type=Path, help="ats-1 candidate JSON")
    parser.add_argument(
        "review", type=Path, help="ats-review-1 JSON with one decision per candidate"
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Original scan root; verified read-only against target.sourceDigest",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Earlier finalized ats-1 report for rescan comparison",
    )
    parser.add_argument(
        "--output", type=Path, help="Final report destination (default: stdout)"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = load_json(args.candidate_report)
        review = load_json(args.review)
        baseline = load_json(args.baseline) if args.baseline is not None else None
        target = validate_source_root(report, args.target)
        write_json(
            finalize(report, review, baseline=baseline),
            args.output,
            forbidden_root=target,
        )
    except ValueError as error:
        print(f"ai-tell-scan: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
