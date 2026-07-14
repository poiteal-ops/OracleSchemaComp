# OracleSchemaComp

Compares row counts for a given list of tables between two Oracle databases
("A" and "B"). Every table is reported; tables whose counts differ (or that
error out on one side) are additionally written to a separate differences
report.

Requires Python 3.9+.

## Project structure

```
src/rowcount_compare.py   Main program
tests/                     Unit tests (pytest) for pure logic - no DB required
runbooks/                  Executable integration scenarios against a fake
                           Oracle driver - no DB required
notebooks/                 Jupyter notebook + helper for interactive use -
                           requires a live DB, see "Notebook" below
tables.example.txt         Example table list
.env.example               Example environment configuration
requirements.txt           oracledb (runtime) + pytest (dev/test) + pandas
                           (notebook)
```

## Install

```
pip install -r requirements.txt
```

`pandas` is only needed for `notebooks/`; Jupyter/JupyterLab itself isn't
pinned here - install whichever you already use.

## Configure

Copy `.env.example` to `.env` and fill in real values (or export the same
variables in your shell/CI):

```
DB_A_USERNAME=...
DB_A_PASSWORD=...
DB_A_DSN=...            # host:port/service_name, easy-connect string, or tnsnames alias
DB_A_SCHEMA=            # optional, see "Schema resolution" below

DB_B_USERNAME=...
DB_B_PASSWORD=...
DB_B_DSN=...
DB_B_SCHEMA=
```

Never commit a filled-in `.env` file.

## Table selection

Give either a whole list of tables or a single table - they're mutually
exclusive:

- `--tables-file tables.txt` - a file with one table per line (see below).
- `--table HR.EMPLOYEES` - compare just that one table, no file needed.

## Table list

For `--tables-file`: one table per line in a text file (see
`tables.example.txt`). Blank lines and `#` comments are ignored.

```
EMPLOYEES
HR.DEPARTMENTS
SALES.ORDERS
```

Format is `TABLE_NAME` or `OWNER.TABLE_NAME`. Only plain unquoted Oracle
identifiers are accepted (table names are interpolated into SQL, since
Oracle cannot bind identifiers as parameters).

### Schema resolution

Per table entry, in priority order:

1. An explicit `OWNER.TABLE` qualifier in the table list always wins.
2. Otherwise, `--db-a-schema` / `--db-b-schema` (or the `DB_A_SCHEMA` /
   `DB_B_SCHEMA` env vars) is used, if set. A and B can use **different**
   schema names for what is logically the same table.
3. Otherwise, the table name is unqualified and resolves against each
   connection's own default schema.

## Run

```
python src/rowcount_compare.py --tables-file tables.example.txt --output-dir reports
```

A single table, without a table-list file:

```
python src/rowcount_compare.py --table HR.EMPLOYEES
```

With per-side default schemas, e.g. the same tables living under different
schema names in each environment:

```
python src/rowcount_compare.py --tables-file tables.example.txt \
    --db-a-schema HR_PROD --db-b-schema HR_UAT
```

Full option list: `python src/rowcount_compare.py --help`.

## Output

Two CSVs are written to `--output-dir` (default `reports/`), timestamped by
run:

- `rowcount_report_<run_id>.csv` - every table compared, always written.
- `rowcount_differences_<run_id>.csv` - only tables with status `mismatch`
  or `error`; written only if at least one exists.

Columns: `run_id, generated_at, table, count_a, count_b, delta, status,
error_a, error_b`. `delta` is `count_b - count_a`. `status` is one of
`match`, `mismatch`, `error` (a count couldn't be obtained on one or both
sides - e.g. the table doesn't exist there - which never aborts the rest of
the scan).

A console summary is also printed.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Every table matched |
| 1 | At least one mismatch or error |
| 2 | Setup failure - missing config, bad table list, or couldn't connect |

## Notebook

For interactive use, `notebooks/rowcount_compare.ipynb` runs the same CLI as a
subprocess and loads its CSV reports into pandas DataFrames. `notebooks/helper.py`
is the module behind it (`load_env_file`, `run_comparison`, `load_latest_reports`) -
no DB logic is duplicated, it just drives `src/rowcount_compare.py` and reads its
output. Requires `pandas` (see Install above) and, like the CLI, a live Oracle
connection - unlike `tests/`/`runbooks/`, it is not covered by the fake driver.

```
jupyter lab notebooks/rowcount_compare.ipynb
```

## Testing

Two independent layers, neither needs a live database:

- **Unit tests** (`tests/`) - pure logic: identifier validation/parsing,
  table-list loading, status/delta calculation.

  ```
  python -m pytest tests/
  ```

- **Runbooks** (`runbooks/`) - integration scenarios that run the full
  program end-to-end (real CLI parsing, real SQL building, real report
  writing) against a fake Oracle driver (`runbooks/fake_oracle.py`) that
  answers `SELECT COUNT(*)` from an in-memory dict instead of a real
  connection. Each scenario is a self-contained, narrated script; run them
  all or one at a time:

  ```
  python runbooks/run_all.py
  python runbooks/scenario_mismatched_row_counts.py
  ```

  Scenarios covered: all tables match, a table mismatches, a table is
  missing on one side (error path, and proves one failure doesn't abort the
  scan), per-side default schema resolution, and comparing a single table
  via `--table` instead of a table-list file.

## Examples

### Connection setup

Copy `.env.example` to `.env`:

```
cp .env.example .env
```

Fill it in for two named environments, e.g. comparing production to UAT:

