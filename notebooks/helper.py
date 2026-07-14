"""Interactive helper for driving rowcount_compare.py from a Jupyter notebook.

Runs the CLI as a subprocess (same code path as the command line - no
duplicated argument/DB logic) and loads the resulting CSV report(s) into
pandas DataFrames for display.

See notebooks/rowcount_compare.ipynb for worked examples.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = PROJECT_ROOT / "src" / "rowcount_compare.py"


@dataclass
class ComparisonResult:
    """Outcome of one run_comparison() call."""

    exit_code: int
    stdout: str
    stderr: str
    report: Optional[pd.DataFrame]
    differences: Optional[pd.DataFrame]


def load_env_file(path: "os.PathLike[str] | str" = PROJECT_ROOT / ".env") -> None:
    """Parse a .env-style file and set its variables into os.environ.

    Equivalent to the `set -a; source .env; set +a` step in the README, for
    notebooks where there's no shell to source it into first. Existing
    environment variables are left untouched (a var already set - e.g. by
    the notebook kernel's env - wins over the file).
    """
    env_path = Path(path)
    if not env_path.is_file():
        raise FileNotFoundError(f".env file not found: {env_path}")

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def run_comparison(
    *,
    tables_file: Optional[str] = None,
    table: Optional[str] = None,
    output_dir: str = "reports",
    db_a_schema: Optional[str] = None,
    db_b_schema: Optional[str] = None,
    db_a_prefix: str = "DB_A",
    db_b_prefix: str = "DB_B",
    log_level: str = "WARNING",
) -> ComparisonResult:
    """Run rowcount_compare.py and load its report(s) into DataFrames.

    Pass exactly one of tables_file or table, mirroring the CLI's
    --tables-file/--table split. Uses the current process's environment
    (so call load_env_file() first, or export vars into the kernel some
    other way) and the current working directory for a relative output_dir.
    """
    if (tables_file is None) == (table is None):
        raise ValueError("run_comparison requires exactly one of tables_file or table")

    argv = [sys.executable, str(CLI_PATH)]
    argv += ["--tables-file", tables_file] if tables_file else ["--table", table]
    argv += ["--output-dir", output_dir]
    argv += ["--db-a-prefix", db_a_prefix, "--db-b-prefix", db_b_prefix]
    if db_a_schema:
        argv += ["--db-a-schema", db_a_schema]
    if db_b_schema:
        argv += ["--db-b-schema", db_b_schema]
    argv += ["--log-level", log_level]

    proc = subprocess.run(argv, capture_output=True, text=True)

    out_path = Path(output_dir)
    report = _load_latest_csv(out_path, "rowcount_report_*.csv")
    differences = _load_latest_csv(out_path, "rowcount_differences_*.csv")
    # A setup/connection failure (exit code 2) writes no CSV at all - report
    # stays None rather than raising, so callers can still inspect
    # exit_code/stderr for what went wrong.
    return ComparisonResult(
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        report=report,
        differences=differences,
    )


def load_latest_reports(output_dir: str = "reports") -> tuple:
    """Load the most recent report/differences CSVs from output_dir, without re-running anything.

    Returns (report_df, differences_df); differences_df is None if no
    differences file exists for the latest run (i.e. everything matched).
    """
    out_path = Path(output_dir)
    report = _load_latest_csv(out_path, "rowcount_report_*.csv")
    if report is None:
        raise FileNotFoundError(f"No rowcount_report_*.csv found in {out_path}")
    differences = _load_latest_csv(out_path, "rowcount_differences_*.csv")
    return report, differences


def _load_latest_csv(output_dir: Path, pattern: str) -> Optional[pd.DataFrame]:
    if not output_dir.is_dir():
        return None
    matches = sorted(output_dir.glob(pattern))
    if not matches:
        return None
    return pd.read_csv(matches[-1])
