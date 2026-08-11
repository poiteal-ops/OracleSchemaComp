# OracleSchemaComp

Compares row counts for a given list of tables between two Oracle databases
("A" and "B"). Every table is reported; tables whose counts differ (or that
error out on one side) are additionally written to a separate differences
report.

Requires Python 3.12+.

## Project structure

```
src/rowcount_compare.py   Main program
tests/                     Unit tests (pytest) for pure logic - no DB required
runbooks/                  Executable integration scenarios against a fake
                           Oracle driver - no DB required
notebooks/                 Runnable fake/live comparison walkthrough
config/tables.example.txt  Example table list
config/.env.example        Example environment configuration
requirements.txt           Runtime dependencies + test/notebook tooling
```

## Install

```powershell
python3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Configure

Copy `config/.env.example` to `config/.env` and fill in real values. The
program loads this file automatically; variables already exported by your
shell or CI take precedence.

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

Choose exactly one comparison mode:

- `--tables-file config/tables.txt` - a file with one table per line (see below).
- `--table HR.EMPLOYEES` - compare just that one table, no file needed.
- `--whole-schema` - discover and compare all accessible tables, views, and
  materialized views in both schemas. This mode requires an explicit schema
  for each side.

## Table list

For `--tables-file`: one table per line in a text file (see
`config/tables.example.txt`). Blank lines and `#` comments are ignored.

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

For `--whole-schema`, step 3 does not apply: both schemas must be supplied via
`--db-a-schema`/`--db-b-schema` or `DB_A_SCHEMA`/`DB_B_SCHEMA`.

## Run

### With `.venv` activated

If your PowerShell prompt starts with `(.venv)`, the virtual environment is
already active. Run a full-schema comparison with:

```powershell
python .\src\rowcount_compare.py --whole-schema
```

### Without activating `.venv`

Call the virtual environment's Python executable directly:

```powershell
.\.venv\Scripts\python.exe .\src\rowcount_compare.py --whole-schema
```

Both forms automatically load connection settings from `config/.env`. Reports
are written to `reports/` unless you provide `--output-dir`.

### Other comparison modes

Compare a table list:

```powershell
python .\src\rowcount_compare.py --tables-file config/tables.example.txt --output-dir reports
```

A single table, without a table-list file:

```powershell
python .\src\rowcount_compare.py --table HR.EMPLOYEES
```

With per-side default schemas, e.g. the same tables living under different
schema names in each environment:

```powershell
python .\src\rowcount_compare.py --tables-file config/tables.example.txt `
    --db-a-schema HR_PROD --db-b-schema HR_UAT
```

Full option list: `python .\src\rowcount_compare.py --help`.

Discover and compare whole schemas with different owner names:

```powershell
python .\src\rowcount_compare.py --whole-schema `
    --db-a-schema HR_PROD --db-b-schema HR_UAT
```

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
| 2 | Setup failure - missing config/schema, bad table list, connection failure, or schema discovery failure |

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
  via `--table` instead of a table-list file, plus whole-schema discovery.

## Notebook

Open `notebooks/oracle_schema_comparison.ipynb` in VS Code or an existing
Jupyter frontend and select the interpreter at `.venv\Scripts\python.exe`.
If JupyterLab is already installed on your machine, you can launch it with:

```powershell
jupyter lab notebooks/oracle_schema_comparison.ipynb
```

The fake demonstration runs without Oracle access. The live execution cell is
disabled by default; it reads credentials only from exported environment
variables or the ignored `config/.env` file. Review the displayed argument list
before setting `RUN_LIVE_COMPARISON = True`. Generated reports can expose schema
object names and Oracle errors, so keep their output directory ignored or
access-controlled.

## Examples

### Connection setup

Copy `config/.env.example` to `config/.env`:

```
Copy-Item config/.env.example config/.env
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

Local runs load `config/.env` automatically. If you prefer to export variables
explicitly (for example in CI), bash/zsh can load the same file with:

```
set -a; source config/.env; set +a
```

PowerShell:

```
Get-Content config/.env | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
}
```

Or export the same variables directly in CI (e.g. GitHub Actions `env:` /
`secrets:`) instead of using a `.env` file at all.

You can compare more than one pair of environments without editing the file by
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
python src/rowcount_compare.py --tables-file config/tables.example.txt \
    --db-a-prefix DEV --db-b-prefix QA
```

### CLI examples

Compare a whole table list, writing reports to the default `reports/` directory:

```
python src/rowcount_compare.py --tables-file config/tables.example.txt
```

Compare a whole table list, writing reports to a custom directory:

```
python src/rowcount_compare.py --tables-file config/tables.example.txt --output-dir out/2026-07-13
```

Compare just one table, no table-list file needed:

```
python src/rowcount_compare.py --table HR.EMPLOYEES
```

Same source/target tables, but they live under different schema names in
each environment (e.g. `HR_PROD` vs `HR_UAT`):

```
python src/rowcount_compare.py --tables-file config/tables.example.txt \
    --db-a-schema HR_PROD --db-b-schema HR_UAT
```

Increase log verbosity for troubleshooting a connection or a specific table:

```
python src/rowcount_compare.py --table HR.EMPLOYEES --log-level DEBUG
```

Discover all supported objects in two explicitly named schemas:

```
python src/rowcount_compare.py --whole-schema \
    --db-a-schema HR_PROD --db-b-schema HR_UAT
```

Use in a CI pipeline - the script's own exit code (0/1/2, see "Exit codes"
above) already fails the step on any mismatch, error, or setup problem, so
no extra `||` handling is needed:

```
python src/rowcount_compare.py --tables-file config/tables.example.txt --output-dir reports
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
| `scenario_whole_schema.py` | Discovers tables, views, and materialized views from both schemas; unions names and reports an object missing on one side as an error |

Each scenario is self-contained (sets up fake env vars and a fake Oracle
driver, runs `rowcount_compare.main()` end-to-end, asserts on the exit code
and report contents, and prints a narrated `PASS`/failure) - read one as a
worked example of a specific behavior.

## Troubleshooting

- **Setup failure (exit 2), "Missing environment variables"** - the
  `DB_A_*`/`DB_B_*` env vars (or the `--db-a-prefix`/`--db-b-prefix` you
  passed) aren't set. Check `config/.env` exists and contains the expected
  names, or check the environment exported by the calling shell/CI process.
- **Setup failure (exit 2), "--whole-schema requires an explicit schema"** -
  set both `DB_A_SCHEMA` and `DB_B_SCHEMA`, or pass both schema flags.
- **Schema discovery found no valid objects** - verify the owner names and the
  connecting users' visibility in `ALL_TABLES`, `ALL_VIEWS`, and `ALL_MVIEWS`.
  Prefer direct least-privilege grants for the objects being compared; do not
  grant broad catalog access solely to make this tool work without a security
  review.
- **A table shows `status=error`** - see `error_a`/`error_b` in the CSV for
  the underlying ORA error. Common cause: the table doesn't exist under the
  schema being used on that side - check the "Schema resolution" section
  above.
- **Setup failure, "Invalid table identifier"** - the table list contains
  something other than a plain `TABLE` or `OWNER.TABLE` entry (for example,
  a quoted identifier or one containing spaces); the error names the file
  and line number. Input case is normalized for ordinary unquoted names,
  but case-sensitive quoted Oracle identifiers are unsupported.
