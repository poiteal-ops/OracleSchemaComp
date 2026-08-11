"""Compare row counts for a list of tables between two Oracle databases.

Connects to database A and database B and runs SELECT COUNT(*) per table on
each side, then writes a report.

Schema resolution, per table entry:
  1. An explicit OWNER.TABLE qualifier in the table list always wins.
  2. Otherwise, the --db-a-schema/--db-b-schema (or DB_A_SCHEMA/DB_B_SCHEMA
     env var) default is used, if given. A and B may use different schema
     names for what is logically "the same" table.
  3. Otherwise, the table name is unqualified and resolves against each
     connection's own default schema.

Assumptions:
  - Table and schema identifiers are standard unquoted Oracle identifiers
    (letters, digits, ``_``/``$``/``#``, starting with a letter). Quoted,
    mixed-case identifiers are out of scope.

Configuration (environment variables, see config/.env.example):
  DB_A_USERNAME, DB_A_PASSWORD, DB_A_DSN, DB_A_SCHEMA (optional)
  DB_B_USERNAME, DB_B_PASSWORD, DB_B_DSN, DB_B_SCHEMA (optional)

Usage:
  python rowcount_compare.py --tables-file tables.txt --output-dir reports
  python rowcount_compare.py --tables-file tables.txt --db-a-schema HR_PROD --db-b-schema HR_UAT
  python rowcount_compare.py --table HR.EMPLOYEES
  python rowcount_compare.py --whole-schema --db-a-schema HR_PROD --db-b-schema HR_UAT
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import oracledb
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / "config" / ".env"

# ORA error codes that are transient (worth a bounded retry) when establishing
# a connection. See references/python-analysis.md, "Connection pooling and retry".
_TRANSIENT_ORA_CODES = {3113, 3114, 12170, 12541, 12537, 25408}


@dataclass(frozen=True)
class DbConfig:
    """Oracle connection settings for one side of the comparison."""

    username: str
    password: str
    dsn: str
    label: str
    default_schema: Optional[str] = None


@dataclass(frozen=True)
class TableRef:
    """A validated table identifier, optionally schema-qualified."""

    raw: str
    owner: Optional[str]
    name: str


@dataclass
class TableCountResult:
    """Row-count outcome for one table on both sides."""

    table: str
    count_a: Optional[int] = None
    count_b: Optional[int] = None
    error_a: Optional[str] = None
    error_b: Optional[str] = None

    @property
    def status(self) -> str:
        if self.error_a or self.error_b:
            return "error"
        if self.count_a == self.count_b:
            return "match"
        return "mismatch"

    @property
    def delta(self) -> Optional[int]:
        if self.count_a is None or self.count_b is None:
            return None
        return self.count_b - self.count_a


def validate_schema_name(raw: str, label: str) -> str:
    """Validate a default-schema override; returns it uppercased."""
    text = raw.strip()
    if not _IDENTIFIER_RE.match(text):
        raise ValueError(f"Invalid schema name for {label}: {raw!r}")
    return text.upper()


def load_config(prefix: str, label: str, schema_override: Optional[str] = None) -> DbConfig:
    """Read <prefix>_USERNAME/_PASSWORD/_DSN from the environment.

    The default schema for unqualified table names is, in priority order,
    ``schema_override`` (typically a CLI flag), then the ``<prefix>_SCHEMA``
    environment variable, then None (connection's own default schema).
    """
    names = {
        "username": f"{prefix}_USERNAME",
        "password": f"{prefix}_PASSWORD",
        "dsn": f"{prefix}_DSN",
    }
    missing = [env_name for env_name in names.values() if not os.getenv(env_name)]
    if missing:
        raise RuntimeError(
            f"Missing environment variables for {label}: " + ", ".join(missing)
        )

    raw_schema = schema_override or os.getenv(f"{prefix}_SCHEMA")
    default_schema = validate_schema_name(raw_schema, label) if raw_schema else None

    return DbConfig(
        username=os.environ[names["username"]],
        password=os.environ[names["password"]],
        dsn=os.environ[names["dsn"]],
        label=label,
        default_schema=default_schema,
    )


def parse_table_ref(raw: str) -> TableRef:
    """Validate and split a possibly OWNER.TABLE identifier.

    Only plain unquoted Oracle identifiers are accepted, since the table
    name is interpolated into SQL (Oracle cannot bind identifiers) and must
    be safe to quote and use verbatim.
    """
    text = raw.strip()
    parts = text.split(".")
    if len(parts) == 1:
        owner, name = None, parts[0]
    elif len(parts) == 2:
        owner, name = parts
    else:
        raise ValueError(f"Invalid table identifier {raw!r}: expected TABLE or OWNER.TABLE")

    if owner is not None and not _IDENTIFIER_RE.match(owner):
        raise ValueError(f"Invalid owner identifier {raw!r}")
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid table identifier {raw!r}")

    return TableRef(raw=text, owner=owner, name=name)


def build_qualified_name(table_ref: TableRef, default_schema: Optional[str] = None) -> str:
    """Render a validated TableRef as safely quoted SQL text.

    An owner explicit in the table list always wins; otherwise falls back
    to ``default_schema`` (a per-connection default), then to no owner at
    all (the connection's own default schema).
    """
    name = f'"{table_ref.name.upper()}"'
    owner = table_ref.owner or default_schema
    if owner:
        return f'"{owner.upper()}".{name}'
    return name


def load_table_list(path: Path) -> list:
    """Read one table identifier per line; '#' starts a comment; dedupes, keeps order."""
    if not path.is_file():
        raise FileNotFoundError(f"Table list file not found: {path}")

    seen = set()
    tables = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            table_ref = parse_table_ref(line)
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
        key = table_ref.raw.upper()
        if key in seen:
            logger.warning("Duplicate table entry skipped: %s (line %d)", table_ref.raw, line_number)
            continue
        seen.add(key)
        tables.append(table_ref)

    if not tables:
        raise ValueError(f"No table identifiers found in {path}")
    return tables


def merge_discovered_objects(names_a: list[str], names_b: list[str]) -> list[TableRef]:
    """Merge discovered names, skipping identifiers this tool cannot address safely."""
    seen = set()
    tables = []
    for name in [*names_a, *names_b]:
        try:
            if name != name.upper():
                raise ValueError("quoted or mixed-case identifiers are unsupported")
            table = parse_table_ref(name)
        except ValueError as exc:
            logger.warning("Discovered object skipped: %r (%s)", name, exc)
            continue
        key = table.raw.upper()
        if key not in seen:
            seen.add(key)
            tables.append(table)

    if not tables:
        raise ValueError("No valid objects discovered across either schema")
    return sorted(tables, key=lambda table: table.raw.upper())


def is_transient_ora_error(error: "oracledb.Error") -> bool:
    args = error.args
    if not args:
        return False
    code = getattr(args[0], "code", None)
    return code in _TRANSIENT_ORA_CODES


def connect_with_retry(config: DbConfig, max_attempts: int = 3) -> "oracledb.Connection":
    """Open a connection, retrying only on transient ORA errors."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return oracledb.connect(user=config.username, password=config.password, dsn=config.dsn)
        except oracledb.Error as exc:
            if attempt >= max_attempts or not is_transient_ora_error(exc):
                logger.error("Connection to %s failed on attempt %d: %s", config.label, attempt, exc)
                raise
            backoff = 0.5 * (2 ** (attempt - 1))
            logger.warning(
                "Transient error connecting to %s (attempt %d/%d): %s; retrying in %.1fs",
                config.label, attempt, max_attempts, exc, backoff,
            )
            time.sleep(backoff)


def get_row_count(
    connection: "oracledb.Connection",
    table_ref: TableRef,
    default_schema: Optional[str] = None,
) -> int:
    qualified_name = build_qualified_name(table_ref, default_schema)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {qualified_name}")  # noqa: S608 - identifier validated/quoted above
        row = cursor.fetchone()
    return int(row[0])


def discover_schema_objects(
    connection: "oracledb.Connection",
    owner: str,
) -> list[str]:
    """Return accessible tables, views, and materialized views for an owner."""
    sql = """
        SELECT table_name AS object_name
        FROM all_tables tables_found
        WHERE owner = :owner
          AND NOT EXISTS (
              SELECT 1
              FROM all_mviews mviews_for_tables
              WHERE mviews_for_tables.owner = tables_found.owner
                AND mviews_for_tables.container_name = tables_found.table_name
          )
        UNION
        SELECT view_name AS object_name
        FROM all_views
        WHERE owner = :owner
        UNION
        SELECT mview_name AS object_name
        FROM all_mviews
        WHERE owner = :owner
        ORDER BY object_name
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, owner=owner)
        rows = cursor.fetchall()
    return [row[0] for row in rows]


def compare_row_counts(
    connection_a: "oracledb.Connection",
    connection_b: "oracledb.Connection",
    tables: list,
    run_id: str,
    schema_a: Optional[str] = None,
    schema_b: Optional[str] = None,
) -> list:
    """Get the row count for each table on both sides; one failure never aborts the scan."""
    results = []
    for table_ref in tables:
        result = TableCountResult(table=table_ref.raw)
        try:
            result.count_a = get_row_count(connection_a, table_ref, schema_a)
        except oracledb.Error as exc:
            result.error_a = str(exc).strip()
            logger.error("run=%s side=A table=%s error=%s", run_id, table_ref.raw, result.error_a)
        try:
            result.count_b = get_row_count(connection_b, table_ref, schema_b)
        except oracledb.Error as exc:
            result.error_b = str(exc).strip()
            logger.error("run=%s side=B table=%s error=%s", run_id, table_ref.raw, result.error_b)

        logger.info(
            "run=%s table=%s count_a=%s count_b=%s status=%s",
            run_id, table_ref.raw, result.count_a, result.count_b, result.status,
        )
        results.append(result)
    return sorted(results, key=lambda r: r.table.upper())


def write_report(results: list, path: Path, run_id: str, generated_at: str) -> None:
    fieldnames = [
        "run_id", "generated_at", "table", "count_a", "count_b", "delta",
        "status", "error_a", "error_b",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({
                "run_id": run_id,
                "generated_at": generated_at,
                "table": result.table,
                "count_a": result.count_a,
                "count_b": result.count_b,
                "delta": result.delta,
                "status": result.status,
                "error_a": result.error_a,
                "error_b": result.error_b,
            })


def print_summary(results: list) -> None:
    matches = [r for r in results if r.status == "match"]
    mismatches = [r for r in results if r.status == "mismatch"]
    errors = [r for r in results if r.status == "error"]

    print(f"Tables compared: {len(results)}")
    print(f"  Match:    {len(matches)}")
    print(f"  Mismatch: {len(mismatches)}")
    print(f"  Error:    {len(errors)}")

    if mismatches:
        print("\nRow-count differences:")
        for r in mismatches:
            print(f"  {r.table}: A={r.count_a} B={r.count_b} delta={r.delta}")

    if errors:
        print("\nTables that could not be counted on one or both sides:")
        for r in errors:
            detail = r.error_a or r.error_b
            print(f"  {r.table}: {detail}")


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    table_source = parser.add_mutually_exclusive_group(required=True)
    table_source.add_argument("--tables-file", type=Path, help="File with one table name (or OWNER.TABLE) per line")
    table_source.add_argument("--table", help="Compare a single table (TABLE_NAME or OWNER.TABLE_NAME) instead of a whole file list")
    table_source.add_argument(
        "--whole-schema",
        action="store_true",
        help="Discover and compare all tables, views, and materialized views in both schemas",
    )
    parser.add_argument("--output-dir", default=Path("reports"), type=Path, help="Directory to write report CSVs into")
    parser.add_argument("--db-a-prefix", default="DB_A", help="Env var prefix for database A (default: DB_A)")
    parser.add_argument("--db-b-prefix", default="DB_B", help="Env var prefix for database B (default: DB_B)")
    parser.add_argument(
        "--db-a-schema",
        default=None,
        help="Default schema/owner for unqualified table names on database A "
             "(falls back to DB_A_SCHEMA env var, then the connection's own default schema)",
    )
    parser.add_argument(
        "--db-b-schema",
        default=None,
        help="Default schema/owner for unqualified table names on database B "
             "(falls back to DB_B_SCHEMA env var, then the connection's own default schema)",
    )
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    load_dotenv(_ENV_FILE, override=False)
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    generated_at = datetime.now().isoformat(timespec="seconds")

    try:
        config_a = load_config(args.db_a_prefix, "A", args.db_a_schema)
        config_b = load_config(args.db_b_prefix, "B", args.db_b_schema)
        if args.whole_schema:
            if not config_a.default_schema or not config_b.default_schema:
                raise RuntimeError(
                    "--whole-schema requires an explicit schema for both database A and B"
                )
            tables = None
        else:
            tables = [parse_table_ref(args.table)] if args.table else load_table_list(args.tables_file)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        logger.critical("Setup failed: %s", exc)
        return 2

    logger.info(
        "run=%s tables=%s schema_a=%s schema_b=%s starting comparison",
        run_id, len(tables) if tables is not None else "pending discovery",
        config_a.default_schema, config_b.default_schema,
    )

    try:
        with connect_with_retry(config_a) as connection_a, connect_with_retry(config_b) as connection_b:
            if args.whole_schema:
                try:
                    names_a = discover_schema_objects(connection_a, config_a.default_schema)
                    names_b = discover_schema_objects(connection_b, config_b.default_schema)
                    tables = merge_discovered_objects(names_a, names_b)
                except ValueError as exc:
                    logger.critical("run=%s schema discovery failed: %s", run_id, exc)
                    return 2
            results = compare_row_counts(
                connection_a, connection_b, tables, run_id,
                schema_a=config_a.default_schema, schema_b=config_b.default_schema,
            )
    except oracledb.Error as exc:
        logger.critical("run=%s connection or schema discovery failed: %s", run_id, exc)
        return 2

    full_report_path = args.output_dir / f"rowcount_report_{run_id}.csv"
    write_report(results, full_report_path, run_id, generated_at)
    logger.info("run=%s wrote full report to %s", run_id, full_report_path)

    differences = [r for r in results if r.status != "match"]
    if differences:
        diff_report_path = args.output_dir / f"rowcount_differences_{run_id}.csv"
        write_report(differences, diff_report_path, run_id, generated_at)
        logger.info("run=%s wrote %d differences to %s", run_id, len(differences), diff_report_path)

    print_summary(results)
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
