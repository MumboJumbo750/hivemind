"""Regressionstests für MCP Filesystem-Tools — TASK-WFS-002.

Testet Sicherheits-Fixes (QA-Review #1):
  1. fs_list filtert Deny-List-Einträge (war Bug: .env wurde gelistet)
  2. fs_search überspringt Binary-Dateien (war Bug: NUL-Bytes wurden gematcht)
  3. Grundfunktionalität aller 5 Tools (fs_read, fs_write, fs_list, fs_search, fs_stat)
  4. Path-Traversal- und Sandbox-Schutz
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcp.tools.fs_tools import (
    _handle_fs_list,
    _handle_fs_read,
    _handle_fs_search,
    _handle_fs_stat,
    _handle_fs_write,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse(result: list) -> dict:
    return json.loads(result[0].text)


def _ok(result: list) -> dict:
    payload = _parse(result)
    assert "error" not in payload, f"Unexpected error: {payload}"
    return payload["data"]


def _err(result: list) -> dict:
    payload = _parse(result)
    assert "error" in payload, f"Expected error, got: {payload}"
    return payload["error"]


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def ws(tmp_path: Path):
    """Werkzeug: temporärer Workspace mit bekannten Testdaten."""
    # Normale Dateien
    (tmp_path / "hello.txt").write_text("Zeile 1\nZeile 2\nZeile 3\n")
    (tmp_path / "secret.py").write_text("PASSWORD = 'hunter2'\n")
    # Verzeichnis
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested content\n")
    # Deny-List-Dateien
    (tmp_path / ".env").write_text("DB_PASSWORD=supersecret\n")
    (tmp_path / ".env.local").write_text("TOKEN=abc123\n")
    # Binary-Datei mit NUL-Bytes
    (tmp_path / "tmp_bin_test.bin").write_bytes(b"\x00\x01\x02SECRET\x00")
    return tmp_path


def _patch_ws(ws: Path):
    """Context-Manager: setzt Workspace-Root und Deny-List für Tests."""
    return patch(
        "app.mcp.tools.fs_tools._workspace_root",
        return_value=ws,
    )


def _patch_deny(patterns: list[str]):
    return patch(
        "app.mcp.tools.fs_tools._deny_patterns",
        return_value=patterns,
    )


# ── Tests: fs_read ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_read_full_file(ws: Path) -> None:
    with _patch_ws(ws):
        data = _ok(await _handle_fs_read({"path": "hello.txt"}))
    assert data["content"] == "Zeile 1\nZeile 2\nZeile 3\n"
    assert data["total_lines"] == 3


@pytest.mark.asyncio
async def test_fs_read_line_range(ws: Path) -> None:
    with _patch_ws(ws):
        data = _ok(await _handle_fs_read({"path": "hello.txt", "start_line": 2, "end_line": 3}))
    assert "Zeile 2" in data["content"]
    assert "Zeile 3" in data["content"]
    assert "Zeile 1" not in data["content"]


@pytest.mark.asyncio
async def test_fs_read_denied_file(ws: Path) -> None:
    with _patch_ws(ws), _patch_deny([".env", ".env.local"]):
        err = _err(await _handle_fs_read({"path": ".env"}))
    assert err["code"] == "access_denied"


@pytest.mark.asyncio
async def test_fs_read_not_found(ws: Path) -> None:
    with _patch_ws(ws):
        err = _err(await _handle_fs_read({"path": "nonexistent.txt"}))
    assert err["code"] == "not_found"


@pytest.mark.asyncio
async def test_fs_read_path_traversal(ws: Path) -> None:
    with _patch_ws(ws):
        err = _err(await _handle_fs_read({"path": "../../etc/passwd"}))
    assert err["code"] == "access_denied"


# ── Tests: fs_write ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_write_creates_file(ws: Path) -> None:
    with _patch_ws(ws):
        data = _ok(await _handle_fs_write({"path": "new_file.txt", "content": "hello world"}))
    assert data["bytes_written"] > 0
    assert (ws / "new_file.txt").read_text() == "hello world"


@pytest.mark.asyncio
async def test_fs_write_creates_subdirs(ws: Path) -> None:
    with _patch_ws(ws):
        data = _ok(await _handle_fs_write({"path": "deep/nested/file.txt", "content": "x"}))
    assert (ws / "deep" / "nested" / "file.txt").exists()


@pytest.mark.asyncio
async def test_fs_write_denied_path(ws: Path) -> None:
    with _patch_ws(ws), _patch_deny([".env"]):
        err = _err(await _handle_fs_write({"path": ".env", "content": "BAD=1"}))
    assert err["code"] == "access_denied"


@pytest.mark.asyncio
async def test_fs_write_path_traversal(ws: Path) -> None:
    with _patch_ws(ws):
        err = _err(await _handle_fs_write({"path": "../outside.txt", "content": "bad"}))
    assert err["code"] == "access_denied"


# ── Tests: fs_list ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_list_basic(ws: Path) -> None:
    with _patch_ws(ws):
        data = _ok(await _handle_fs_list({"path": "."}))
    names = {e["name"] for e in data["entries"]}
    assert "hello.txt" in names
    assert "subdir" in names


@pytest.mark.asyncio
async def test_fs_list_deny_list_entries_hidden(ws: Path) -> None:
    """Bug-Fix #1: .env darf NICHT in fs_list erscheinen."""
    with _patch_ws(ws), _patch_deny([".env", ".env.local"]):
        data = _ok(await _handle_fs_list({"path": "."}))
    names = {e["name"] for e in data["entries"]}
    assert ".env" not in names, ".env darf nicht in fs_list erscheinen!"
    assert ".env.local" not in names, ".env.local darf nicht in fs_list erscheinen!"


