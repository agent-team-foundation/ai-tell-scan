#!/usr/bin/env python3
"""Validate a completed ats-1 report's executable semantics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from ats_core import load_json, validate_final_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a completed ats-1 report.")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        validate_final_report(load_json(args.report))
    except ValueError as error:
        print(f"ai-tell-scan: {error}", file=sys.stderr)
        return 2
    print("ats-1 report is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
