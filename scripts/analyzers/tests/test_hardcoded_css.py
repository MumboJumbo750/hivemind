"""
Unit tests for HardcodedCssAnalyzer.
Run: podman compose run --rm --no-deps --entrypoint="" -v "$PWD:/workspace:ro" -w /workspace backend \
       /app/.venv/bin/python -m pytest scripts/analyzers/tests/test_hardcoded_css.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import textwrap
import tempfile
import os
import pytest

from scripts.analyzers.hardcoded_css import HardcodedCssAnalyzer


@pytest.fixture
def analyzer():
    return HardcodedCssAnalyzer()


def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ─── Colors ──────────────────────────────────────────────────────────────────

def test_hex_color_in_css(analyzer, tmp_path):
    f = _write(tmp_path, "component.css", """\
        .btn { color: #333; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-color" and "#333" in f.message for f in findings)


def test_hex_color_in_vue_style_block(analyzer, tmp_path):
    f = _write(tmp_path, "Button.vue", """\
        <template><button/></template>
        <style scoped>
        .btn { background: #ff0000; }
        </style>
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-color" for f in findings)


def test_rgb_color(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .x { color: rgb(255, 0, 0); }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any("rgb/rgba" in f.message for f in findings)


def test_rgba_color(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .x { background: rgba(0,0,0,0.5); }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any("rgb/rgba" in f.message for f in findings)


def test_hsl_color(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .x { color: hsl(120, 100%, 50%); }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any("hsl/hsla" in f.message for f in findings)


def test_named_color(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .x { color: red; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-color" for f in findings)


def test_var_css_exempt(analyzer, tmp_path):
    """Lines using var(--) must not be flagged."""
    _write(tmp_path, "comp.css", """\
        .x { color: var(--color-primary); }
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-color" for f in findings)


def test_transparent_exempt(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .x { background: transparent; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-color" for f in findings)


def test_definition_file_skipped(analyzer, tmp_path):
    """Token definition files must be skipped entirely."""
    _write(tmp_path, "tokens.css", """\
        :root { --color-primary: #007bff; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert not findings


def test_theme_file_skipped(analyzer, tmp_path):
    _write(tmp_path, "dark-theme.css", """\
        :root { --bg: #111; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert not findings


# ─── Spacing ─────────────────────────────────────────────────────────────────

def test_hardcoded_padding(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .card { padding: 16px; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-spacing" for f in findings)


def test_hardcoded_margin(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .x { margin: 8px 16px; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-spacing" for f in findings)


def test_zero_px_exempt(analyzer, tmp_path):
    """0px and 1px should not be flagged."""
    _write(tmp_path, "comp.css", """\
        .x { margin: 0px; border: 1px solid; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-spacing" for f in findings)


def test_hardcoded_gap(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .grid { gap: 24px; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-spacing" for f in findings)


# ─── Font Size ────────────────────────────────────────────────────────────────

def test_hardcoded_font_size_px(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        p { font-size: 14px; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-font-size" for f in findings)


def test_hardcoded_font_size_rem(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        p { font-size: 1.25rem; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-font-size" for f in findings)


def test_font_size_var_exempt(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        p { font-size: var(--font-size-md); }
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-font-size" for f in findings)


# ─── Z-Index ─────────────────────────────────────────────────────────────────

def test_hardcoded_zindex(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .modal { z-index: 999; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-z-index" and "999" in f.message for f in findings)


def test_zindex_zero_exempt(analyzer, tmp_path):
    _write(tmp_path, "comp.css", """\
        .x { z-index: 0; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-z-index" for f in findings)


# ─── Vue SFC — no style block ─────────────────────────────────────────────────

def test_vue_no_style_block_skipped(analyzer, tmp_path):
    _write(tmp_path, "NoStyle.vue", """\
        <template><div style="color: red"/></template>
    """)
    findings = analyzer.analyze(tmp_path)
    # inline template style attr is not analyzed (only <style> blocks for .vue)
    assert not any(f.category == "hardcoded-color" for f in findings)


# ─── JSX inline styles ────────────────────────────────────────────────────────

def test_jsx_inline_color(analyzer, tmp_path):
    _write(tmp_path, "comp.tsx", """\
        const X = () => <div style={{ color: '#ff0000', padding: '16px' }} />;
    """)
    findings = analyzer.analyze(tmp_path)
    cats = {f.category for f in findings}
    assert "hardcoded-color" in cats


# ─── AnalyzerRegistry auto-discovery ─────────────────────────────────────────

def test_registry_discovers_hardcoded_css():
    from scripts.analyzers import AnalyzerRegistry
    AnalyzerRegistry.reset()
    # Force import of the analyzer module
    import scripts.analyzers.hardcoded_css  # noqa: F401
    analyzers = AnalyzerRegistry.discover()
    names = [a.name for a in analyzers]
    assert "hardcoded-css" in names


# ─── Zero false-positives in Hivemind frontend ───────────────────────────────

def test_no_errors_in_hivemind_frontend():
    """Sanity check: no ERROR-severity findings in the actual Hivemind frontend."""
    repo_root = Path(__file__).resolve().parents[3]
    frontend = repo_root / "frontend"
    if not frontend.exists():
        pytest.skip("frontend/ not found")
    a = HardcodedCssAnalyzer()
    findings = a.analyze(frontend)
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"Unexpected errors in frontend: {errors}"
