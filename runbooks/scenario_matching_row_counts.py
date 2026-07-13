"""Runbook: every table has the same row count on both sides.

Expected: exit code 0, every row in the full report is status=match, and no
differences report file is written at all.

Run directly: python runbooks/scenario_matching_row_counts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_support import run_compare  # noqa: E402


def run() -> bool:
    outcome = run_compare(
        counts_a={"EMPLOYEES": 100, "DEPARTMENTS": 12},
        counts_b={"EMPLOYEES": 100, "DEPARTMENTS": 12},
        table_lines=["EMPLOYEES", "DEPARTMENTS"],
    )

    print(outcome.stdout)

    assert outcome.exit_code == 0, f"expected exit code 0, got {outcome.exit_code}"
    assert outcome.differences_report is None, "expected no differences report to be written"
    statuses = {row["table"]: row["status"] for row in outcome.full_report}
    assert statuses == {"EMPLOYEES": "match", "DEPARTMENTS": "match"}, statuses

    print("PASS: all tables matched, exit code 0, no differences report written")
    return True


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
