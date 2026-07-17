#!/usr/bin/env python3
"""Validate the repository's canonical skill without third-party packages."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "ai-tell-scan" / "SKILL.md"
REQUIRED = (
    ROOT / "AGENTS.md",
    ROOT / "LICENSE",
    ROOT / "README.md",
    ROOT / "schemas" / "ats-1.schema.json",
    SKILL,
)


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED if not path.is_file()]
    if missing:
        print(f"missing required files: {', '.join(missing)}", file=sys.stderr)
        return 1

    text = SKILL.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(?P<header>.*?)\n---\n", text, re.DOTALL)
    if not match:
        print("SKILL.md needs a leading YAML frontmatter block", file=sys.stderr)
        return 1
    header = match.group("header")
    if not re.search(r"(?m)^name:\s*ai-tell-scan\s*$", header):
        print("SKILL.md name must be ai-tell-scan", file=sys.stderr)
        return 1
    description = re.search(r"(?m)^description:\s*(.+)$", header)
    if not description or len(description.group(1).strip()) < 40:
        print("SKILL.md needs a specific routing description", file=sys.stderr)
        return 1
    placeholders = ("<repo-root>/scripts/quick_validate_skill.py", "TODO", "TBD")
    found = [value for value in placeholders if value in text]
    if found:
        print(f"SKILL.md contains unresolved placeholders: {', '.join(found)}", file=sys.stderr)
        return 1
    for relative in re.findall(r"\]\((references/[^)#]+)\)", text):
        target = SKILL.parent / relative
        if not target.is_file():
            print(f"SKILL.md references missing file: {relative}", file=sys.stderr)
            return 1
    print("ai-tell-scan skill contract is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
