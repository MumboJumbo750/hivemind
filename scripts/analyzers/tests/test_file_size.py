"""
Unit tests for FileSizeAnalyzer.

Run (canonical):
    make health-test

Or directly:
    podman compose exec -w /workspace -e PYTHONPATH=/workspace:/app backend \
        /app/.venv/bin/pytest scripts/analyzers/tests/test_file_size.py -v
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.analyzers.file_size import FileSizeAnalyzer


@pytest.fixture
def analyzer():
    return FileSizeAnalyzer(warn_lines=10, error_lines=20, test_warn_lines=30, test_error_lines=50, complexity_threshold=3)


def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ─── File size thresholds ─────────────────────────────────────────────────────

def test_file_under_warn_no_finding(analyzer, tmp_path):
    _write(tmp_path, "small.py", "\n" * 5)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "file-too-large" for f in findings)


def test_file_over_warn_is_warning(analyzer, tmp_path):
    _write(tmp_path, "medium.py", "\n" * 15)
    findings = analyzer.analyze(tmp_path)
    assert any(f.severity == "warning" and f.category == "file-too-large" for f in findings)


def test_file_over_error_is_error(analyzer, tmp_path):
    _write(tmp_path, "large.py", "\n" * 25)
    findings = analyzer.analyze(tmp_path)
    assert any(f.severity == "error" and f.category == "file-too-large" for f in findings)


def test_test_file_higher_threshold(analyzer, tmp_path):
    """Files under tests/ should use the higher test thresholds."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write(tmp_path, "tests/test_something.py", "\n" * 25)
    findings = analyzer.analyze(tmp_path)
    # 25 lines < test_warn=30 → no finding
    assert not any(f.category == "file-too-large" for f in findings)


def test_test_file_over_test_warn(analyzer, tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write(tmp_path, "tests/test_something.py", "\n" * 35)
    findings = analyzer.analyze(tmp_path)
    assert any(f.severity == "warning" and f.category == "file-too-large" for f in findings)


def test_ignored_dirs_skipped(analyzer, tmp_path):
    """node_modules and .venv should be skipped."""
    nm = tmp_path / "node_modules"
    nm.mkdir()
    _write(tmp_path, "node_modules/big.py", "\n" * 100)
    findings = analyzer.analyze(tmp_path)
    assert not any("node_modules" in f.file for f in findings)


def test_ts_file_size(analyzer, tmp_path):
    _write(tmp_path, "widget.ts", "\n" * 25)
    findings = analyzer.analyze(tmp_path)
    assert any(f.severity == "error" and "widget.ts" in f.file for f in findings)


def test_vue_file_size(analyzer, tmp_path):
    _write(tmp_path, "Button.vue", "\n" * 15)
    findings = analyzer.analyze(tmp_path)
    assert any(f.severity == "warning" and "Button.vue" in f.file for f in findings)


# ─── Cyclomatic complexity ────────────────────────────────────────────────────

def test_high_complexity_function(analyzer, tmp_path):
    """Function with >3 branches (threshold) should be flagged."""
    code = textwrap.dedent("""\
        def complex_func(x):
            if x > 0:
                pass
            if x < 0:
                pass
            if x == 0:
                pass
            if x > 10:
                pass
            return x
    """)
    _write(tmp_path, "logic.py", code)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "complexity" and "complex_func" in f.message for f in findings)


def test_simple_function_no_complexity_finding(analyzer, tmp_path):
    """Simple function with <=3 branches should not be flagged."""
    code = textwrap.dedent("""\
        def simple(x):
            if x > 0:
                return x
            return 0
    """)
    _write(tmp_path, "simple.py", code)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "complexity" for f in findings)


def test_complexity_reports_line_number(analyzer, tmp_path):
    code = textwrap.dedent("""\
        x = 1

        def branchy(a, b, c, d):
            if a: pass
            if b: pass
            if c: pass
            if d: pass
            return a
    """)
    _write(tmp_path, "branchy.py", code)
    findings = analyzer.analyze(tmp_path)
    complexity_findings = [f for f in findings if f.category == "complexity"]
    assert complexity_findings
    assert complexity_findings[0].line is not None
    assert complexity_findings[0].line >= 3


def test_no_crash_on_syntax_error(analyzer, tmp_path):
    """Analyzer must not crash on invalid Python files."""
    _write(tmp_path, "broken.py", "def broken(\n")
    findings = analyzer.analyze(tmp_path)
    # No complexity findings, no crash
    assert not any(f.category == "complexity" for f in findings)
