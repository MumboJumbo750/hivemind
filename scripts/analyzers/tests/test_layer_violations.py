"""
Unit tests for LayerViolationsAnalyzer.

Run (canonical):
    make health-test

Or directly:
    podman compose exec -w /workspace -e PYTHONPATH=/workspace:/app backend \
        /app/.venv/bin/pytest scripts/analyzers/tests/test_layer_violations.py -v
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.analyzers.layer_violations import LayerViolationsAnalyzer, LayerRule


@pytest.fixture
def analyzer():
    return LayerViolationsAnalyzer()


def _write(tmp: Path, rel: str, content: str) -> Path:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ─── Built-in: BE Router → no direct model import ─────────────────────────────

def test_router_imports_model_is_error(analyzer, tmp_path):
    _write(tmp_path, "backend/app/routers/tasks.py", """\
        from fastapi import APIRouter
        from app.models.task import Task

        router = APIRouter()
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(
        f.severity == "error" and "router" in f.message.lower() and f.category == "layer-violation"
        for f in findings
    )


def test_router_imports_schema_is_ok(analyzer, tmp_path):
    _write(tmp_path, "backend/app/routers/tasks.py", """\
        from fastapi import APIRouter
        from app.schemas.task import TaskSchema

        router = APIRouter()
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "layer-violation" for f in findings)


def test_router_init_skipped(analyzer, tmp_path):
    """__init__.py in routers should not be checked."""
    _write(tmp_path, "backend/app/routers/__init__.py", """\
        from app.models.base import Base
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "layer-violation" for f in findings)


# ─── Built-in: BE Service → no router import ─────────────────────────────────

def test_service_imports_router_is_error(analyzer, tmp_path):
    _write(tmp_path, "backend/app/services/task_service.py", """\
        from app.routers.tasks import router
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(
        f.severity == "error" and "circular" in f.message.lower()
        for f in findings
    )


def test_service_no_router_is_ok(analyzer, tmp_path):
    _write(tmp_path, "backend/app/services/task_service.py", """\
        from app.models.task import Task
        from sqlalchemy.orm import Session
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "layer-violation" for f in findings)


# ─── Built-in: FE UI primitive → no store import ─────────────────────────────

def test_ui_component_imports_store_is_error(analyzer, tmp_path):
    _write(tmp_path, "frontend/src/components/ui/Button.vue", """\
        <template><button /></template>
        <script setup lang="ts">
        import { useProjectStore } from '@/stores/project'
        </script>
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(
        f.severity == "error" and "layer-violation" == f.category
        for f in findings
    )


def test_ui_component_clean_is_ok(analyzer, tmp_path):
    _write(tmp_path, "frontend/src/components/ui/Badge.vue", """\
        <template><span><slot /></span></template>
        <script setup lang="ts">
        defineProps<{ label: string }>()
        </script>
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "layer-violation" for f in findings)


# ─── Built-in: FE Composable → no component import ───────────────────────────

def test_composable_imports_component_is_warning(analyzer, tmp_path):
    _write(tmp_path, "frontend/src/composables/useTheme.ts", """\
        import Button from '@/components/ui/Button.vue'
        export function useTheme() {}
    """)
    findings = analyzer.analyze(tmp_path)
    assert any(
        f.severity == "warning" and "layer-violation" == f.category
        for f in findings
    )


def test_composable_no_component_is_ok(analyzer, tmp_path):
    _write(tmp_path, "frontend/src/composables/useTheme.ts", """\
        import { ref } from 'vue'
        export function useTheme() {
            return ref('dark')
        }
    """)
    findings = analyzer.analyze(tmp_path)
    assert not any(f.category == "layer-violation" for f in findings)


# ─── Custom rules ────────────────────────────────────────────────────────────

def test_custom_rule_is_applied(tmp_path):
    custom_rule = LayerRule(
        name="no-lodash-in-utils",
        file_pattern="src/utils/*.ts",
        forbidden_imports=["from 'lodash'", 'from "lodash"'],
        message="Utils should not import lodash directly",
        severity="warning",
    )
    a = LayerViolationsAnalyzer(extra_rules=[custom_rule])
    _write(tmp_path, "src/utils/helpers.ts", """\
        import _ from 'lodash'
        export function pick(obj: any, key: string) { return _[key] }
    """)
    findings = a.analyze(tmp_path)
    assert any("lodash" in f.message.lower() and f.severity == "warning" for f in findings)


def test_custom_rule_ok_when_no_violation(tmp_path):
    custom_rule = LayerRule(
        name="no-lodash-in-utils",
        file_pattern="src/utils/*.ts",
        forbidden_imports=["from 'lodash'"],
        message="No lodash",
        severity="warning",
    )
    a = LayerViolationsAnalyzer(extra_rules=[custom_rule])
    _write(tmp_path, "src/utils/helpers.ts", """\
        export function pick(obj: Record<string, unknown>, key: string) {
            return obj[key]
        }
    """)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "layer-violation" for f in findings)
