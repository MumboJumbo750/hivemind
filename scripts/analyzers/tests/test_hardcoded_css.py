"""
Unit tests for HardcodedCssAnalyzer.

Run (canonical):
    make health-test

Or directly:
    podman compose exec -w /workspace -e PYTHONPATH=/workspace:/app backend \
        /app/.venv/bin/pytest scripts/analyzers/tests/ -v
"""

from __future__ import annotations

from pathlib import Path

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


def test_jsx_camelcase_spacing_string(analyzer, tmp_path):
    """paddingTop: '8px' in JSX style object must be detected."""
    _write(tmp_path, "comp.tsx", """\
        const X = () => <div style={{ paddingTop: '8px', marginLeft: '16px' }} />;
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-spacing" for f in findings)


def test_jsx_numeric_spacing(analyzer, tmp_path):
    """padding: 12 (bare integer) in JSX must be detected."""
    _write(tmp_path, "comp.tsx", """\
        const X = () => <div style={{ padding: 12 }} />;
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-spacing" for f in findings)


def test_jsx_numeric_spacing_zero_exempt(analyzer, tmp_path):
    """padding: 0 and padding: 1 must NOT be flagged."""
    _write(tmp_path, "comp.tsx", """\
        const X = () => <div style={{ padding: 0, margin: 1 }} />;
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-spacing" for f in findings)


def test_jsx_camelcase_fontsize(analyzer, tmp_path):
    """fontSize: '14px' in JSX style object must be detected."""
    _write(tmp_path, "comp.tsx", """\
        const X = () => <span style={{ fontSize: '14px' }}>text</span>;
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-font-size" for f in findings)


def test_jsx_numeric_zindex(analyzer, tmp_path):
    """zIndex: 999 in JSX style object must be detected."""
    _write(tmp_path, "comp.tsx", """\
        const X = () => <div style={{ zIndex: 999 }} />;
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-z-index" and "999" in f.message for f in findings)


def test_jsx_string_zindex(analyzer, tmp_path):
    """zIndex: '100' (string) in JSX style object must be detected."""
    _write(tmp_path, "comp.tsx", """\
        const X = () => <div style={{ zIndex: '100' }} />;
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-z-index" for f in findings)


def test_jsx_var_exempt(analyzer, tmp_path):
    """style={{ color: 'var(--color-primary)' }} must NOT be flagged."""
    _write(tmp_path, "comp.tsx", """\
        const X = () => <div style={{ color: 'var(--color-primary)', padding: 'var(--sp-4)' }} />;
    """)
    findings = analyzer.analyze(tmp_path)
    assert not findings


def test_styled_components_color(analyzer, tmp_path):
    """styled-components template literal with hardcoded color must be detected."""
    _write(tmp_path, "Btn.tsx", """\
        import styled from 'styled-components';
        const Btn = styled.button`
          color: #cc0000;
          padding: 12px;
        `;
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-color" for f in findings)


def test_styled_components_spacing(analyzer, tmp_path):
    """styled-components template literal with hardcoded spacing must be detected."""
    _write(tmp_path, "Card.tsx", """\
        import styled from 'styled-components';
        const Card = styled.div`
          padding: 24px;
          margin: 16px 0;
        `;
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-spacing" for f in findings)


# ─── Configurable exceptions ──────────────────────────────────────────────────

def test_exclude_pattern_skips_file(tmp_path):
    """Files matching exclude_patterns must be skipped entirely."""
    _write(tmp_path, "legacy-ui.css", """\
        .x { color: #ff0000; padding: 12px; }
    """)
    a = HardcodedCssAnalyzer(config={"exclude_patterns": ["legacy-ui.css"]})
    findings = a.analyze(tmp_path)
    assert not findings


def test_extra_definition_pattern(tmp_path):
    """Custom definition_patterns must mark a file as exempt from analysis."""
    _write(tmp_path, "my-brand-tokens.css", """\
        :root { --primary: #007bff; --spacing-4: 16px; }
    """)
    a = HardcodedCssAnalyzer(config={"definition_patterns": ["my-brand-*"]})
    findings = a.analyze(tmp_path)
    assert not findings


def test_color_allowlist(tmp_path):
    """Colors in color_allowlist must not be flagged as named colors."""
    _write(tmp_path, "comp.css", """\
        .x { color: rebeccapurple; }
    """)
    a_default = HardcodedCssAnalyzer()
    # rebeccapurple is not in default list, so no finding expected
    # Test allowlist suppresses a color that IS in the default list
    _write(tmp_path, "comp2.css", """\
        .x { color: red; }
    """)
    a_allowlist = HardcodedCssAnalyzer(config={"color_allowlist": ["red"]})
    findings = a_allowlist.analyze(tmp_path)
    assert not any(
        f.category == "hardcoded-color" and "red" in f.message for f in findings
    )


def test_spacing_allowlist_px(tmp_path):
    """Custom spacing_allowlist_px values must not be flagged."""
    _write(tmp_path, "comp.css", """\
        .x { width: 18px; height: 18px; }
    """)
    # Default analyzer would flag 18px
    a_default = HardcodedCssAnalyzer()
    assert any(f.category == "hardcoded-spacing" for f in a_default.analyze(tmp_path))

    # With 18 in allowlist, should be exempt
    a_allowed = HardcodedCssAnalyzer(config={"spacing_allowlist_px": [18]})
    findings = a_allowed.analyze(tmp_path)
    assert not any(f.category == "hardcoded-spacing" for f in findings)


def test_hivemind_health_json_config(tmp_path):
    """Analyzer reads .hivemind-health.json from root when no config given."""
    import json
    (tmp_path / ".hivemind-health.json").write_text(
        json.dumps({"hardcoded-css": {"exclude_patterns": ["*.css"]}}),
        encoding="utf-8",
    )
    _write(tmp_path, "styles.css", """\
        .x { color: #ff0000; }
    """)
    a = HardcodedCssAnalyzer()
    findings = a.analyze(tmp_path)
    assert not findings


# ─── AnalyzerRegistry auto-discovery ─────────────────────────────────────────

def test_registry_discovers_hardcoded_css():
    from scripts.analyzers import AnalyzerRegistry
    AnalyzerRegistry.reset()
    # Force import of the analyzer module
    import scripts.analyzers.hardcoded_css  # noqa: F401
    analyzers = AnalyzerRegistry.discover()
    names = [a.name for a in analyzers]
    assert "hardcoded-css" in names


# ─── Zero false-positives: var() usage is never flagged ──────────────────────

def test_no_false_positives_on_var_usage(analyzer, tmp_path):
    """A perfectly tokenized component using only var(--) must produce zero findings."""
    _write(tmp_path, "PerfectComponent.vue", """\
        <template><div class="card">content</div></template>
        <style scoped>
        .card {
          color: var(--color-primary);
          background: var(--color-surface);
          border-color: var(--color-border);
          padding: var(--spacing-4);
          margin: var(--spacing-2) var(--spacing-4);
          font-size: var(--font-size-md);
          z-index: var(--z-modal);
          width: var(--size-full);
          gap: var(--spacing-2);
        }
        .badge {
          background: transparent;
          color: inherit;
          border: 1px solid var(--color-border);
          padding: 0px;
        }
        </style>
    """)
    findings = analyzer.analyze(tmp_path)
    assert not findings, f"False positives detected: {[f.message for f in findings]}"


def test_no_false_positives_on_perfect_jsx(analyzer, tmp_path):
    """A JSX component using only var(--) or safe values must produce zero findings."""
    _write(tmp_path, "Perfect.tsx", """\
        const X = () => (
          <div style={{ color: 'var(--color-fg)', padding: 'var(--sp-4)', zIndex: 0 }} />
        );
    """)
    findings = analyzer.analyze(tmp_path)
    assert not findings, f"False positives detected: {[f.message for f in findings]}"


def test_no_errors_in_hivemind_frontend():
    """
    Verify that the Hivemind frontend produces NO error-severity findings
    and that lines explicitly using var(--) in frontend files are not falsely flagged.

    Note: info/warning findings for genuinely hardcoded values in the frontend
    are expected (those are real issues to refactor) and are NOT false positives.
    """
    repo_root = Path(__file__).resolve().parents[3]
    frontend = repo_root / "frontend"
    if not frontend.exists():
        pytest.skip("frontend/ not found")
    a = HardcodedCssAnalyzer()
    findings = a.analyze(frontend)

    # No error-severity findings (would indicate a Bug in the analyzer)
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"Unexpected errors in frontend: {errors}"

    # No findings should reference a line that uses var(--)
    # (= no false positives on properly tokenized lines)
    from pathlib import Path as _Path
    false_positives = []
    for f in findings:
        if f.line is None:
            continue
        filepath = frontend / f.file
        if not filepath.exists():
            continue
        try:
            lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
            if f.line <= len(lines):
                src_line = lines[f.line - 1]
                if "var(--" in src_line:
                    false_positives.append(
                        f"{f.file}:{f.line} — {f.message!r} (line: {src_line.strip()!r})"
                    )
        except Exception:
            pass
    assert false_positives == [], (
        f"False positives: var(--) lines were flagged:\n" + "\n".join(false_positives)
    )
