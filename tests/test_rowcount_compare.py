from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rowcount_compare import (  # noqa: E402
    TableCountResult,
    build_qualified_name,
    load_table_list,
    merge_discovered_objects,
    parse_args,
    parse_table_ref,
    validate_schema_name,
)


def test_parse_table_ref_unqualified():
    ref = parse_table_ref("employees")
    assert ref.owner is None
    assert ref.name == "employees"


def test_parse_table_ref_qualified():
    ref = parse_table_ref("HR.EMPLOYEES")
    assert ref.owner == "HR"
    assert ref.name == "EMPLOYEES"


@pytest.mark.parametrize(
    "raw",
    ["1BAD", "bad-name", "a.b.c", "", "with space", "drop table;"],
)
def test_parse_table_ref_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_table_ref(raw)


def test_build_qualified_name_unqualified():
    ref = parse_table_ref("employees")
    assert build_qualified_name(ref) == '"EMPLOYEES"'


def test_build_qualified_name_qualified():
    ref = parse_table_ref("hr.employees")
    assert build_qualified_name(ref) == '"HR"."EMPLOYEES"'


def test_build_qualified_name_uses_default_schema_when_unqualified():
    ref = parse_table_ref("employees")
    assert build_qualified_name(ref, default_schema="HR_PROD") == '"HR_PROD"."EMPLOYEES"'


def test_build_qualified_name_explicit_owner_overrides_default_schema():
    ref = parse_table_ref("hr.employees")
    assert build_qualified_name(ref, default_schema="OTHER") == '"HR"."EMPLOYEES"'


def test_validate_schema_name_normalizes_case():
    assert validate_schema_name("hr_prod", "A") == "HR_PROD"


def test_validate_schema_name_rejects_invalid():
    with pytest.raises(ValueError):
        validate_schema_name("bad-schema", "A")


def test_load_table_list_skips_blanks_and_comments(tmp_path):
    path = tmp_path / "tables.txt"
    path.write_text(
        "\n".join([
            "# comment line",
            "HR.EMPLOYEES",
            "",
            "  HR.DEPARTMENTS  # inline comment",
            "HR.EMPLOYEES",  # duplicate, should be skipped
        ]),
        encoding="utf-8",
    )
    tables = load_table_list(path)
    assert [t.raw for t in tables] == ["HR.EMPLOYEES", "HR.DEPARTMENTS"]


def test_load_table_list_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_table_list(tmp_path / "does_not_exist.txt")


def test_load_table_list_empty_file_raises(tmp_path):
    path = tmp_path / "tables.txt"
    path.write_text("# only comments\n\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_table_list(path)


def test_load_table_list_invalid_identifier_reports_line(tmp_path):
    path = tmp_path / "tables.txt"
    path.write_text("HR.EMPLOYEES\nbad-name\n", encoding="utf-8")
    with pytest.raises(ValueError, match="tables.txt:2"):
        load_table_list(path)


def test_merge_discovered_objects_unions_dedupes_and_sorts():
    tables = merge_discovered_objects(
        ["EMPLOYEES", "ACTIVE_EMPLOYEES", "SHARED_OBJECT"],
        ["DEPARTMENT_TOTALS", "SHARED_OBJECT", "EMPLOYEES"],
    )
    assert [table.raw for table in tables] == [
        "ACTIVE_EMPLOYEES",
        "DEPARTMENT_TOTALS",
        "EMPLOYEES",
        "SHARED_OBJECT",
    ]


def test_merge_discovered_objects_empty_union_raises():
    with pytest.raises(ValueError, match="No valid objects"):
        merge_discovered_objects([], [])


def test_merge_discovered_objects_skips_unsupported_identifiers(caplog):
    with caplog.at_level("WARNING"):
        tables = merge_discovered_objects(
            ["EMPLOYEES", "MixedCase"],
            ['NAME WITH SPACE', "EMPLOYEES"],
        )

    assert [table.raw for table in tables] == ["EMPLOYEES"]
    assert "MixedCase" in caplog.text
    assert "NAME WITH SPACE" in caplog.text


def test_invalid_name_on_one_side_does_not_hide_valid_name_on_other(caplog):
    with caplog.at_level("WARNING"):
        tables = merge_discovered_objects(["MixedCase"], ["MIXEDCASE"])

    assert [table.raw for table in tables] == ["MIXEDCASE"]
    assert "MixedCase" in caplog.text


def test_status_match():
    result = TableCountResult(table="T", count_a=10, count_b=10)
    assert result.status == "match"
    assert result.delta == 0


def test_status_mismatch():
    result = TableCountResult(table="T", count_a=10, count_b=12)
    assert result.status == "mismatch"
    assert result.delta == 2


def test_status_error_takes_priority():
    result = TableCountResult(table="T", count_a=10, count_b=10, error_b="ORA-00942: table or view does not exist")
    assert result.status == "error"


def test_delta_none_when_a_side_errored():
    result = TableCountResult(table="T", count_a=None, count_b=10, error_a="boom")
    assert result.delta is None


def test_parse_args_accepts_single_table():
    args = parse_args(["--table", "HR.EMPLOYEES"])
    assert args.table == "HR.EMPLOYEES"
    assert args.tables_file is None


def test_parse_args_accepts_tables_file():
    args = parse_args(["--tables-file", "tables.txt"])
    assert args.tables_file == Path("tables.txt")
    assert args.table is None


def test_parse_args_accepts_whole_schema():
    args = parse_args(["--whole-schema"])
    assert args.whole_schema is True
    assert args.table is None
    assert args.tables_file is None


def test_parse_args_requires_a_table_source(capsys):
    with pytest.raises(SystemExit):
        parse_args([])
    assert "required" in capsys.readouterr().err


def test_parse_args_rejects_both_table_sources(capsys):
    with pytest.raises(SystemExit):
        parse_args(["--tables-file", "tables.txt", "--table", "HR.EMPLOYEES"])
    assert "not allowed" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--whole-schema", "--table", "HR.EMPLOYEES"],
        ["--whole-schema", "--tables-file", "tables.txt"],
    ],
)
def test_parse_args_rejects_whole_schema_with_another_source(argv, capsys):
    with pytest.raises(SystemExit):
        parse_args(argv)
    assert "not allowed" in capsys.readouterr().err
