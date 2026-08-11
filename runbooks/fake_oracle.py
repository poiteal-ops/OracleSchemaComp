"""A minimal fake Oracle driver used by runbook scenarios.

Lets a scenario run rowcount_compare.main() end-to-end - real argument
parsing, real SQL string building, real report writing - without a live
Oracle database. Only the oracledb.connect() call is replaced; everything
downstream of it runs unmodified.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional, TypedDict
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import oracledb  # noqa: E402

import rowcount_compare  # noqa: E402


class FakeOracleError(oracledb.Error):
    """Stand-in for a real ORA error, e.g. a table missing on one side."""


class SchemaInventory(TypedDict):
    tables: List[str]
    views: List[str]
    mviews: Dict[str, str]


class FakeCursor:
    """Answers row-count and schema-discovery queries from canned data."""

    def __init__(
        self,
        table_counts: Dict[str, int],
        schema_objects: Dict[str, SchemaInventory],
    ) -> None:
        self._table_counts = table_counts
        self._schema_objects = schema_objects
        self._result = None
        self._rows = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def execute(self, sql: str, **parameters: str) -> None:
        if "ALL_TABLES" in sql.upper():
            upper_sql = sql.upper()
            required_fragments = ("ALL_VIEWS", "ALL_MVIEWS", "NOT EXISTS", "CONTAINER_NAME")
            missing = [fragment for fragment in required_fragments if fragment not in upper_sql]
            if missing:
                raise FakeOracleError(
                    "discovery query missing required SQL: " + ", ".join(missing)
                )
            owner = parameters["owner"]
            inventory = self._schema_objects.get(
                owner, {"tables": [], "views": [], "mviews": {}}
            )
            containers = set(inventory["mviews"].values())
            names = (
                {name for name in inventory["tables"] if name not in containers}
                | set(inventory["views"])
                | set(inventory["mviews"])
            )
            self._rows = [(name,) for name in sorted(names)]
            return

        qualified = sql.split("FROM ", 1)[1].strip()
        key = qualified.replace('"', "")
        if key not in self._table_counts:
            raise FakeOracleError(f"ORA-00942: table or view does not exist: {key}")
        self._result = self._table_counts[key]

    def fetchone(self) -> tuple:
        return (self._result,)

    def fetchall(self) -> List[tuple]:
        return self._rows or []


class FakeConnection:
    def __init__(
        self,
        table_counts: Dict[str, int],
        schema_objects: Dict[str, SchemaInventory],
    ) -> None:
        self._table_counts = table_counts
        self._schema_objects = schema_objects

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._table_counts, self._schema_objects)

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


@contextmanager
def fake_oracle(
    dsn_to_counts: Dict[str, Dict[str, int]],
    dsn_to_schema_objects: Optional[Dict[str, Dict[str, SchemaInventory]]] = None,
) -> Iterator[None]:
    """Patch rowcount_compare.oracledb.connect for the duration of the with-block.

    dsn_to_counts maps a fake DSN string to the {"OWNER.TABLE": row_count}
    dict that side should answer with.
    """

    def fake_connect(user: str, password: str, dsn: str) -> FakeConnection:
        if dsn not in dsn_to_counts:
            raise FakeOracleError(f"unexpected dsn in runbook: {dsn}")
        schema_objects = (dsn_to_schema_objects or {}).get(dsn, {})
        return FakeConnection(dsn_to_counts[dsn], schema_objects)

    with mock.patch.object(rowcount_compare.oracledb, "connect", side_effect=fake_connect):
        yield
