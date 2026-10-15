"""Compare two inventory folders and report added or removed functions and patterns."""

from __future__ import annotations

import json
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_runs(baseline_dir: Path, current_dir: Path) -> dict:
    baseline_functions = set(_load(baseline_dir / "unique_functions.json")["functions"])
    current_functions = set(_load(current_dir / "unique_functions.json")["functions"])
    baseline_patterns = {
        row["name"]
        for row in _load(baseline_dir / "unique_patterns.json")["patterns"]
        if row.get("file_count", row.get("job_count", 0)) > 0
    }
    current_patterns = {
        row["name"]
        for row in _load(current_dir / "unique_patterns.json")["patterns"]
        if row.get("file_count", row.get("job_count", 0)) > 0
    }
    return {
        "baseline_dir": str(baseline_dir),
        "current_dir": str(current_dir),
        "functions_added": sorted(current_functions - baseline_functions),
        "functions_removed": sorted(baseline_functions - current_functions),
        "patterns_added": sorted(current_patterns - baseline_patterns),
        "patterns_removed": sorted(baseline_patterns - current_patterns),
    }
