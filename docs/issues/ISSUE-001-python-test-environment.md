---
id: ISSUE-001
status: closed
priority: medium
area: tooling
created: 2026-08-11
updated: 2026-08-11
---

## Summary

The system Python could not collect the test suite because `oracledb` was not
installed. After installing the declared dependencies, pytest also could not use
its default temporary directory because the sandbox denied access.

## Evidence

- `python -m pytest tests/` failed with `ModuleNotFoundError: No module named 'oracledb'`.
- The first venv run failed with `PermissionError: [WinError 5]` for
  `C:\Users\Alain\AppData\Local\Temp\pytest-of-Alain`.
- Pointing `--basetemp` at a missing nested directory first failed with
  `FileNotFoundError: [WinError 3]`; pytest does not create the parent directory.
- Python 3.14.3 was available through `C:\Users\Alain\.local\bin\python3.14.exe`,
  although the Windows `py` launcher did not list it.

## Impact

Tests could not establish a trustworthy baseline until the local environment was
bootstrapped and pytest used a writable temporary location.

## Acceptance criteria

The complete existing test suite runs under the project `.venv` and reports zero
failures or errors.

## Related work

The dependency set comes from `requirements.txt`. Packages were downloaded from
PyPI into the project-local `.venv`; deleting `.venv` removes the installation.
The scope change also added `python-dotenv` 1.2.2 from PyPI as a persistent
runtime requirement; remove its requirement line and run
`.venv\Scripts\python.exe -m pip uninstall python-dotenv` to undo that install.

## Work log

2026-08-11 — Created `.venv` with Python 3.14.3, installed requirements, created
the workspace temp parent, and verified 26 tests pass with
`--basetemp=.tmp\pytest-baseline`.

2026-08-11 — Installed the newly declared `python-dotenv` 1.2.2 runtime
dependency from PyPI into `.venv`.