@pytest.mark.asyncio
async def test_fs_list_recursive(ws: Path) -> None:
    with _patch_ws(ws):
        data = _ok(await _handle_fs_list({"path": ".", "recursive": True}))
    paths = {e["path"] for e in data["entries"]}
    assert any("nested.txt" in p for p in paths)


@pytest.mark.asyncio
async def test_fs_list_not_a_directory(ws: Path) -> None:
    with _patch_ws(ws):
        err = _err(await _handle_fs_list({"path": "hello.txt"}))
    assert err["code"] == "not_a_directory"


@pytest.mark.asyncio
async def test_fs_list_symlink_dir_escape_blocked(tmp_path: Path) -> None:
    """QA-Fix #2: Symlink auf externes Verzeichnis darf nicht rekursiert werden.

    Repro: ws/leak_etc -> /tmp/external_dir (ausserhalb Workspace)
    fs_list(recursive=True) darf keine Dateien aus external_dir liefern.
    """
    # Workspace: tmp_path/ws
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    (ws_dir / "safe.txt").write_text("safe\n")

    # Externes Verzeichnis ausserhalb des Workspace
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret_external.txt").write_text("EXTERNAL_SECRET\n")

    # Symlink innerhalb des Workspace auf externes Verzeichnis
    symlink = ws_dir / "leak_dir"
    try:
        symlink.symlink_to(external)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks nicht unterstuetzt auf diesem Filesystem")

    with patch("app.mcp.tools.fs_tools._workspace_root", return_value=ws_dir.resolve()):
        data = _ok(await _handle_fs_list({"path": ".", "recursive": True}))

    paths = {e["path"] for e in data["entries"]}
    # Dateien aus external_dir duerfen NICHT erscheinen
    assert not any("secret_external.txt" in p for p in paths), (
        "fs_list darf keine Dateien ausserhalb WORKSPACE_ROOT per Symlink listen!"
    )
    # safe.txt muss erscheinen
    assert any("safe.txt" in p for p in paths)


@pytest.mark.asyncio
async def test_fs_list_symlink_file_escape_blocked(tmp_path: Path) -> None:
    """QA-Fix #2: Symlink auf externe Datei wird nicht gelistet."""
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    (ws_dir / "safe.txt").write_text("safe\n")

    external_file = tmp_path / "external_secrets.txt"
    external_file.write_text("TOP_SECRET\n")

    symlink = ws_dir / "link_to_secrets.txt"
    try:
        symlink.symlink_to(external_file)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks nicht unterstuetzt auf diesem Filesystem")

    with patch("app.mcp.tools.fs_tools._workspace_root", return_value=ws_dir.resolve()):
        data = _ok(await _handle_fs_list({"path": "."}))

    names = {e["name"] for e in data["entries"]}
    assert "link_to_secrets.txt" not in names, (
        "fs_list darf keine Datei-Symlinks ausserhalb WORKSPACE_ROOT liefern!"
    )


# ── Tests: fs_search ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_search_basic_hit(ws: Path) -> None:
    with _patch_ws(ws), _patch_deny([]):
        data = _ok(await _handle_fs_search({"pattern": "Zeile", "path": "."}))
    assert data["total"] >= 2
    paths = {r["path"] for r in data["results"]}
    assert any("hello.txt" in p for p in paths)


