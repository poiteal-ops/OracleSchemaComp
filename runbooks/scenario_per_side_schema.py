"""Runbook: A and B keep the same table under different schema names.

Exercises --db-a-schema/--db-b-schema: an unqualified table-list entry must
resolve to the given default schema on each side independently, while an
already-qualified entry (SALES.ORDERS) ignores the defaults entirely.

Expected: exit code 1 (EMPLOYEES differs), EMPLOYEES compared as
HR_PROD.EMPLOYEES on A and HR_UAT.EMPLOYEES on B, SALES.ORDERS matches
using its own explicit qualifier.

Run directly: python runbooks/scenario_per_side_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_support import run_compare  # noqa: E402


def run() -> bool:
    outcome = run_compare(
        counts_a={"HR_PROD.EMPLOYEES": 100, "SALES.ORDERS": 40},
        counts_b={"HR_UAT.EMPLOYEES": 97, "SALES.ORDERS": 40},
        table_lines=["EMPLOYEES", "SALES.ORDERS"],
        schema_a="hr_prod",
        schema_b="hr_uat",
    )

    print(outcome.stdout)

    assert outcome.exit_code == 1, f"expected exit code 1, got {outcome.exit_code}"

    statuses = {row["table"]: row["status"] for row in outcome.full_report}
    assert statuses == {"EMPLOYEES": "mismatch", "SALES.ORDERS": "match"}, statuses

    assert outcome.differences_report is not None
    assert [row["table"] for row in outcome.differences_report] == ["EMPLOYEES"]
    assert outcome.differences_report[0]["delta"] == "-3"

    print("PASS: per-side default schema resolved EMPLOYEES to HR_PROD/HR_UAT correctly")
    return True


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
