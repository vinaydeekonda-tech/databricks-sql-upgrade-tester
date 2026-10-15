import json
import unittest
from pathlib import Path

from databricks_sql_upgrade.cli import main
from databricks_sql_upgrade.scanner import scan_repository

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class ScanTests(unittest.TestCase):
    def test_examples_find_qualify_and_merge(self) -> None:
        rows = scan_repository(EXAMPLES)
        patterns = {name for row in rows for name in row.patterns}
        functions = {name for row in rows for name in row.functions}
        self.assertIn("QUALIFY", patterns)
        self.assertIn("MERGE", patterns)
        self.assertIn("row_number", functions)
        self.assertIn("from_json", functions)

    def test_dry_run_writes_gate(self) -> None:
        output = ROOT / "output" / "unit-dry-run"
        code = main(
            [
                "check",
                "--repo",
                str(EXAMPLES),
                "--output",
                str(output),
                "--sql-version",
                "test",
                "--dry-run",
            ]
        )
        self.assertEqual(code, 0)
        payload = json.loads((output / "compile_check_results.json").read_text(encoding="utf-8"))
        self.assertTrue(payload["gate_pass"])
        self.assertGreater(payload["function_probes"], 0)
        self.assertGreater(payload["pattern_probes"], 0)


if __name__ == "__main__":
    unittest.main()