@pytest.mark.asyncio
async def test_fs_search_skips_binary_files(ws: Path) -> None:
    """Bug-Fix #2: Binary-Dateien mit NUL-Bytes müssen übersprungen werden."""
    with _patch_ws(ws), _patch_deny([]):
        data = _ok(await _handle_fs_search({"pattern": "SECRET", "path": "."}))
    # tmp_bin_test.bin enthält "SECRET" aber soll nicht matchen
    paths = {r["path"] for r in data["results"]}
    assert not any("tmp_bin_test.bin" in p for p in paths), (
        "Binary-Datei tmp_bin_test.bin darf nicht in fs_search-Treffern erscheinen!"
    )


@pytest.mark.asyncio
async def test_fs_search_deny_list_skipped(ws: Path) -> None:
    with _patch_ws(ws), _patch_deny([".env", ".env.local"]):
        data = _ok(await _handle_fs_search({"pattern": "supersecret", "path": "."}))
    paths = {r["path"] for r in data["results"]}
    assert not any(".env" in p for p in paths)


@pytest.mark.asyncio
async def test_fs_search_regex(ws: Path) -> None:
    with _patch_ws(ws), _patch_deny([]):
        data = _ok(await _handle_fs_search({
            "pattern": r"Zeile\s+\d+",
            "path": ".",
            "regex": True,
        }))
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_fs_search_no_match(ws: Path) -> None:
    with _patch_ws(ws), _patch_deny([]):
        data = _ok(await _handle_fs_search({"pattern": "XYZZY_NOT_FOUND", "path": "."}))
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_fs_search_symlink_file_escape_blocked(tmp_path: Path) -> None:
    """QA-Fix #2: fs_search darf keine Dateien lesen, die per Symlink ausserhalb liegen.

    Repro: ws/link_to_hosts -> /tmp/external/hosts
    fs_search(pattern='EXTERNAL') darf keine Treffer in der externen Datei liefern.
    """
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    (ws_dir / "inside.txt").write_text("INSIDE_CONTENT\n")

    external_file = tmp_path / "external_hosts.txt"
    external_file.write_text("EXTERNAL_CONTENT\n")

    symlink = ws_dir / "link_to_external.txt"
    try:
        symlink.symlink_to(external_file)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks nicht unterstuetzt auf diesem Filesystem")

    with patch("app.mcp.tools.fs_tools._workspace_root", return_value=ws_dir.resolve()), \
         patch("app.mcp.tools.fs_tools._deny_patterns", return_value=[]):
        data = _ok(await _handle_fs_search({"pattern": "EXTERNAL_CONTENT", "path": "."}))

    paths = {r["path"] for r in data["results"]}
    assert not any("link_to_external" in p for p in paths), (
        "fs_search darf externe Dateien per Symlink nicht lesen!"
    )


@pytest.mark.asyncio
async def test_fs_search_symlink_dir_escape_blocked(tmp_path: Path) -> None:
    """QA-Fix #2: fs_search darf nicht durch symlinked dirs ausserhalb lesen."""
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    (ws_dir / "inside.txt").write_text("INSIDE\n")

    external = tmp_path / "external"
    external.mkdir()
    (external / "ext_file.txt").write_text("DIR_ESCAPE_CONTENT\n")

    symlink = ws_dir / "leak_dir"
    try:
        symlink.symlink_to(external)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks nicht unterstuetzt auf diesem Filesystem")

    with patch("app.mcp.tools.fs_tools._workspace_root", return_value=ws_dir.resolve()), \
         patch("app.mcp.tools.fs_tools._deny_patterns", return_value=[]):
        data = _ok(await _handle_fs_search({"pattern": "DIR_ESCAPE_CONTENT", "path": "."}))

    assert data["total"] == 0, (
        "fs_search darf Inhalt aus per Symlink erreichbaren externen Verzeichnissen nicht liefern!"
    )


# ── Tests: fs_stat ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fs_stat_file(ws: Path) -> None:
    with _patch_ws(ws):
        data = _ok(await _handle_fs_stat({"path": "hello.txt"}))
    assert data["type"] == "file"
    assert data["size"] > 0
    assert "mtime_iso" in data


@pytest.mark.asyncio
async def test_fs_stat_directory(ws: Path) -> None:
    with _patch_ws(ws):
        data = _ok(await _handle_fs_stat({"path": "subdir"}))
    assert data["type"] == "dir"


@pytest.mark.asyncio
async def test_fs_stat_denied(ws: Path) -> None:
    with _patch_ws(ws), _patch_deny([".env"]):
        err = _err(await _handle_fs_stat({"path": ".env"}))
    assert err["code"] == "access_denied"


@pytest.mark.asyncio
async def test_fs_stat_not_found(ws: Path) -> None:
    with _patch_ws(ws):
        err = _err(await _handle_fs_stat({"path": "ghost.txt"}))
    assert err["code"] == "not_found"
