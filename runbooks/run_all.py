"""Run every runbook scenario against a fake Oracle driver and print pass/fail.

No live database required. Suitable for CI: exits 0 only if every scenario
passes.

Usage: python runbooks/run_all.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

RUNBOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(RUNBOOKS_DIR))

SCENARIO_MODULES = [
    "scenario_matching_row_counts",
    "scenario_mismatched_row_counts",
    "scenario_missing_table",
    "scenario_per_side_schema",
    "scenario_single_table",
    "scenario_whole_schema",
]


def main() -> int:
    failures = []
    for module_name in SCENARIO_MODULES:
        print(f"\n=== {module_name} ===")
        module = importlib.import_module(module_name)
        try:
            passed = bool(module.run())
        except AssertionError as exc:
            passed = False
            print(f"FAIL: {exc}")
        if not passed:
            failures.append(module_name)

    print("\n" + "=" * 60)
    print(f"{len(SCENARIO_MODULES) - len(failures)}/{len(SCENARIO_MODULES)} runbook scenarios passed")
    if failures:
        print("Failed: " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