```
DB_A_USERNAME=hr_reader
DB_A_PASSWORD=change_me
DB_A_DSN=prod-db.example.com:1521/HRPROD
DB_A_SCHEMA=HR_PROD

DB_B_USERNAME=hr_reader
DB_B_PASSWORD=change_me
DB_B_DSN=uat-db.example.com:1521/HRUAT
DB_B_SCHEMA=HR_UAT
```

Load it into your shell before running the script (bash/zsh):

```
set -a; source .env; set +a
```

PowerShell:

```
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
}
```

Or export the same variables directly in CI (e.g. GitHub Actions `env:` /
`secrets:`) instead of using a `.env` file at all.

You can compare more than one pair of environments without editing `.env` by
using alternate prefixes and `--db-a-prefix`/`--db-b-prefix`:

```
DEV_USERNAME=...
DEV_PASSWORD=...
DEV_DSN=dev-db.example.com:1521/HRDEV

QA_USERNAME=...
QA_PASSWORD=...
QA_DSN=qa-db.example.com:1521/HRQA
```

```
python src/rowcount_compare.py --tables-file tables.example.txt \
    --db-a-prefix DEV --db-b-prefix QA
```

### CLI examples

Compare a whole table list, writing reports to the default `reports/` directory:

```
python src/rowcount_compare.py --tables-file tables.example.txt
```

Compare a whole table list, writing reports to a custom directory:

```
python src/rowcount_compare.py --tables-file tables.example.txt --output-dir out/2026-07-13
```

Compare just one table, no table-list file needed:

```
python src/rowcount_compare.py --table HR.EMPLOYEES
```

Same source/target tables, but they live under different schema names in
each environment (e.g. `HR_PROD` vs `HR_UAT`):

```
python src/rowcount_compare.py --tables-file tables.example.txt \
    --db-a-schema HR_PROD --db-b-schema HR_UAT
```

The connecting user is rarely the schema owner - e.g. a read-only account
`hr_reader` querying tables it doesn't own. `--db-a-schema`/`--db-b-schema`
qualify every unqualified table name with that owner, so `hr_reader` only
needs `SELECT` granted on the target tables, nothing more:

```
python src/rowcount_compare.py --tables-file tables.example.txt \
    --db-a-schema HR_PROD --db-b-schema HR_PROD
```

Same idea via env vars instead of flags (handy when the schema doesn't
change run to run, e.g. in `.env` or CI `env:`) - `--db-a-schema` still wins
if both are set:

```
DB_A_SCHEMA=HR_PROD
DB_B_SCHEMA=HR_PROD
```

```
python src/rowcount_compare.py --tables-file tables.example.txt
```

Mixing a default schema with a one-off exception: everything in the file
resolves against `--db-a-schema`/`--db-b-schema` *except* rows already
qualified as `OWNER.TABLE`, which always win regardless of the flags. Given a
`tables.txt` of:

```
EMPLOYEES
DEPARTMENTS
FINANCE.INVOICES
```

```
python src/rowcount_compare.py --tables-file tables.txt \
    --db-a-schema HR_PROD --db-b-schema HR_UAT
```

`EMPLOYEES`/`DEPARTMENTS` resolve to `HR_PROD.*`/`HR_UAT.*`; `FINANCE.INVOICES`
resolves to `FINANCE.INVOICES` unchanged on both sides.

Comparing more than one schema pair from the same table list isn't supported
in a single run - `--db-a-schema`/`--db-b-schema` apply to the whole list, so
split into separate table-list files (or runs) per schema pair instead.

Increase log verbosity for troubleshooting a connection or a specific table:

```
python src/rowcount_compare.py --table HR.EMPLOYEES --log-level DEBUG
```

Use in a CI pipeline - the script's own exit code (0/1/2, see "Exit codes"
above) already fails the step on any mismatch, error, or setup problem, so
no extra `||` handling is needed:

```
python src/rowcount_compare.py --tables-file tables.example.txt --output-dir reports
```

Full option list:

```
python src/rowcount_compare.py --help
```

### Runbook examples

Run every scenario in one go:

```
python runbooks/run_all.py
```

Run a single scenario directly, e.g. to see the mismatch-detection path in isolation:

```
python runbooks/scenario_mismatched_row_counts.py
```

Available scenarios:

| Script | What it proves |
|---|---|
| `scenario_matching_row_counts.py` | All tables match; exit code 0; no differences report written |
| `scenario_mismatched_row_counts.py` | One table's counts differ; exit code 1; delta computed correctly |
| `scenario_missing_table.py` | A table is missing on one side (ORA-00942-style error); reported as `status=error` without aborting the rest of the scan |
| `scenario_per_side_schema.py` | `--db-a-schema`/`--db-b-schema` resolve an unqualified table name differently per side, while an explicit `OWNER.TABLE` entry ignores the defaults |
| `scenario_single_table.py` | `--table` compares one table without a `--tables-file` |

Each scenario is self-contained (sets up fake env vars and a fake Oracle
driver, runs `rowcount_compare.main()` end-to-end, asserts on the exit code
and report contents, and prints a narrated `PASS`/failure) - read one as a
worked example of a specific behavior.

## Troubleshooting

- **Setup failure (exit 2), "Missing environment variables"** - the
  `DB_A_*`/`DB_B_*` env vars (or the `--db-a-prefix`/`--db-b-prefix` you
  passed) aren't set. Check `.env` is loaded into the shell running the
  script.
- **A table shows `status=error`** - see `error_a`/`error_b` in the CSV for
  the underlying ORA error. Common cause: the table doesn't exist under the
  schema being used on that side - check the "Schema resolution" section
  above.
- **Setup failure, "Invalid table identifier"** - the table list contains
  something other than a plain `TABLE` or `OWNER.TABLE` entry (e.g. a
  quoted or mixed-case identifier); the error names the file and line
  number.
