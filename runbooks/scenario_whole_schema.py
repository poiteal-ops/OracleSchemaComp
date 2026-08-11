"""Runbook: discover and compare a whole schema on both database sides."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_support import run_compare  # noqa: E402


def run() -> bool:
    mview_name = "DEPARTMENT_TOTALS_MATERIALIZED_VIEW"
    mview_container = "DEPARTMENT_TOTALS_MV_0001"
    outcome = run_compare(
        counts_a={
            "HR_PROD.EMPLOYEES": 100,
            "HR_PROD.ACTIVE_EMPLOYEES": 90,
            f"HR_PROD.{mview_name}": 12,
            "HR_PROD.LEGACY_AUDIT": 4,
        },
        counts_b={
            "HR_UAT.EMPLOYEES": 100,
            "HR_UAT.ACTIVE_EMPLOYEES": 90,
            f"HR_UAT.{mview_name}": 12,
        },
        whole_schema=True,
        schema_a="HR_PROD",
        schema_b="HR_UAT",
        objects_a=["EMPLOYEES", "LEGACY_AUDIT", mview_container],
        objects_b=["EMPLOYEES", mview_container],
        views_a=["ACTIVE_EMPLOYEES"],
        views_b=["ACTIVE_EMPLOYEES"],
        mviews_a={mview_name: mview_container},
        mviews_b={mview_name: mview_container},
    )

    print(outcome.stdout)
    assert outcome.exit_code == 1, f"expected exit code 1, got {outcome.exit_code}"

    statuses = {row["table"]: row["status"] for row in outcome.full_report}
    assert statuses == {
        "ACTIVE_EMPLOYEES": "match",
        mview_name: "match",
        "EMPLOYEES": "match",
        "LEGACY_AUDIT": "error",
    }, statuses

    assert outcome.differences_report is not None
    assert [row["table"] for row in outcome.differences_report] == ["LEGACY_AUDIT"]

    print("PASS: whole-schema discovery merged both sides and reported a missing object")
    return True


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
