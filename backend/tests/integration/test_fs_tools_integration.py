"""Integration-Tests für MCP Filesystem-Tools — TASK-WFS-006.

Testet den vollständigen HTTP-Stack:
  client (AsyncClient/ASGI) → MCP-Router (/api/mcp/call) → fs-Handler

Abgedeckte Szenarien:
  1. fs_read liest existierende Datei korrekt
  2. fs_write erstellt Datei, Änderung auf Dateisystem (Host-Mount) ist sichtbar
  3. fs_list gibt korrekte Struktur zurück
  4. fs_search findet Grep-Matches
  5. Path-Traversal wird geblockt (../../etc/passwd)
  6. Deny-List wird in allen Tools respektiert
  7. run_analyzer gibt validen JSON-Report zurück
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────

def _call_result(response) -> dict:
    """Parse MCP call response → inneres Payload-Dict."""
    resp_json = response.json()
    assert "result" in resp_json, f"Kein 'result' in Response: {resp_json}"
    text = resp_json["result"][0]["text"]
    return json.loads(text)


def _ok(response) -> dict:
    payload = _call_result(response)
    assert "error" not in payload, f"Unerwarteter Fehler: {payload}"
    return payload["data"]


def _err(response) -> dict:
    payload = _call_result(response)
    assert "error" in payload, f"Fehler erwartet, erhalten: {payload}"
    return payload["error"]


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def ws(tmp_path: Path):
    """Temporärer Workspace mit bekannten Testdateien."""
    (tmp_path / "hello.txt").write_text("Zeile 1\nZeile 2\nZeile 3\n")
    (tmp_path / "data.py").write_text("# Python-Datei\nANSWER = 42\n")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested content\n")
    (tmp_path / ".env").write_text("DB_PASSWORD=supersecret\n")
    (tmp_path / ".env.local").write_text("TOKEN=abc123\n")
    return tmp_path


def _patch_ws(ws: Path):
    """Patcht _workspace_root auf ein Temp-Verzeichnis."""
    return patch("app.mcp.tools.fs_tools._workspace_root", return_value=ws)


def _patch_deny(patterns: list[str]):
    return patch("app.mcp.tools.fs_tools._deny_patterns", return_value=patterns)


# ── Tests: fs_read ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_read_existing_file(client, ws: Path) -> None:
    """fs_read liest existierende Datei korrekt über HTTP MCP-Endpoint."""
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_read", "arguments": {"path": "hello.txt"}},
        )

    assert response.status_code == 200
    data = _ok(response)
    assert data["content"] == "Zeile 1\nZeile 2\nZeile 3\n"
    assert data["total_lines"] == 3
    assert "path" in data
    assert "encoding" in data


@pytest.mark.asyncio
async def test_fs_read_line_range(client, ws: Path) -> None:
    """fs_read gibt nur den angeforderten Zeilenbereich zurück."""
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_read", "arguments": {
                "path": "hello.txt",
                "start_line": 2,
                "end_line": 2,
            }},
        )

    assert response.status_code == 200
    data = _ok(response)
    assert "Zeile 2" in data["content"]
    assert "Zeile 1" not in data["content"]
    assert "Zeile 3" not in data["content"]


@pytest.mark.asyncio
async def test_fs_read_not_found(client, ws: Path) -> None:
    """fs_read liefert not_found für nicht existierende Datei."""
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_read", "arguments": {"path": "ghost.txt"}},
        )

    assert response.status_code == 200
    err = _err(response)
    assert err["code"] == "not_found"


# ── Tests: fs_write ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_write_file_visible_on_filesystem(client, ws: Path) -> None:
    """fs_write erstellt Datei — Änderung ist auf dem Dateisystem sofort sichtbar.

    Kerntest für Host-Mount-Integration: stellt sicher, dass fs_write tatsächlich
    schreibt und nicht nur im Speicher operiert. Im Container-Betrieb entspricht
    dies dem Host-sichtbaren Volume-Mount ./backend → /app.
    """
    content = "integration test content\n"
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_write", "arguments": {
                "path": "written.txt",
                "content": content,
            }},
        )

    assert response.status_code == 200
    data = _ok(response)
    assert data["bytes_written"] == len(content.encode("utf-8"))

    # Verifiziere Host-sichtbare Änderung: Datei muss physisch existieren
    target = ws / "written.txt"
    assert target.exists(), "Datei muss nach fs_write auf dem Dateisystem existieren!"
    assert target.read_text() == content, "Dateiinhalt muss exakt übereinstimmen!"


@pytest.mark.asyncio
async def test_fs_write_creates_subdirectory(client, ws: Path) -> None:
    """fs_write legt fehlende Unterverzeichnisse automatisch an (create_dirs=True)."""
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_write", "arguments": {
                "path": "newdir/subdir/deep.txt",
                "content": "tiefe Datei",
            }},
        )

    assert response.status_code == 200
    _ok(response)
    assert (ws / "newdir" / "subdir" / "deep.txt").read_text() == "tiefe Datei"


@pytest.mark.asyncio
async def test_fs_write_overwrites_existing(client, ws: Path) -> None:
    """fs_write überschreibt eine vorhandene Datei atomisch."""
    original = ws / "hello.txt"
    old_content = original.read_text()

    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_write", "arguments": {
                "path": "hello.txt",
                "content": "NEU",
            }},
        )

    assert response.status_code == 200
    _ok(response)
    assert original.read_text() == "NEU"
    assert original.read_text() != old_content


# ── Tests: fs_list ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_list_correct_structure(client, ws: Path) -> None:
    """fs_list gibt korrekte Verzeichnisstruktur mit erwarteten Feldern zurück."""
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_list", "arguments": {"path": "."}},
        )

    assert response.status_code == 200
    data = _ok(response)

    # Top-Level-Felder
    assert "entries" in data
    assert "truncated" in data
    assert "path" in data
    assert isinstance(data["entries"], list)
    assert isinstance(data["truncated"], bool)

    names = {e["name"] for e in data["entries"]}
    assert "hello.txt" in names
    assert "subdir" in names

    # Jeder Eintrag hat die erwarteten Pflichtfelder
    for entry in data["entries"]:
        assert "name" in entry, f"Eintrag ohne 'name': {entry}"
        assert "type" in entry, f"Eintrag ohne 'type': {entry}"
        assert "path" in entry, f"Eintrag ohne 'path': {entry}"
        assert entry["type"] in ("file", "dir"), f"Ungültiger Typ: {entry['type']}"

    # Dateien haben eine 'size'-Angabe
    file_entries = [e for e in data["entries"] if e["type"] == "file"]
    for fe in file_entries:
        assert "size" in fe, f"Datei-Eintrag ohne 'size': {fe}"


@pytest.mark.asyncio
async def test_fs_list_recursive(client, ws: Path) -> None:
    """fs_list(recursive=True) liefert auch Einträge aus Unterverzeichnissen."""
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_list", "arguments": {"path": ".", "recursive": True}},
        )

    assert response.status_code == 200
    data = _ok(response)
    paths = {e["path"] for e in data["entries"]}
    assert any("nested.txt" in p for p in paths), "nested.txt muss im rekursiven Listing erscheinen"


@pytest.mark.asyncio
async def test_fs_list_not_directory(client, ws: Path) -> None:
    """fs_list auf eine Datei liefert not_a_directory."""
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_list", "arguments": {"path": "hello.txt"}},
        )

    assert response.status_code == 200
    err = _err(response)
    assert err["code"] == "not_a_directory"


# ── Tests: fs_search ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_search_finds_grep_matches(client, ws: Path) -> None:
    """fs_search findet Grep-Matches mit korrekter Struktur je Treffer."""
    with _patch_ws(ws), _patch_deny([]):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_search", "arguments": {
                "pattern": "ANSWER",
                "path": ".",
            }},
        )

    assert response.status_code == 200
    data = _ok(response)
    assert data["total"] >= 1

    paths = {r["path"] for r in data["results"]}
    assert any("data.py" in p for p in paths), "ANSWER muss in data.py gefunden werden"

    # Jeder Treffer hat die erwarteten Felder
    for match in data["results"]:
        assert "path" in match, f"Treffer ohne 'path': {match}"
        assert "line" in match, f"Treffer ohne 'line': {match}"
        assert "content" in match, f"Treffer ohne 'content': {match}"
        assert isinstance(match["line"], int)


@pytest.mark.asyncio
async def test_fs_search_no_match(client, ws: Path) -> None:
    """fs_search gibt total=0 und leere Liste zurück wenn kein Treffer."""
    with _patch_ws(ws), _patch_deny([]):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_search", "arguments": {
                "pattern": "XYZZY_NEVER_EXISTS_12345",
                "path": ".",
            }},
        )

    assert response.status_code == 200
    data = _ok(response)
    assert data["total"] == 0
    assert data["results"] == []


@pytest.mark.asyncio
async def test_fs_search_regex_pattern(client, ws: Path) -> None:
    """fs_search unterstützt Regex-Patterns."""
    with _patch_ws(ws), _patch_deny([]):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_search", "arguments": {
                "pattern": r"Zeile\s+\d+",
                "path": ".",
                "regex": True,
            }},
        )

    assert response.status_code == 200
    data = _ok(response)
    assert data["total"] >= 1


# ── Tests: Sicherheit ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_path_traversal_blocked_read(client, ws: Path) -> None:
    """Path-Traversal mit ../../etc/passwd wird von fs_read mit access_denied geblockt."""
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_read", "arguments": {"path": "../../etc/passwd"}},
        )

    assert response.status_code == 200
    err = _err(response)
    assert err["code"] == "access_denied"


@pytest.mark.asyncio
async def test_path_traversal_blocked_write(client, ws: Path) -> None:
    """Path-Traversal wird auch von fs_write geblockt."""
    with _patch_ws(ws):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_write", "arguments": {
                "path": "../outside.txt",
                "content": "evil",
            }},
        )

    assert response.status_code == 200
    err = _err(response)
    assert err["code"] == "access_denied"


@pytest.mark.asyncio
async def test_deny_list_respected(client, ws: Path) -> None:
    """Deny-List wird in fs_read, fs_write und fs_list konsistent respektiert."""
    deny = [".env", ".env.local"]

    with _patch_ws(ws), _patch_deny(deny):
        # fs_read auf .env → access_denied
        resp_read = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_read", "arguments": {"path": ".env"}},
        )
        # fs_write auf .env → access_denied
        resp_write = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_write", "arguments": {"path": ".env", "content": "BAD=1"}},
        )
        # fs_list: .env darf nicht auftauchen
        resp_list = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_list", "arguments": {"path": "."}},
        )
        # fs_search: .env darf nicht in Ergebnissen erscheinen
        resp_search = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/fs_search", "arguments": {
                "pattern": "supersecret",
                "path": ".",
            }},
        )

    assert _err(resp_read)["code"] == "access_denied"
    assert _err(resp_write)["code"] == "access_denied"

    list_data = _ok(resp_list)
    names = {e["name"] for e in list_data["entries"]}
    assert ".env" not in names, ".env darf nicht in fs_list erscheinen!"
    assert ".env.local" not in names, ".env.local darf nicht in fs_list erscheinen!"

    search_data = _ok(resp_search)
    search_paths = {r["path"] for r in search_data["results"]}
    assert not any(".env" in p for p in search_paths), ".env darf nicht in fs_search erscheinen!"


# ── Tests: run_analyzer ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_analyzer_valid_json_report(client) -> None:
    """run_analyzer liefert validen JSON-Report mit korrekter Struktur."""
    fake_report = {
        "timestamp": "2026-03-03T12:00:00+00:00",
        "root_path": "/workspace",
        "stack": ["python"],
        "summary": {
            "total": 1,
            "errors": 0,
            "warnings": 1,
            "infos": 0,
            "auto_fixable": 0,
        },
        "findings": [
            {
                "analyzer": "test-analyzer",
                "severity": "warning",
                "file": "backend/app/main.py",
                "line": 1,
                "message": "WFS-006 Integration Test Finding",
                "category": "test",
                "auto_fixable": False,
            }
        ],
        "analyzer_stats": {"test-analyzer": {"status": "ok", "findings_count": 1}},
    }

    with patch("app.mcp.tools.analyzer_tools._run_analyzers_sync", return_value=fake_report):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/run_analyzer", "arguments": {}},
        )

    assert response.status_code == 200
    data = _ok(response)

    # Pflichtfelder im Report-Response
    assert "report" in data, "run_analyzer muss 'report' liefern"
    assert "report_hash" in data, "run_analyzer muss 'report_hash' liefern"
    assert "cached" in data, "run_analyzer muss 'cached' liefern"
    assert isinstance(data["cached"], bool)

    # Report-Struktur validieren
    report = data["report"]
    assert "summary" in report
    assert "findings" in report
    assert "analyzer_stats" in report
    assert isinstance(report["findings"], list)
    assert isinstance(report["summary"], dict)

    # Summary-Felder
    summary = report["summary"]
    for field in ("total", "errors", "warnings", "infos", "auto_fixable"):
        assert field in summary, f"summary.{field} fehlt"
        assert isinstance(summary[field], int)

    # Findings-Struktur
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    for field in ("analyzer", "severity", "file", "line", "message"):
        assert field in finding, f"finding.{field} fehlt"


@pytest.mark.asyncio
async def test_run_analyzer_cached_false_first_call(client) -> None:
    """Erster run_analyzer-Aufruf liefert cached=False."""
    from app.mcp.tools.analyzer_tools import _cache
    _cache.clear()

    fake_report = {
        "timestamp": "2026-03-03T12:00:00+00:00",
        "root_path": "/workspace",
        "stack": [],
        "summary": {"total": 0, "errors": 0, "warnings": 0, "infos": 0, "auto_fixable": 0},
        "findings": [],
        "analyzer_stats": {},
    }

    with patch("app.mcp.tools.analyzer_tools._run_analyzers_sync", return_value=fake_report):
        response = await client.post(
            "/api/mcp/call",
            json={"tool": "hivemind/run_analyzer", "arguments": {}},
        )

    assert response.status_code == 200
    data = _ok(response)
    assert data["cached"] is False
