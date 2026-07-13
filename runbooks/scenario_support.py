"""Shared plumbing for runbook scenarios: env/tmp-dir setup and report reading."""

from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rowcount_compare  # noqa: E402
from fake_oracle import fake_oracle  # noqa: E402

DSN_A = "fake-dsn-a"
DSN_B = "fake-dsn-b"


@dataclass
class RunbookOutcome:
    exit_code: int
    stdout: str
    full_report: List[Dict[str, str]] = field(default_factory=list)
    differences_report: Optional[List[Dict[str, str]]] = None


@contextmanager
def _temp_env(values: Dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def run_compare(
    counts_a: Dict[str, int],
    counts_b: Dict[str, int],
    table_lines: Optional[List[str]] = None,
    table: Optional[str] = None,
    schema_a: Optional[str] = None,
    schema_b: Optional[str] = None,
) -> RunbookOutcome:
    """Run rowcount_compare.main() end-to-end against fake table-count data.

    Pass exactly one of table_lines (a whole table-list file) or table (a
    single table name), mirroring the CLI's --tables-file/--table split.
    """
    if (table_lines is None) == (table is None):
        raise ValueError("run_compare requires exactly one of table_lines or table")

    env = {
        "DB_A_USERNAME": "fake_user_a",
        "DB_A_PASSWORD": "fake_password_a",
        "DB_A_DSN": DSN_A,
        "DB_B_USERNAME": "fake_user_b",
        "DB_B_PASSWORD": "fake_password_b",
        "DB_B_DSN": DSN_B,
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        output_dir = tmp_path / "reports"

        if table is not None:
            argv = ["--table", table, "--output-dir", str(output_dir)]
        else:
            tables_file = tmp_path / "tables.txt"
            tables_file.write_text("\n".join(table_lines) + "\n", encoding="utf-8")
            argv = ["--tables-file", str(tables_file), "--output-dir", str(output_dir)]

        if schema_a:
            argv += ["--db-a-schema", schema_a]
        if schema_b:
            argv += ["--db-b-schema", schema_b]

        buffer = io.StringIO()
        with _temp_env(env), fake_oracle({DSN_A: counts_a, DSN_B: counts_b}), redirect_stdout(buffer):
            exit_code = rowcount_compare.main(argv)

        full_report = _read_latest(output_dir, "rowcount_report_*.csv")
        differences_report = _read_latest(output_dir, "rowcount_differences_*.csv")

    return RunbookOutcome(
        exit_code=exit_code,
        stdout=buffer.getvalue(),
        full_report=full_report,
        differences_report=differences_report if differences_report else None,
    )


def _read_latest(output_dir: Path, pattern: str) -> List[Dict[str, str]]:
    if not output_dir.is_dir():
        return []
    matches = sorted(output_dir.glob(pattern))
    if not matches:
        return []
    with matches[-1].open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
