"""Runbook: one table's row count differs between database A and database B.

Expected: exit code 1, the mismatched table shows up in both the full report
and the differences report with the correct delta (B - A), and the unaffected
table stays status=match and is absent from the differences report.

Run directly: python runbooks/scenario_mismatched_row_counts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_support import run_compare  # noqa: E402


def run() -> bool:
    outcome = run_compare(
        counts_a={"EMPLOYEES": 100, "DEPARTMENTS": 12},
        counts_b={"EMPLOYEES": 97, "DEPARTMENTS": 12},
        table_lines=["EMPLOYEES", "DEPARTMENTS"],
    )

    print(outcome.stdout)

    assert outcome.exit_code == 1, f"expected exit code 1, got {outcome.exit_code}"
    assert outcome.differences_report is not None, "expected a differences report to be written"
    assert [row["table"] for row in outcome.differences_report] == ["EMPLOYEES"]
    assert outcome.differences_report[0]["delta"] == "-3"

    statuses = {row["table"]: row["status"] for row in outcome.full_report}
    assert statuses == {"EMPLOYEES": "mismatch", "DEPARTMENTS": "match"}, statuses

    print("PASS: mismatch detected on EMPLOYEES (delta=-3), DEPARTMENTS unaffected, exit code 1")
    return True


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
