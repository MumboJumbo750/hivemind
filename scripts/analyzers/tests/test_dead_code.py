"""
Unit tests for DeadCodeAnalyzer.

Run (canonical):
    make health-test

Or directly:
    podman compose exec -w /workspace -e PYTHONPATH=/workspace:/app backend \
        /app/.venv/bin/pytest scripts/analyzers/tests/test_dead_code.py -v
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.analyzers.dead_code import DeadCodeAnalyzer


def _write(tmp: Path, rel: str, content: str) -> Path:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ─── TypeScript: unexported symbols ──────────────────────────────────────────

def test_ts_unexported_function_flagged(tmp_path):
    a = DeadCodeAnalyzer(check_ts_unexported=True, check_py_unused_functions=False, check_unreferenced_files=False)
    _write(tmp_path, "utils.ts", """\
        function helper() {
            return 42
        }
    """)
    findings = a.analyze(tmp_path)
    assert any(f.category == "unexported-symbol" and "helper" in f.message for f in findings)


def test_ts_exported_function_not_flagged(tmp_path):
    a = DeadCodeAnalyzer(check_ts_unexported=True, check_py_unused_functions=False, check_unreferenced_files=False)
    _write(tmp_path, "utils.ts", """\
        export function helper() {
            return 42
        }
    """)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unexported-symbol" for f in findings)


def test_ts_function_used_locally_not_flagged(tmp_path):
    """If a function is called within the same file, it should not be flagged."""
    a = DeadCodeAnalyzer(check_ts_unexported=True, check_py_unused_functions=False, check_unreferenced_files=False)
    _write(tmp_path, "utils.ts", """\
        function helper() {
            return 42
        }
        const result = helper()
    """)
    findings = a.analyze(tmp_path)
    # helper() called once → usages > 1 → not flagged
    assert not any(f.category == "unexported-symbol" and "helper" in f.message for f in findings)


def test_ts_dead_code_ok_suppression(tmp_path):
    a = DeadCodeAnalyzer(check_ts_unexported=True, check_py_unused_functions=False, check_unreferenced_files=False)
    _write(tmp_path, "utils.ts", """\
        function legacy() { // dead-code-ok
            return 0
        }
    """)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unexported-symbol" and "legacy" in f.message for f in findings)


def test_ts_entry_point_skipped(tmp_path):
    """index.ts is an entry point and should not be checked."""
    a = DeadCodeAnalyzer(check_ts_unexported=True, check_py_unused_functions=False, check_unreferenced_files=False)
    _write(tmp_path, "index.ts", """\
        function bootstrap() { return true }
    """)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unexported-symbol" for f in findings)


# ─── Python: unused module-level functions ───────────────────────────────────

def test_py_unused_function_flagged(tmp_path):
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=True, check_unreferenced_files=False)
    _write(tmp_path, "utils.py", """\
        def orphan():
            return 1
    """)
    findings = a.analyze(tmp_path)
    assert any(f.category == "unused-function" and "orphan" in f.message for f in findings)


def test_py_called_function_not_flagged(tmp_path):
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=True, check_unreferenced_files=False)
    _write(tmp_path, "utils.py", """\
        def helper():
            return 1

        result = helper()
    """)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unused-function" and "helper" in f.message for f in findings)


def test_py_all_export_not_flagged(tmp_path):
    """Functions in __all__ should not be flagged even if not called locally."""
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=True, check_unreferenced_files=False)
    _write(tmp_path, "api.py", """\
        __all__ = ["public_func"]

        def public_func():
            return "exported"
    """)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unused-function" and "public_func" in f.message for f in findings)


def test_py_private_function_skipped(tmp_path):
    """Functions starting with _ are considered intentionally private."""
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=True, check_unreferenced_files=False)
    _write(tmp_path, "helpers.py", """\
        def _internal():
            pass
    """)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unused-function" and "_internal" in f.message for f in findings)


def test_py_noqa_suppression(tmp_path):
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=True, check_unreferenced_files=False)
    _write(tmp_path, "compat.py", """\
        def legacy_func():  # noqa: dead-code
            pass
    """)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unused-function" and "legacy_func" in f.message for f in findings)


def test_py_init_py_skipped(tmp_path):
    """__init__.py should be skipped entirely."""
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=True, check_unreferenced_files=False)
    _write(tmp_path, "__init__.py", """\
        def helper():
            pass
    """)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unused-function" for f in findings)


def test_py_no_crash_on_syntax_error(tmp_path):
    """Broken Python files should not crash the analyzer."""
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=True, check_unreferenced_files=False)
    _write(tmp_path, "broken.py", "def broken(\n")
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unused-function" for f in findings)


# ─── Unreferenced files ───────────────────────────────────────────────────────

def test_unreferenced_file_flagged(tmp_path):
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=False, check_unreferenced_files=True)
    # orphan.ts is not imported by anything
    _write(tmp_path, "orphan.ts", "export const x = 1\n")
    _write(tmp_path, "main.ts", "const y = 2\n")
    findings = a.analyze(tmp_path)
    assert any(f.category == "unreferenced-file" and "orphan.ts" in f.file for f in findings)


def test_referenced_file_not_flagged(tmp_path):
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=False, check_unreferenced_files=True)
    _write(tmp_path, "utils.ts", "export const x = 1\n")
    _write(tmp_path, "app.ts", "import { x } from './utils'\n")
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unreferenced-file" and "utils.ts" in f.file for f in findings)


def test_entry_points_not_flagged_as_unreferenced(tmp_path):
    a = DeadCodeAnalyzer(check_ts_unexported=False, check_py_unused_functions=False, check_unreferenced_files=True)
    _write(tmp_path, "main.py", "print('hello')\n")
    _write(tmp_path, "index.ts", "console.log('hi')\n")
    findings = a.analyze(tmp_path)
    assert not any(f.category == "unreferenced-file" for f in findings)


# ─── All findings are info severity ──────────────────────────────────────────

def test_all_findings_are_info(tmp_path):
    """DeadCodeAnalyzer must only emit info-level findings."""
    a = DeadCodeAnalyzer()
    _write(tmp_path, "utils.py", """\
        def orphan():
            return 1
    """)
    findings = a.analyze(tmp_path)
    for f in findings:
        assert f.severity == "info", f"Expected info, got {f.severity} for {f}"
