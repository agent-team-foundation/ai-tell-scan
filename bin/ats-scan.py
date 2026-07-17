#!/usr/bin/env python3
"""Repository-local entry point for the canonical AI Tell Scan script."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parent.parent
    / ".claude"
    / "skills"
    / "ai-tell-scan"
    / "scripts"
    / "scan.py"
)

sys.path.insert(0, str(SCRIPT.parent))
runpy.run_path(str(SCRIPT), run_name="__main__")
