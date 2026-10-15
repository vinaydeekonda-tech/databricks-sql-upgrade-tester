"""Command line entry point for Databricks SQL upgrade checks."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from databricks_sql_upgrade import __version__
from databricks_sql_upgrade.client import DatabricksSqlClient
from databricks_sql_upgrade.compare import compare_runs
from databricks_sql_upgrade.compile_check import run_compile_check, write_compile_results
from databricks_sql_upgrade.scanner import build_smoke_list, scan_repository, write_outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan a SQL Git repo and EXPLAIN-check functions on a Databricks SQL warehouse."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Scan SQL files and optionally EXPLAIN them")
    check.add_argument("--repo", type=Path, required=True, help="Checkout of the SQL Git repository to scan")
    check.add_argument("--sql-glob", default="**/*.sql", help="Glob under --repo (default: **/*.sql)")
    check.add_argument("--output", type=Path, default=None, help="Output directory (default: output/<timestamp>)")
    check.add_argument("--sql-version", default="unspecified", help="Label for the Databricks SQL version under test")
    check.add_argument("--compile-check", action="store_true", help="EXPLAIN functions and patterns on the warehouse")
    check.add_argument("--dry-run", action="store_true", help="Build probes without calling Databricks")

    compare = sub.add_parser("compare", help="Diff two previous check output folders")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--current", type=Path, required=True)
    compare.add_argument("--output", type=Path, default=None)
    return parser


def _check(args: argparse.Namespace) -> int:
    inventories = scan_repository(args.repo, args.sql_glob)
    if not inventories:
        print(f"No SQL files matched {args.sql_glob} under {args.repo}", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output or Path("output") / stamp
    written = write_outputs(inventories, output_dir)
    smoke = build_smoke_list(inventories)
    smoke_path = output_dir / "smoke_files.json"
    smoke_path.write_text(
        json.dumps({"sql_version": args.sql_version, "files": smoke}, indent=2),
        encoding="utf-8",
    )
    (output_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sql_version": args.sql_version,
                "repo": str(args.repo.resolve()),
                "sql_glob": args.sql_glob,
                "sql_files": len(inventories),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = json.loads(written["summary_json"].read_text(encoding="utf-8"))
    print(f"SQL files:        {summary['sql_files']}")
    print(f"Unique functions: {summary['unique_functions']}")
    print(f"Unique patterns:  {summary['unique_patterns']}")
    print(f"Smoke files:      {len(smoke)}")
    print(f"Output:           {output_dir}")

    if not args.compile_check and not args.dry_run:
        return 0

    client = DatabricksSqlClient()
    if args.compile_check and not args.dry_run and not client.configured():
        print(
            "Set DATABRICKS_HOST, DATABRICKS_TOKEN, and DATABRICKS_WAREHOUSE_ID before --compile-check.",
            file=sys.stderr,
        )
        return 2

    payload = run_compile_check(client, inventories, dry_run=args.dry_run or not args.compile_check)
    write_compile_results(payload, output_dir)
    print(f"Compile gate:     {'PASS' if payload['gate_pass'] else 'FAIL'}")
    if not payload["gate_pass"]:
        for row in payload["syntax_failures"] + payload["other_failures"]:
            print(f"  {row['probe_type']} {row['name']}: {row['error']}", file=sys.stderr)
        return 1
    return 0


def _compare(args: argparse.Namespace) -> int:
    diff = compare_runs(args.baseline, args.current)
    print(f"Functions added:   {len(diff['functions_added'])}")
    print(f"Functions removed: {len(diff['functions_removed'])}")
    print(f"Patterns added:    {len(diff['patterns_added'])}")
    print(f"Patterns removed:  {len(diff['patterns_removed'])}")
    if args.output:
        args.output.write_text(json.dumps(diff, indent=2), encoding="utf-8")
        print(f"Diff written to:   {args.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check":
        return _check(args)
    if args.command == "compare":
        return _compare(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
