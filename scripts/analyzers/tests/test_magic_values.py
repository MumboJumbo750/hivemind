"""
Unit tests for MagicValuesAnalyzer.

Run:
    podman compose exec backend /app/.venv/bin/pytest scripts/analyzers/tests/test_magic_values.py -v
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from scripts.analyzers.magic_values import MagicValuesAnalyzer


@pytest.fixture
def analyzer():
    return MagicValuesAnalyzer()


def _write(tmp: Path, name: str, content: str) -> Path:
    """Write a file under tmp_path, creating subdirs as needed."""
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ─── Python: Magic Numbers in Comparisons ─────────────────────────────────────


def test_py_magic_number_comparison_gt(analyzer, tmp_path):
    _write(tmp_path, "service.py", """\
        def check(count):
            if count > 42:
                return True
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "magic-number" and "42" in f.message for f in findings)


def test_py_magic_number_comparison_le(analyzer, tmp_path):
    _write(tmp_path, "service.py", """\
        def throttle(rate):
            if rate <= 3000:
                pass
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "magic-number" and "3000" in f.message for f in findings)


def test_py_allowed_number_zero(analyzer, tmp_path):
    _write(tmp_path, "service.py", """\
        if count == 0:
            pass
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "magic-number" for f in findings)


def test_py_allowed_number_one(analyzer, tmp_path):
    _write(tmp_path, "service.py", """\
        if offset > 1:
            pass
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "magic-number" for f in findings)


def test_py_allowed_number_minus_one(analyzer, tmp_path):
    _write(tmp_path, "service.py", """\
        if result != -1:
            pass
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "magic-number" for f in findings)


def test_py_float_magic_number(analyzer, tmp_path):
    _write(tmp_path, "config.py", """\
        threshold = 0.85
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "magic-number" and "0.85" in f.message for f in findings)


def test_py_all_caps_assignment_exempt(analyzer, tmp_path):
    """ALL_CAPS assignments are intentional constants — must not be flagged."""
    _write(tmp_path, "constants.py", """\
        MAX_RETRIES = 5
        TIMEOUT_MS = 3000
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "magic-number" for f in findings)


def test_py_noqa_magic_suppresses(analyzer, tmp_path):
    _write(tmp_path, "service.py", """\
        if count > 99:  # noqa: magic
            pass
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "magic-number" for f in findings)


def test_py_lowercase_assignment_magic(analyzer, tmp_path):
    _write(tmp_path, "worker.py", """\
        timeout = 3000
        max_retries = 5
    """)
    findings = analyzer.analyze(tmp_path)
    assert any("timeout" in f.message or "max_retries" in f.message for f in findings)


def test_py_short_var_assignment_exempt(analyzer, tmp_path):
    """Single-letter loop variables should not be flagged."""
    _write(tmp_path, "worker.py", """\
        n = 5
        i = 3
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "magic-number" for f in findings)


# ─── Python: Tests & Migrations Exempt ────────────────────────────────────────


