"""Runbook: a table exists on database A but not on database B.

Expected: exit code 1, the missing table shows up as status=error with
error_b populated (simulated ORA-00942), and - critically - the other,
healthy table is still compared normally. One table's failure must not
abort the scan.

Run directly: python runbooks/scenario_missing_table.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_support import run_compare  # noqa: E402


def run() -> bool:
    outcome = run_compare(
        counts_a={"EMPLOYEES": 100, "LEGACY_AUDIT": 5},
        counts_b={"EMPLOYEES": 100},  # LEGACY_AUDIT absent -> ORA-00942 on side B
        table_lines=["EMPLOYEES", "LEGACY_AUDIT"],
    )

    print(outcome.stdout)

    assert outcome.exit_code == 1, f"expected exit code 1, got {outcome.exit_code}"

    rows_by_table = {row["table"]: row for row in outcome.full_report}
    assert rows_by_table["EMPLOYEES"]["status"] == "match", "healthy table should still be compared"
    assert rows_by_table["LEGACY_AUDIT"]["status"] == "error"
    assert "ORA-00942" in rows_by_table["LEGACY_AUDIT"]["error_b"]
    assert rows_by_table["LEGACY_AUDIT"]["error_a"] == ""

    assert outcome.differences_report is not None
    assert [row["table"] for row in outcome.differences_report] == ["LEGACY_AUDIT"]

    print("PASS: missing table on side B reported as error without blocking EMPLOYEES")
    return True


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
