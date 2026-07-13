"""Runbook: compare a single table via --table instead of a --tables-file list.

Expected: exit code 1 (the one table mismatches), and both reports contain
exactly that one table - proves --table bypasses the table-list file entirely
and still goes through the same schema-resolution and reporting path.

Run directly: python runbooks/scenario_single_table.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_support import run_compare  # noqa: E402


def run() -> bool:
    outcome = run_compare(
        counts_a={"HR.EMPLOYEES": 100},
        counts_b={"HR.EMPLOYEES": 97},
        table="HR.EMPLOYEES",
    )

    print(outcome.stdout)

    assert outcome.exit_code == 1, f"expected exit code 1, got {outcome.exit_code}"
    assert [row["table"] for row in outcome.full_report] == ["HR.EMPLOYEES"]
    assert outcome.differences_report is not None
    assert [row["table"] for row in outcome.differences_report] == ["HR.EMPLOYEES"]
    assert outcome.differences_report[0]["delta"] == "-3"

    print("PASS: --table compared HR.EMPLOYEES alone, delta=-3, exit code 1")
    return True


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