def test_py_test_dir_skipped(analyzer, tmp_path):
    _write(tmp_path, "tests/test_foo.py", """\
        if count > 99:
            pass
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.file.startswith("tests/") for f in findings)


def test_py_migrations_dir_skipped(analyzer, tmp_path):
    _write(tmp_path, "migrations/0001_initial.py", """\
        THRESHOLD = 0.75
        if val > 42:
            pass
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any("migrations" in f.file for f in findings)


# ─── Python: Custom Config ────────────────────────────────────────────────────


def test_custom_allowed_numbers(tmp_path):
    az = MagicValuesAnalyzer(allowed_numbers=[0, 1, -1, 2, 42, 100])
    _write(tmp_path, "service.py", """\
        if count > 42:
            pass
    """)
    findings = az.analyze(tmp_path)
    assert not any(f.category == "magic-number" for f in findings)


def test_custom_ignore_pattern(tmp_path):
    az = MagicValuesAnalyzer(ignore_patterns=[r"SKIP_ME"])
    _write(tmp_path, "service.py", """\
        if count > 99:  # SKIP_ME
            pass
    """)
    findings = az.analyze(tmp_path)
    assert not any(f.category == "magic-number" for f in findings)


# ─── TypeScript/JavaScript: Magic Numbers ─────────────────────────────────────


def test_ts_magic_number_comparison(analyzer, tmp_path):
    _write(tmp_path, "service.ts", """\
        if (retries > 5) {
            throw new Error("too many retries");
        }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "magic-number" and "5" in f.message for f in findings)


def test_ts_magic_number_timeout_arg(analyzer, tmp_path):
    _write(tmp_path, "worker.ts", """\
        setTimeout(() => refresh(), 3000);
    """)
    findings = analyzer.analyze(tmp_path)
    # 3000 should be flagged either as magic-number or magic-number-arg
    assert any(
        f.category in ("magic-number", "magic-number-arg") and "3000" in f.message
        for f in findings
    )


def test_ts_magic_ok_suppresses(analyzer, tmp_path):
    _write(tmp_path, "worker.ts", """\
        setTimeout(() => refresh(), 3000); // magic-ok
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any("3000" in f.message for f in findings)


def test_ts_test_file_skipped(analyzer, tmp_path):
    _write(tmp_path, "service.test.ts", """\
        expect(count).toBeGreaterThan(99);
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any("service.test.ts" in f.file for f in findings)


def test_ts_spec_file_skipped(analyzer, tmp_path):
    _write(tmp_path, "component.spec.ts", """\
        if (x > 42) { ok = true; }
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any("spec" in f.file for f in findings)


def test_ts_import_line_skipped(analyzer, tmp_path):
    _write(tmp_path, "module.ts", """\
        import { something } from './path/to/api/v1/module';
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-api-path" for f in findings)


# ─── Vue: Script Block Only ───────────────────────────────────────────────────


def test_vue_script_magic_number(analyzer, tmp_path):
    _write(tmp_path, "MyComponent.vue", """\
        <template><div>{{ count }}</div></template>
        <script setup lang="ts">
        const limit = ref(50);
        if (limit.value > 50) { /* warn */ }
        </script>
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category in ("magic-number", "magic-number-arg") for f in findings)


def test_vue_template_not_analyzed(analyzer, tmp_path):
    """Numbers in the <template> section must not be flagged."""
    _write(tmp_path, "MyComponent.vue", """\
        <template>
          <div v-if="count > 99">too many</div>
        </template>
        <script setup lang="ts">
        const count = ref(0);
        </script>
    """)
    # 99 is in the template — only count = ref(0) in script (0 is allowed)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "magic-number" and "99" in f.message for f in findings)


# ─── Hardcoded URLs ───────────────────────────────────────────────────────────


def test_py_hardcoded_http_url(analyzer, tmp_path):
    _write(tmp_path, "client.py", """\
        BASE_URL = 'http://example.com/api'
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-url" for f in findings)


def test_py_hardcoded_https_url(analyzer, tmp_path):
    _write(tmp_path, "service.py", """\
        response = requests.get('https://api.example.com/v1/data')
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-url" for f in findings)


def test_ts_hardcoded_url(analyzer, tmp_path):
    _write(tmp_path, "api.ts", """\
        const resp = await fetch('https://backend.internal/health');
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-url" for f in findings)


def test_log_line_url_exempt(analyzer, tmp_path):
    """URLs in log/print lines are messages, not config — skip."""
    _write(tmp_path, "service.py", """\
        print("See docs at https://example.com/docs")
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-url" for f in findings)


# ─── Hardcoded API Paths ──────────────────────────────────────────────────────


def test_py_hardcoded_api_path(analyzer, tmp_path):
    _write(tmp_path, "client.py", """\
        url = base + '/api/v1/users'
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-api-path" for f in findings)


def test_ts_hardcoded_api_path(analyzer, tmp_path):
    _write(tmp_path, "service.ts", """\
        const data = await fetch('/api/epics');
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-api-path" for f in findings)


def test_router_file_api_path_exempt(analyzer, tmp_path):
    """Router/route definition files may define API paths — exempt."""
    _write(tmp_path, "router.ts", """\
        const EPICS_PATH = '/api/epics';
        const TASKS_PATH = '/api/tasks';
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-api-path" for f in findings)


def test_routes_file_api_path_exempt(analyzer, tmp_path):
    _write(tmp_path, "routes.py", """\
        TASK_ENDPOINT = '/api/v1/tasks'
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-api-path" for f in findings)


# ─── Hardcoded Status Strings ─────────────────────────────────────────────────


def test_py_hardcoded_status_string(analyzer, tmp_path):
    _write(tmp_path, "task_service.py", """\
        if task.state == 'pending':
            process(task)
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-status" and "pending" in f.message for f in findings)


def test_ts_triple_eq_status(analyzer, tmp_path):
    _write(tmp_path, "store.ts", """\
        if (task.state === 'in_progress') {
            showSpinner();
        }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-status" and "in_progress" in f.message for f in findings)


def test_ts_not_equal_status(analyzer, tmp_path):
    _write(tmp_path, "store.ts", """\
        if (state !== 'done') { retry(); }
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(f.category == "hardcoded-status" and "done" in f.message for f in findings)


def test_arbitrary_string_comparison_not_flagged(analyzer, tmp_path):
    """Generic short strings in comparisons that aren't status words: must not be flagged."""
    _write(tmp_path, "parser.py", """\
        if token == 'abc':
            pass
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "hardcoded-status" for f in findings)


# ─── Integration: run_all includes magic-values ───────────────────────────────


def test_run_all_includes_magic_values_analyzer(tmp_path):
    """MagicValuesAnalyzer must be auto-discovered by AnalyzerRegistry."""
    from scripts.analyzers import AnalyzerRegistry

    AnalyzerRegistry.reset()
    analyzers = AnalyzerRegistry.discover()
    names = [a.name for a in analyzers]
    assert "magic-values" in names
