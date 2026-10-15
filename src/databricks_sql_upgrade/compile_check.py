"""EXPLAIN function and pattern probes on a Databricks SQL warehouse."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from databricks_sql_upgrade.client import DatabricksSqlClient, classify_compile_error
from databricks_sql_upgrade.probes import FUNCTION_PROBE_SQL, PATTERN_PROBE_SQL
from databricks_sql_upgrade.scanner import SqlFileInventory


@dataclass
class ProbeResult:
    name: str
    probe_type: str
    sql: str
    status: str
    ok: bool
    failure_category: str | None = None
    error: str | None = None


def _run_probe(client: DatabricksSqlClient, name: str, probe_type: str, sql: str, dry_run: bool) -> ProbeResult:
    if dry_run:
        return ProbeResult(name=name, probe_type=probe_type, sql=sql, status="DRY_RUN", ok=True)
    result = client.explain(sql)
    category = None if result.ok else classify_compile_error(result.error)
    # Missing tables and missing privileges are expected for EXPLAIN-only DML probes.
    ok = result.ok or category == "object_or_permission"
    return ProbeResult(
        name=name,
        probe_type=probe_type,
        sql=sql,
        status=result.status,
        ok=ok,
        failure_category=category,
        error=result.error,
    )


def run_compile_check(
    client: DatabricksSqlClient,
    inventories: list[SqlFileInventory],
    dry_run: bool = False,
) -> dict:
    functions = sorted({name for item in inventories for name in item.functions})
    patterns = sorted({name for item in inventories for name in item.patterns if name in PATTERN_PROBE_SQL})

    results: list[ProbeResult] = []
    for name in functions:
        sql = FUNCTION_PROBE_SQL.get(name)
        if not sql:
            results.append(
                ProbeResult(name=name, probe_type="function", sql="", status="SKIPPED_NO_PROBE", ok=True)
            )
            continue
        results.append(_run_probe(client, name, "function", sql, dry_run))

    for name in patterns:
        results.append(_run_probe(client, name, "pattern", PATTERN_PROBE_SQL[name], dry_run))

    syntax_failures = [asdict(row) for row in results if not row.ok and row.failure_category == "syntax"]
    other_failures = [
        asdict(row)
        for row in results
        if not row.ok and row.failure_category not in {None, "object_or_permission"}
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "function_probes": len(functions),
        "pattern_probes": len(patterns),
        "gate_pass": not syntax_failures and not other_failures,
        "syntax_failures": syntax_failures,
        "other_failures": other_failures,
        "results": [asdict(row) for row in results],
    }


def write_compile_results(payload: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "compile_check_results.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
