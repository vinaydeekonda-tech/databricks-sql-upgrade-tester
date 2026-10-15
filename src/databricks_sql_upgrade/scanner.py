"""Scan a Git checkout of SQL files and inventory functions and patterns."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from databricks_sql_upgrade.patterns import SQL_PATTERNS, compile_patterns, extract_functions

SKIP_DIRS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "output",
    "target",
    "dist",
    "build",
}


@dataclass
class SqlFileInventory:
    name: str
    folder: str
    rel_path: str
    line_count: int = 0
    patterns: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)


def scan_repository(repo_root: Path, sql_glob: str = "**/*.sql") -> list[SqlFileInventory]:
    """Return one inventory row per SQL file under repo_root."""
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise FileNotFoundError(f"SQL repository not found: {repo_root}")

    compiled = compile_patterns()
    inventories: list[SqlFileInventory] = []
    for path in sorted(repo_root.glob(sql_glob)):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(repo_root).as_posix()
        folder = path.parent.relative_to(repo_root).as_posix()
        if folder == ".":
            folder = "root"
        matched = sorted(name for name, regex in compiled.items() if regex.search(text))
        inventories.append(
            SqlFileInventory(
                name=path.stem,
                folder=folder,
                rel_path=rel,
                line_count=text.count("\n") + (1 if text else 0),
                patterns=matched,
                functions=sorted(extract_functions(text)),
            )
        )
    return inventories


def build_summary(inventories: list[SqlFileInventory]) -> dict:
    pattern_counts: Counter[str] = Counter()
    function_counts: Counter[str] = Counter()
    for item in inventories:
        pattern_counts.update(item.patterns)
        function_counts.update(item.functions)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sql_files": len(inventories),
        "unique_patterns": len(pattern_counts),
        "unique_functions": len(function_counts),
        "pattern_usage": dict(pattern_counts.most_common()),
        "function_usage": dict(function_counts.most_common()),
    }


def write_outputs(inventories: list[SqlFileInventory], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(inventories)

    inventory_json = output_dir / "sql_inventory.json"
    inventory_json.write_text(json.dumps([asdict(item) for item in inventories], indent=2), encoding="utf-8")

    summary_json = output_dir / "inventory_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    matrix_csv = output_dir / "pattern_matrix.csv"
    with matrix_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["folder", "name", "rel_path", "line_count", "pattern_count", "function_count", "patterns", "functions"]
        )
        for item in inventories:
            writer.writerow(
                [
                    item.folder,
                    item.name,
                    item.rel_path,
                    item.line_count,
                    len(item.patterns),
                    len(item.functions),
                    "|".join(item.patterns),
                    "|".join(item.functions),
                ]
            )

    functions = sorted({name for item in inventories for name in item.functions})
    unique_functions = output_dir / "unique_functions.json"
    unique_functions.write_text(
        json.dumps(
            {"generated_at": summary["generated_at"], "count": len(functions), "functions": functions},
            indent=2,
        ),
        encoding="utf-8",
    )

    unique_patterns = output_dir / "unique_patterns.json"
    unique_patterns.write_text(
        json.dumps(
            {
                "generated_at": summary["generated_at"],
                "patterns": [
                    {
                        "name": pattern.name,
                        "category": pattern.category,
                        "risk": pattern.risk,
                        "description": pattern.description,
                        "file_count": summary["pattern_usage"].get(pattern.name, 0),
                    }
                    for pattern in SQL_PATTERNS
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "inventory_json": inventory_json,
        "summary_json": summary_json,
        "patterns_csv": matrix_csv,
        "unique_functions_json": unique_functions,
        "unique_patterns_json": unique_patterns,
    }


def build_smoke_list(inventories: list[SqlFileInventory]) -> list[dict]:
    """Pick the smallest set of SQL files that covers every high-risk pattern found."""
    high_risk = {pattern.name for pattern in SQL_PATTERNS if pattern.risk == "high"}
    remaining = {name for item in inventories for name in item.patterns if name in high_risk}
    pool = {item.rel_path: item for item in inventories if item.patterns}
    selected: list[dict] = []

    while remaining and pool:
        best_path = max(pool, key=lambda path: len(set(pool[path].patterns) & remaining))
        covered = set(pool[best_path].patterns) & remaining
        if not covered:
            break
        item = pool.pop(best_path)
        selected.append(
            {
                "rel_path": item.rel_path,
                "folder": item.folder,
                "name": item.name,
                "covers": sorted(covered),
                "patterns": item.patterns,
                "functions": item.functions,
            }
        )
        remaining -= covered
    return selected
