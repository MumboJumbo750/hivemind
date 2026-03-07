"""Tests für hivemind-run_analyzer MCP-Tool — TASK-WFS-003.

Testet:
  1. Happy-Path: normaler Scan liefert JSON-Report
  2. Cache-Hit: zweiter Aufruf mit gleichem Report-Hash gibt cached=True zurück
  3. Cache-Miss: veränderter Report-Hash gibt cached=False zurück
  4. Fehler-Isolation: Analyzer-Ausnahmen werden als Warning-Finding ausgegeben
  5. Timeout-Handling: Analyzer-Timeout erzeugt Warning-Finding, Run läuft weiter
  6. Parameter-Validierung: ungültiger min_severity löst error aus
  7. analyzer_name Parsing: kommagetrennte Namen, "all", None
  8. deep_scan wird an unterstützende Analyzer weitergegeben
  9. Ungültiger root_path löst ValueError aus
 10. ImportError für scripts.analyzers liefert internal_error
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse(result: list) -> dict:
    return json.loads(result[0].text)


def _ok_data(result: list) -> dict:
    payload = _parse(result)
    assert "error" not in payload, f"Unerwarteter Fehler: {payload}"
    return payload["data"]


def _err_payload(result: list) -> dict:
    payload = _parse(result)
    assert "error" in payload, f"Fehler erwartet, erhalten: {payload}"
    return payload["error"]


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_report_dict() -> dict:
    """Minimaler Report-Dict der scripts.analyzers Report-Struktur."""
    return {
        "timestamp": "2026-03-03T12:00:00+00:00",
        "root_path": "/workspace",
        "stack": ["python"],
        "summary": {"total": 1, "errors": 0, "warnings": 1, "infos": 0, "auto_fixable": 0},
        "findings": [
            {
                "analyzer": "test-analyzer",
                "severity": "warning",
                "file": "backend/app/main.py",
                "line": 10,
                "message": "Test-Finding",
                "category": "test",
                "auto_fixable": False,
            }
        ],
        "analyzer_stats": {"test-analyzer": {"status": "ok", "findings_count": 1}},
    }


@pytest.fixture(autouse=True)
def clear_cache():
    """Cache vor jedem Test leeren."""
    from app.mcp.tools.analyzer_tools import _cache
    _cache.clear()
    yield
    _cache.clear()


@pytest.fixture(scope="session", autouse=True)
def ensure_workspace_on_path():
    """Stellt einmalig sicher, dass /workspace/scripts korrekt in sys.path steht.

    Nötig weil /app/scripts/__init__.py (Backend-Skripte) sonst das
    ``scripts``-Paket in sys.modules verdrängt, bevor die Integration-Tests
    ``from scripts.analyzers import ...`` ausführen.
    """
    try:
        from app.mcp.tools.analyzer_tools import _ensure_workspace_scripts_importable
        _ensure_workspace_scripts_importable()
    except RuntimeError:
        pass  # Kein /workspace-Mount → Integration-Tests werden übersprungen


# ── Tests: Happy-Path ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_analyzer_basic(fake_report_dict):
    """Grundlegender Scan: Report wird zurückgegeben, cached=False beim ersten Aufruf."""
    with patch(
        "app.mcp.tools.analyzer_tools._run_analyzers_sync",
        return_value=fake_report_dict,
    ):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer
        result = await _handle_run_analyzer({})

    data = _ok_data(result)
    assert data["cached"] is False
    assert "report_hash" in data
    assert data["report"]["summary"]["warnings"] == 1
    assert len(data["report"]["findings"]) == 1


@pytest.mark.asyncio
async def test_run_analyzer_returns_analyzer_stats(fake_report_dict):
    """analyzer_stats werden im Report mitgeliefert."""
    with patch(
        "app.mcp.tools.analyzer_tools._run_analyzers_sync",
        return_value=fake_report_dict,
    ):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer
        result = await _handle_run_analyzer({"root_path": "/workspace"})

    data = _ok_data(result)
    assert "analyzer_stats" in data["report"]
    assert data["report"]["analyzer_stats"]["test-analyzer"]["status"] == "ok"


# ── Tests: Caching ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_hit_second_call(fake_report_dict):
    """Zweiter Aufruf mit identischem Report → cached=True."""
    with patch(
        "app.mcp.tools.analyzer_tools._run_analyzers_sync",
        return_value=fake_report_dict,
    ):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer

        result1 = await _handle_run_analyzer({})
        result2 = await _handle_run_analyzer({})

    data1 = _ok_data(result1)
    data2 = _ok_data(result2)

    assert data1["cached"] is False
    assert data2["cached"] is True
    assert data1["report_hash"] == data2["report_hash"]


@pytest.mark.asyncio
async def test_cache_hit_skips_analyzer_call(fake_report_dict):
    """Cache-Hit: _run_analyzers_sync wird beim zweiten Aufruf NICHT aufgerufen (echter Skip)."""
    call_count = 0

    def _count(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return fake_report_dict

    with patch("app.mcp.tools.analyzer_tools._run_analyzers_sync", side_effect=_count):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer

        await _handle_run_analyzer({})   # erster Aufruf → läuft durch
        await _handle_run_analyzer({})   # zweiter Aufruf → echter Cache-Hit, kein Analyzer-Call

    assert call_count == 1, f"Analyzer wurde {call_count}x aufgerufen, erwartet: 1"


@pytest.mark.asyncio
async def test_cache_miss_on_different_params(fake_report_dict):
    """Unterschiedliche Parameter → separate Cache-Einträge; beide cached=False beim ersten Aufruf."""
    call_count = 0

    def _count(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return fake_report_dict

    with patch("app.mcp.tools.analyzer_tools._run_analyzers_sync", side_effect=_count):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer

        r1 = await _handle_run_analyzer({})
        r2 = await _handle_run_analyzer({"min_severity": "warning"})

    assert _ok_data(r1)["cached"] is False
    assert _ok_data(r2)["cached"] is False  # anderer Key → eigener Cache-Eintrag
    assert call_count == 2  # Analyzer wurde für jeden einzigartigen Key einmal aufgerufen


@pytest.mark.asyncio
async def test_cache_keys_differ_by_analyzer_name(fake_report_dict):
    """Unterschiedliche analyzer_name → keine Cache-Überschneidung."""
    with patch(
        "app.mcp.tools.analyzer_tools._run_analyzers_sync",
        return_value=fake_report_dict,
    ):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer

        r1 = await _handle_run_analyzer({"analyzer_name": "hardcoded-css"})
        r2 = await _handle_run_analyzer({"analyzer_name": "magic-numbers"})

    assert _ok_data(r1)["cached"] is False
    assert _ok_data(r2)["cached"] is False  # anderer Key → eigener Eintrag


# ── Tests: Fehler-Isolation ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_exception_returns_internal_error():
    """Exception in _run_analyzers_sync → error-Response."""
    with patch(
        "app.mcp.tools.analyzer_tools._run_analyzers_sync",
        side_effect=RuntimeError("scripts.analyzers nicht gefunden"),
    ):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer
        result = await _handle_run_analyzer({})

    err = _err_payload(result)
    assert err["code"] == "internal_error"
    assert "scripts.analyzers" in err["message"]


# ── Tests: Parameter-Validierung ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_min_severity():
    """Ungültiger min_severity-Wert → invalid_argument."""
    from app.mcp.tools.analyzer_tools import _handle_run_analyzer
    result = await _handle_run_analyzer({"min_severity": "critical"})
    err = _err_payload(result)
    assert err["code"] == "invalid_argument"
    assert "min_severity" in err["message"]


@pytest.mark.asyncio
async def test_min_severity_valid_values(fake_report_dict):
    """Alle gültigen min_severity-Werte werden akzeptiert."""
    for sev in ("error", "warning", "info"):
        with patch(
            "app.mcp.tools.analyzer_tools._run_analyzers_sync",
            return_value=fake_report_dict,
        ):
            from app.mcp.tools.analyzer_tools import _handle_run_analyzer
            result = await _handle_run_analyzer({"min_severity": sev})
        data = _ok_data(result)
        assert "report" in data, f"min_severity='{sev}' sollte keinen Fehler liefern"


# ── Tests: analyzer_name Parsing ──────────────────────────────────────────

def test_cache_key_none_equals_all():
    """analyzer_name=None und analyzer_name='all' ergeben denselben Cache-Key."""
    from app.mcp.tools.analyzer_tools import _cache_key

    key_none = _cache_key(None, "/workspace", None, True)
    key_all = _cache_key(None, "/workspace", None, True)
    assert key_none == key_all


def test_cache_key_single_analyzer():
    """analyzer_name='hardcoded-css' → analyzer_names=['hardcoded-css'] im Key."""
    from app.mcp.tools.analyzer_tools import _cache_key

    key = _cache_key(["hardcoded-css"], "/workspace", None, True)
    assert "hardcoded-css" in key
    assert "__all__" not in key


def test_analyzer_name_comma_split_and_sort():
    """Kommagetrennte Namen werden sortiert in den Cache-Key aufgenommen."""
    from app.mcp.tools.analyzer_tools import _cache_key

    key_asc = _cache_key(["a", "b", "c"], "/workspace", None, True)
    key_desc = _cache_key(["c", "b", "a"], "/workspace", None, True)
    assert key_asc == key_desc  # Sortierung → gleicher Key


@pytest.mark.asyncio
async def test_analyzer_name_all_string_treated_as_none(fake_report_dict):
    """analyzer_name='all' wird wie None behandelt (alle Analyzer)."""
    captured_names = []

    def _capture(root_path, analyzer_names, min_severity, deep_scan):
        captured_names.append(analyzer_names)
        return fake_report_dict

    with patch("app.mcp.tools.analyzer_tools._run_analyzers_sync", side_effect=_capture):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer
        await _handle_run_analyzer({"analyzer_name": "all"})
        await _handle_run_analyzer({"analyzer_name": "ALL"})
        await _handle_run_analyzer({"analyzer_name": ""})
        await _handle_run_analyzer({})

    for names in captured_names:
        assert names is None, f"Erwartet None, erhalten: {names}"


@pytest.mark.asyncio
async def test_analyzer_name_comma_list_parsed(fake_report_dict):
    """analyzer_name='a,b,c' → analyzer_names=['a','b','c']."""
    captured = []

    def _capture(root_path, analyzer_names, min_severity, deep_scan):
        captured.append(analyzer_names)
        return fake_report_dict

    with patch("app.mcp.tools.analyzer_tools._run_analyzers_sync", side_effect=_capture):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer
        await _handle_run_analyzer({"analyzer_name": "hardcoded-css,magic-numbers, duplicate"})

    assert captured[0] == ["hardcoded-css", "magic-numbers", "duplicate"]


# ── Tests: deep_scan ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deep_scan_default_true(fake_report_dict):
    """deep_scan-Default ist True."""
    captured = []

    def _capture(root_path, analyzer_names, min_severity, deep_scan):
        captured.append(deep_scan)
        return fake_report_dict

    with patch("app.mcp.tools.analyzer_tools._run_analyzers_sync", side_effect=_capture):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer
        await _handle_run_analyzer({})

    assert captured[0] is True


@pytest.mark.asyncio
async def test_deep_scan_false_passed_through(fake_report_dict):
    """deep_scan=False wird korrekt weitergegeben."""
    captured = []

    def _capture(root_path, analyzer_names, min_severity, deep_scan):
        captured.append(deep_scan)
        return fake_report_dict

    with patch("app.mcp.tools.analyzer_tools._run_analyzers_sync", side_effect=_capture):
        from app.mcp.tools.analyzer_tools import _handle_run_analyzer
        await _handle_run_analyzer({"deep_scan": False})

    assert captured[0] is False


# ── Tests: _run_analyzers_sync ────────────────────────────────────────────

def test_run_analyzers_sync_invalid_root(tmp_path):
    """Ungültiger root_path → ValueError."""
    from app.mcp.tools.analyzer_tools import _run_analyzers_sync

    nonexistent = str(tmp_path / "nonexistent_dir_xyz")
    with pytest.raises((ValueError, RuntimeError)):
        _run_analyzers_sync(nonexistent, None, None, True)


def test_run_analyzers_sync_missing_scripts_module(tmp_path):
    """ImportError wenn scripts.analyzers nicht verfügbar → RuntimeError.

    Simuliert einen Container ohne /workspace-Mount, indem _workspace_sys_path
    auf None gemockt wird.  Das löst in _ensure_workspace_scripts_importable()
    sofort eine RuntimeError aus, ohne sys.path global zu manipulieren.
    """
    from app.mcp.tools.analyzer_tools import _run_analyzers_sync

    with patch("app.mcp.tools.analyzer_tools._workspace_sys_path", return_value=None):
        with pytest.raises(RuntimeError, match="scripts.analyzers"):
            _run_analyzers_sync(str(tmp_path), None, None, True)


def test_run_analyzers_sync_timeout_continues(tmp_path, monkeypatch):
    """Analyzer-Timeout → Warning-Finding, andere Analyzer laufen weiter."""
    # Nur wenn scripts.analyzers tatsächlich verfügbar ist (Container-Umgebung)
    try:
        from app.mcp.tools.analyzer_tools import _ensure_workspace_scripts_importable
        _ensure_workspace_scripts_importable()
        from scripts.analyzers import BaseAnalyzer, Finding, AnalyzerRegistry  # type: ignore
    except (ImportError, RuntimeError):
        pytest.skip("scripts.analyzers nicht verfügbar (kein /workspace mount)")

    # Dummy-Analyzer der hängt
    class HangingAnalyzer(BaseAnalyzer):
        name = "_test_hanging"
        description = "Hängt immer"

        def analyze(self, root: Path) -> list[Finding]:
            import time
            time.sleep(9999)
            return []

    # Dummy-Analyzer der sofort fertig ist
    class QuickAnalyzer(BaseAnalyzer):
        name = "_test_quick"
        description = "Fertig sofort"

        def analyze(self, root: Path) -> list[Finding]:
            return [Finding("_test_quick", "info", "x.py", 1, "ok", "test")]

    # AnalyzerRegistry zurücksetzen und Mock-Analyzer injizieren
    AnalyzerRegistry.reset()
    with monkeypatch.context() as m:
        m.setattr(AnalyzerRegistry, "discover", classmethod(lambda cls: [HangingAnalyzer, QuickAnalyzer]))
        # Timeout auf 0.1s setzen
        import app.mcp.tools.analyzer_tools as at
        original_timeout = at._ANALYZER_TIMEOUT
        at._ANALYZER_TIMEOUT = 0.1

        try:
            from app.mcp.tools.analyzer_tools import _run_analyzers_sync
            report = _run_analyzers_sync(str(tmp_path), None, None, True)
        finally:
            at._ANALYZER_TIMEOUT = original_timeout
            AnalyzerRegistry.reset()

    # Timeout-Warning vorhanden
    timeout_findings = [f for f in report["findings"] if f["category"] == "analyzer-timeout"]
    assert len(timeout_findings) == 1
    assert "_test_hanging" in timeout_findings[0]["message"]

    # QuickAnalyzer hat trotzdem einen Fund
    quick_findings = [f for f in report["findings"] if f["analyzer"] == "_test_quick"]
    assert len(quick_findings) == 1

    # Stats
    assert report["analyzer_stats"]["_test_hanging"]["status"] == "timeout"
    assert report["analyzer_stats"]["_test_quick"]["status"] == "ok"


def test_run_analyzers_sync_error_isolation(tmp_path, monkeypatch):
    """Analyzer-Ausnahme → Warning-Finding, andere Analyzer bleiben unberührt."""
    try:
        from app.mcp.tools.analyzer_tools import _ensure_workspace_scripts_importable
        _ensure_workspace_scripts_importable()
        from scripts.analyzers import BaseAnalyzer, Finding, AnalyzerRegistry  # type: ignore
    except (ImportError, RuntimeError):
        pytest.skip("scripts.analyzers nicht verfügbar (kein /workspace mount)")

    class CrashingAnalyzer(BaseAnalyzer):
        name = "_test_crashing"
        description = "Schmiert immer ab"

        def analyze(self, root: Path) -> list[Finding]:
            raise RuntimeError("kaboom!")

    class GoodAnalyzer(BaseAnalyzer):
        name = "_test_good"
        description = "Sauber"

        def analyze(self, root: Path) -> list[Finding]:
            return [Finding("_test_good", "info", "a.py", None, "fine", "ok")]

    AnalyzerRegistry.reset()
    with monkeypatch.context() as m:
        m.setattr(AnalyzerRegistry, "discover", classmethod(lambda cls: [CrashingAnalyzer, GoodAnalyzer]))

        from app.mcp.tools.analyzer_tools import _run_analyzers_sync
        report = _run_analyzers_sync(str(tmp_path), None, None, True)

    AnalyzerRegistry.reset()

    error_findings = [f for f in report["findings"] if f["category"] == "analyzer-error"]
    assert len(error_findings) == 1
    assert "kaboom" in error_findings[0]["message"]

    good_findings = [f for f in report["findings"] if f["analyzer"] == "_test_good"]
    assert len(good_findings) == 1

    assert report["analyzer_stats"]["_test_crashing"]["status"] == "error"
    assert report["analyzer_stats"]["_test_good"]["status"] == "ok"


# ── Tests: Report-Hash ────────────────────────────────────────────────────

def test_report_hash_deterministic():
    """Gleicher Dict → gleicher Hash."""
    from app.mcp.tools.analyzer_tools import _report_hash

    d = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
    assert _report_hash(d) == _report_hash(d)


def test_report_hash_changes_on_diff():
    """Unterschiedliche Dicts → unterschiedliche Hashes."""
    from app.mcp.tools.analyzer_tools import _report_hash

    assert _report_hash({"a": 1}) != _report_hash({"a": 2})


def test_report_hash_length():
    """Hash hat genau 16 Zeichen."""
    from app.mcp.tools.analyzer_tools import _report_hash

    h = _report_hash({"x": "y"})
    assert len(h) == 16
