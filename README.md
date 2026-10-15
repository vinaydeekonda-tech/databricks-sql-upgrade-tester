# Databricks SQL upgrade tester

Scan any Git repository of SQL files, find the functions and syntax those files use, and `EXPLAIN` them on a Databricks SQL warehouse before you upgrade the SQL runtime.

Your SQL stays in your repository. This project only needs:

- a checkout of that repository
- a Databricks workspace URL
- a token that can run SQL
- a SQL warehouse id

It works on AWS, Azure, and GCP workspaces. It does not create warehouses, catalogs, or jobs.

## What a run does

1. Reads every `*.sql` file in the checkout you pass with `--repo`.
2. Lists Databricks SQL functions and higher-risk syntax (`MERGE`, `QUALIFY`, `PIVOT`, `DECLARE`, and others).
3. Picks a small smoke list: the fewest files that still cover every high-risk pattern found.
4. When you pass `--compile-check`, sends one `EXPLAIN` probe per function and pattern to your warehouse.
5. Writes JSON and CSV under `output/`. A syntax failure exits non-zero so CI can block the upgrade.

A missing table on a `MERGE` or `UPDATE` probe is treated as an object error. It does not fail the gate. A parse or unsupported-syntax error does.

## Install

```bash
git clone https://github.com/<you>/databricks-sql-upgrade-tester.git
cd databricks-sql-upgrade-tester
python3 -m pip install -e .
```

Python 3.10 or newer. No third-party packages are required.

## Configure Databricks

Create a SQL warehouse, open its connection details, and export:

```bash
export DATABRICKS_HOST="https://<workspace-host>"
export DATABRICKS_WAREHOUSE_ID="<warehouse-id>"
export DATABRICKS_TOKEN="<token>"
```

Prefer a short-lived token from the Databricks CLI:

```bash
databricks auth login --host "$DATABRICKS_HOST" --profile sql-upgrade
export DATABRICKS_TOKEN="$(databricks auth token --profile sql-upgrade)"
```

The token needs permission to use that warehouse. Do not commit it. See `.env.example`.

## Run against your SQL

```bash
databricks-sql-upgrade check \
  --repo /path/to/your-sql-repo \
  --sql-version "2026.38" \
  --compile-check
```

Try the included examples first, with no warehouse:

```bash
databricks-sql-upgrade check --repo examples --sql-version "local" --dry-run
```

Useful flags:

| Flag | Purpose |
|------|---------|
| `--repo` | Root of the Git checkout that holds your SQL |
| `--sql-glob` | Which files to read. Default is `**/*.sql` |
| `--sql-version` | Label stored in the report. It does not change the warehouse channel |
| `--compile-check` | Call the Databricks SQL Statements API |
| `--dry-run` | Build the same probes and skip the API call |
| `--output` | Where to write the report |

Compare a run from before the upgrade with a run after it:

```bash
databricks-sql-upgrade compare \
  --baseline output/before \
  --current output/after \
  --output output/after/upgrade_diff.json
```

## Reports

| File | Contents |
|------|----------|
| `sql_inventory.json` | One row per SQL file, with functions and patterns |
| `unique_functions.json` | Distinct functions |
| `unique_patterns.json` | Pattern counts |
| `pattern_matrix.csv` | Spreadsheet view |
| `smoke_files.json` | Smallest file set that covers high-risk patterns |
| `compile_check_results.json` | `gate_pass` plus any failing probes |

## GitHub Actions

Workflow: `.github/workflows/upgrade-check.yml`.

In the tester repository, add these Actions secrets:

| Secret | Required | Purpose |
|--------|----------|---------|
| `DATABRICKS_HOST` | yes, for compile check | Workspace URL |
| `DATABRICKS_TOKEN` | yes, for compile check | Token |
| `DATABRICKS_WAREHOUSE_ID` | yes, for compile check | SQL warehouse |
| `SQL_REPO_TOKEN` | only for a private SQL repo | PAT with read access to that repository |

Then run **Databricks SQL upgrade check** and pass `owner/name`, the branch, and the SQL version. The workflow checks out that repository and scans it. It does not publish the SQL.

If your SQL already lives in a repository that can see this tester, you can also vendor or call this package from that repository's own workflow.

## What not to publish

Publish this tester. Keep your SQL repository private unless you already intended to open it.

Before the first public push:

- Confirm your company allows this code to be released under the MIT license in `LICENSE`.
- Search the tree for workspace hostnames, tokens, catalog names, and table names from your environment.
- Do not copy an internal pipeline folder in on top of this project. Internal job configs, database inventory, and orchestrator triggers are not part of this package.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```
