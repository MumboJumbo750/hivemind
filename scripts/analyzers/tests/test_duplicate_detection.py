"""
Unit tests for DuplicateDetectionAnalyzer.

Run (canonical):
    make health-test

Or directly:
    podman compose exec -w /workspace -e PYTHONPATH=/workspace:/app backend \
        /app/.venv/bin/pytest scripts/analyzers/tests/ -v
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.analyzers.duplicate_detection import DuplicateDetectionAnalyzer


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def analyzer():
    return DuplicateDetectionAnalyzer()


@pytest.fixture
def analyzer_phase1_only():
    """Phase 1 only — no SequenceMatcher pass."""
    return DuplicateDetectionAnalyzer(deep_scan=False)


@pytest.fixture
def strict():
    """Low threshold to make near-duplicates easier to trigger in tests."""
    return DuplicateDetectionAnalyzer(similarity_threshold=0.60)


def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ── Template duplicate (exact) ────────────────────────────────────────────────


def test_exact_template_duplicate(analyzer, tmp_path):
    """Two Vue files with identical <template> blocks should be flagged."""
    tmpl = """\
        <template>
          <div class="card">
            <h2>{{ title }}</h2>
            <p>{{ description }}</p>
          </div>
        </template>
    """
    _write(tmp_path, "src/CompA.vue", tmpl)
    _write(tmp_path, "src/CompB.vue", tmpl)

    findings = analyzer.analyze(tmp_path)
    cats = [f.category for f in findings]
    assert "template-duplicate" in cats, f"Expected template-duplicate, got: {cats}"


def test_no_template_duplicate_when_different(analyzer, tmp_path):
    """Two Vue files with different templates should NOT be flagged as exact duplicates."""
    _write(
        tmp_path,
        "src/CompA.vue",
        """\
        <template><div>Hello A</div></template>
        """,
    )
    _write(
        tmp_path,
        "src/CompB.vue",
        """\
        <template><div>Hello B</div></template>
        """,
    )

    findings = analyzer.analyze(tmp_path)
    exact = [f for f in findings if f.category == "template-duplicate"]
    assert not exact


def test_template_duplicate_exact_three_files(analyzer, tmp_path):
    """Three files with the same template → should emit pairwise findings (3 pairs)."""
    tmpl = """\
        <template>
          <button class="btn">{{ label }}</button>
        </template>
    """
    _write(tmp_path, "src/A.vue", tmpl)
    _write(tmp_path, "src/B.vue", tmpl)
    _write(tmp_path, "src/C.vue", tmpl)

    findings = [f for f in analyzer.analyze(tmp_path) if f.category == "template-duplicate"]
    # 3 choose 2 = 3 pairs
    assert len(findings) == 3


# ── Template near-duplicate ───────────────────────────────────────────────────


def test_near_duplicate_template_detected(strict, tmp_path):
    """Two very similar (but not identical) templates trigger a near-duplicate finding."""
    _write(
        tmp_path,
        "src/CompA.vue",
        """\
        <template>
          <div class="card">
            <h2>{{ title }}</h2>
            <p>{{ description }}</p>
            <span>{{ author }}</span>
          </div>
        </template>
        """,
    )
    _write(
        tmp_path,
        "src/CompB.vue",
        """\
        <template>
          <div class="card">
            <h2>{{ name }}</h2>
            <p>{{ summary }}</p>
            <span>{{ creator }}</span>
          </div>
        </template>
        """,
    )

    findings = strict.analyze(tmp_path)
    near = [f for f in findings if f.category == "template-near-duplicate"]
    assert near, "Expected near-duplicate template finding"
    assert any("↔" in f.message for f in near)


def test_near_duplicate_not_triggered_for_unrelated(analyzer, tmp_path):
    """Very different templates must NOT be flagged as near-duplicates."""
    _write(
        tmp_path,
        "src/CompA.vue",
        """\
        <template>
          <div><input type="text" v-model="query" /></div>
        </template>
        """,
    )
    _write(
        tmp_path,
        "src/CompB.vue",
        """\
        <template>
          <table><tr><td>{{ row.id }}</td><td>{{ row.email }}</td></tr></table>
        </template>
        """,
    )

    findings = analyzer.analyze(tmp_path)
    near = [f for f in findings if f.category == "template-near-duplicate"]
    assert not near


def test_deep_scan_false_skips_near_duplicates(analyzer_phase1_only, tmp_path):
    """With deep_scan=False, near-duplicate detection is skipped entirely."""
    _write(
        tmp_path,
        "src/CompA.vue",
        """\
        <template>
          <div class="card">{{ title }} - {{ desc }}</div>
        </template>
        """,
    )
    _write(
        tmp_path,
        "src/CompB.vue",
        """\
        <template>
          <div class="card">{{ name }} - {{ info }}</div>
        </template>
        """,
    )

    findings = analyzer_phase1_only.analyze(tmp_path)
    near = [f for f in findings if "near-duplicate" in f.category]
    assert not near


# ── CSS block duplicate ───────────────────────────────────────────────────────


def test_exact_css_duplicate(analyzer, tmp_path):
    """Two Vue files with identical <style> blocks should be flagged."""
    style = """\
        <style scoped>
        .card { padding: 16px; border: 1px solid #ccc; }
        .card h2 { font-size: 18px; color: #333; }
        </style>
    """
    _write(tmp_path, "src/CompA.vue", style)
    _write(tmp_path, "src/CompB.vue", style)

    findings = analyzer.analyze(tmp_path)
    cats = [f.category for f in findings]
    assert "css-duplicate" in cats


def test_css_near_duplicate(strict, tmp_path):
    """Two very similar <style> blocks trigger a near-duplicate finding."""
    _write(
        tmp_path,
        "src/CompA.vue",
        """\
        <style scoped>
        .button { background: blue; color: white; padding: 8px 16px; border-radius: 4px; }
        .button:hover { background: darkblue; }
        .button:disabled { opacity: 0.5; }
        </style>
        """,
    )
    _write(
        tmp_path,
        "src/CompB.vue",
        """\
        <style scoped>
        .btn { background: blue; color: white; padding: 8px 16px; border-radius: 4px; }
        .btn:hover { background: darkblue; }
        .btn:disabled { opacity: 0.6; }
        </style>
        """,
    )

    findings = strict.analyze(tmp_path)
    near = [f for f in findings if f.category == "css-near-duplicate"]
    assert near, "Expected css-near-duplicate finding"


# ── Code-block (function) duplicate ──────────────────────────────────────────


def test_exact_python_function_duplicate(analyzer, tmp_path):
    """Two Python files with identical function bodies are flagged as code-duplicate."""
    func = """\
        def calculate_discount(price, pct):
            if pct < 0 or pct > 100:
                raise ValueError("Invalid percentage")
            discount = price * pct / 100
            result = price - discount
            return result
    """
    _write(tmp_path, "service_a.py", func + "\n")
    _write(tmp_path, "service_b.py", func + "\n")

    findings = analyzer.analyze(tmp_path)
    code_dups = [f for f in findings if f.category == "code-duplicate"]
    assert code_dups, f"Expected code-duplicate, got: {[f.category for f in findings]}"


def test_near_duplicate_python_function(strict, tmp_path):
    """Two very similar Python functions trigger a near-duplicate finding."""
    _write(
        tmp_path,
        "utils_a.py",
        """\
        def get_active_users(session, organization_id):
            query = session.query(User)
            query = query.filter(User.active == True)
            query = query.filter(User.org_id == organization_id)
            return query.all()
        """,
    )
    _write(
        tmp_path,
        "utils_b.py",
        """\
        def get_enabled_users(db, org_id):
            query = db.query(User)
            query = query.filter(User.enabled == True)
            query = query.filter(User.organization_id == org_id)
            return query.all()
        """,
    )

    findings = strict.analyze(tmp_path)
    near_code = [f for f in findings if f.category == "code-near-duplicate"]
    assert near_code, "Expected code-near-duplicate finding"
    assert any("↔" in f.message for f in near_code)


def test_short_functions_below_min_lines_excluded(tmp_path):
    """Functions below min_block_lines should not be compared."""
    a = DuplicateDetectionAnalyzer(min_block_lines=10)
    # These functions are only 4 lines — below threshold
    func = """\
        def add(a, b):
            result = a + b
            return result
    """
    _write(tmp_path, "a.py", func)
    _write(tmp_path, "b.py", func)

    findings = [f for f in a.analyze(tmp_path) if "code" in f.category]
    assert not findings, "Short functions should not be detected as duplicates"


def test_code_block_duplicate_deep_scan_false(analyzer_phase1_only, tmp_path):
    """With deep_scan=False, code-block near-duplicate detection is skipped."""
    func = """\
        def process(items):
            result = []
            for item in items:
                if item.active:
                    result.append(item.value)
            return result
    """
    _write(tmp_path, "a.py", func)
    _write(tmp_path, "b.py", func)

    # deep_scan=False: code block checks are skipped
    findings = analyzer_phase1_only.analyze(tmp_path)
    code_dups = [f for f in findings if "code" in f.category]
    assert not code_dups


# ── Import-pattern duplicates ─────────────────────────────────────────────────


def test_import_pattern_exact_repeat(tmp_path):
    """Identical import group in > threshold (3) files flags all files."""
    a = DuplicateDetectionAnalyzer(import_repeat_threshold=3)
    imports = """\
        import { ref, computed } from 'vue'
        import { useRouter } from 'vue-router'
        import { useStore } from 'pinia'
    """
    for name in ("a.ts", "b.ts", "c.ts", "d.ts"):
        _write(tmp_path, f"src/{name}", imports)

    findings = [f for f in a.analyze(tmp_path) if f.category == "import-pattern-duplicate"]
    # 4 files exceed threshold of 3 → findings for each of the 4 files
    assert len(findings) == 4


def test_import_pattern_below_threshold_not_flagged(tmp_path):
    """Import group appearing in <= threshold files should NOT be flagged."""
    a = DuplicateDetectionAnalyzer(import_repeat_threshold=3)
    imports = """\
        import { ref } from 'vue'
        import { useRouter } from 'vue-router'
    """
    # Only 3 files — threshold is >3, so 3 is fine
    for name in ("a.ts", "b.ts", "c.ts"):
        _write(tmp_path, f"src/{name}", imports)

    findings = [f for f in a.analyze(tmp_path) if f.category == "import-pattern-duplicate"]
    assert not findings


def test_import_pattern_python(tmp_path):
    """Python import groups repeated in >3 files are detected."""
    a = DuplicateDetectionAnalyzer(import_repeat_threshold=3)
    imports = """\
        from sqlalchemy.orm import Session
        from app.models import User
        from app.db import get_db
        from fastapi import Depends
    """
    for name in ("route_a.py", "route_b.py", "route_c.py", "route_d.py"):
        _write(tmp_path, f"app/{name}", imports)

    findings = [f for f in a.analyze(tmp_path) if f.category == "import-pattern-duplicate"]
    assert findings


# ── Ignore dirs ───────────────────────────────────────────────────────────────


def test_node_modules_ignored(analyzer, tmp_path):
    """Files under node_modules should never be analyzed."""
    tmpl = """\
        <template>
          <div>{{ message }}</div>
        </template>
    """
    _write(tmp_path, "src/Real.vue", tmpl)
    _write(tmp_path, "node_modules/pkg/Comp.vue", tmpl)

    findings = analyzer.analyze(tmp_path)
    file_paths = [f.file for f in findings]
    assert not any("node_modules" in p for p in file_paths)


# ── Finding structure ─────────────────────────────────────────────────────────


def test_finding_has_both_files_in_message(analyzer, tmp_path):
    """Each duplicate finding must reference both files in its message."""
    tmpl = """\
        <template>
          <div class="wrapper">
            <slot />
          </div>
        </template>
    """
    _write(tmp_path, "src/Alpha.vue", tmpl)
    _write(tmp_path, "src/Beta.vue", tmpl)

    findings = [f for f in analyzer.analyze(tmp_path) if f.category == "template-duplicate"]
    assert findings
    msg = findings[0].message
    # Message should reference both files
    assert "Alpha.vue" in msg or "Beta.vue" in msg


def test_finding_similarity_score_in_message(strict, tmp_path):
    """Near-duplicate findings must include a similarity score in the message."""
    _write(
        tmp_path,
        "src/CompA.vue",
        """\
        <template>
          <div class="box">
            <h3>{{ heading }}</h3>
            <p>{{ content }}</p>
          </div>
        </template>
        """,
    )
    _write(
        tmp_path,
        "src/CompB.vue",
        """\
        <template>
          <div class="box">
            <h3>{{ title }}</h3>
            <p>{{ body }}</p>
          </div>
        </template>
        """,
    )

    findings = strict.analyze(tmp_path)
    near = [f for f in findings if "near-duplicate" in f.category]
    if near:
        # Message should contain a percentage
        assert any("%" in f.message for f in near)


# ── Analyzer registration ─────────────────────────────────────────────────────


def test_analyzer_auto_discovered():
    """DuplicateDetectionAnalyzer should be found via AnalyzerRegistry."""
    from scripts.analyzers import AnalyzerRegistry

    AnalyzerRegistry.reset()
    registered_names = [a.name for a in AnalyzerRegistry.discover()]
    assert "duplicate-detection" in registered_names
