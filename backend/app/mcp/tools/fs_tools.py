"""MCP Filesystem-Tools — TASK-WFS-002.

Tools:
  hivemind-fs_read    — Datei lesen (Line-Range optional)
  hivemind-fs_write   — Datei schreiben/erstellen (atomisch, temp+rename)
  hivemind-fs_list    — Verzeichnis auflisten (rekursiv/flach, ignore-Patterns)
  hivemind-fs_search  — Grep/Glob-Suche über Workspace
  hivemind-fs_stat    — Metadaten (Größe, Typ, mtime)

Sicherheit:
  - Path-Sandboxing: alle Pfade auf HIVEMIND_WORKSPACE_ROOT eingesperrt
  - Path-Traversal-Schutz (.. und Symlinks werden resolved/geprüft)
  - Konfigurierbare Deny-List (HIVEMIND_FS_DENY_LIST)
  - In-Memory Rate-Limiting pro Tool (HIVEMIND_FS_RATE_LIMIT calls/min)
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

from app.config import settings
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)

# ── Sandbox Configuration ─────────────────────────────────────────────────

def _workspace_root() -> Path:
    """Return the resolved workspace root. Falls back to CWD if not mounted."""
    root = Path(settings.hivemind_workspace_root).resolve()
    if not root.exists():
        # Graceful fallback for test environments without the /workspace mount
        root = Path.cwd().resolve()
        logger.warning("HIVEMIND_WORKSPACE_ROOT %s does not exist, falling back to %s",
                       settings.hivemind_workspace_root, root)
    return root


def _deny_patterns() -> list[str]:
    raw = settings.hivemind_fs_deny_list
    return [p.strip() for p in raw.split(",") if p.strip()]


def _is_denied(rel_path: str) -> bool:
    """Return True when rel_path matches any deny pattern."""
    patterns = _deny_patterns()
    normalized = rel_path.replace("\\", "/")
    for pat in patterns:
        # Exact prefix match or fnmatch glob
        if normalized == pat or normalized.startswith(pat + "/"):
            return True
        if fnmatch.fnmatch(normalized, pat):
            return True
    return False


def _sandbox(path_str: str) -> Path:
    """Resolve *path_str* and raise ValueError if outside workspace root.

    Accepts both absolute paths (must be within root) and relative paths
    (resolved relative to root).
    """
    root = _workspace_root()
    candidate = Path(path_str)

    if not candidate.is_absolute():
        candidate = root / candidate

    # Resolve to real path (follows symlinks)
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise ValueError(f"Path resolution failed: {exc}") from exc

    # Ensure it stays within the workspace root
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Path '{path_str}' escapes workspace root '{root}'. Access denied."
        )

    # Check deny-list using relative path from root
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        rel = resolved
    if _is_denied(str(rel)):
        raise ValueError(f"Path '{rel}' is on the deny-list. Access denied.")

    return resolved


# ── Rate Limiter ───────────────────────────────────────────────────────────

_rate_counters: dict[str, list[float]] = defaultdict(list)  # tool_name → call timestamps


def _check_rate_limit(tool_name: str) -> None:
    """Raise ValueError when per-minute call limit exceeded."""
    limit = settings.hivemind_fs_rate_limit
    now = time.monotonic()
    window = 60.0
    calls = _rate_counters[tool_name]
    # Purge old entries
    _rate_counters[tool_name] = [t for t in calls if now - t < window]
    if len(_rate_counters[tool_name]) >= limit:
        raise ValueError(
            f"Rate limit exceeded for {tool_name}: max {limit} calls/min."
        )
    _rate_counters[tool_name].append(now)


# ── Response Helpers ───────────────────────────────────────────────────────

def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data}, default=str))]


def _err(code: str, message: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": {"code": code, "message": message}}))]


# ── Tool: fs_read ──────────────────────────────────────────────────────────

async def _handle_fs_read(args: dict) -> list[TextContent]:
    _check_rate_limit("hivemind-fs_read")
    path_str = args.get("path", "")
    start_line: int | None = args.get("start_line")
    end_line: int | None = args.get("end_line")
    encoding = args.get("encoding", "utf-8")

    try:
        resolved = _sandbox(path_str)
    except ValueError as exc:
        return _err("access_denied", str(exc))

    if not resolved.exists():
        return _err("not_found", f"Path '{path_str}' does not exist.")
    if not resolved.is_file():
        return _err("not_a_file", f"Path '{path_str}' is not a file.")

    try:
        text = resolved.read_text(encoding=encoding, errors="replace")
    except OSError as exc:
        return _err("read_error", str(exc))

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)

    if start_line is not None or end_line is not None:
        s = max(0, (start_line or 1) - 1)
        e = end_line if end_line is not None else total_lines
        selected = lines[s:e]
        content = "".join(selected)
    else:
        content = text

    return _ok({
        "path": str(resolved.relative_to(_workspace_root())),
        "content": content,
        "total_lines": total_lines,
        "encoding": encoding,
    })


register_tool(
    Tool(
        name="hivemind-fs_read",
        description=(
            "Lese eine Datei aus dem Workspace. "
            "Optionale line_range über start_line/end_line (1-basiert). "
            "Pfad relativ zum Workspace-Root oder absolut (muss innerhalb bleiben)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Pfad zur Datei (relativ oder absolut)"},
                "start_line": {"type": "integer", "description": "Erste Zeile (1-basiert, inklusiv)"},
                "end_line": {"type": "integer", "description": "Letzte Zeile (1-basiert, inklusiv)"},
                "encoding": {"type": "string", "description": "Encoding (default: utf-8)"},
            },
            "required": ["path"],
        },
    ),
    handler=_handle_fs_read,
)


# ── Tool: fs_write ─────────────────────────────────────────────────────────

async def _handle_fs_write(args: dict) -> list[TextContent]:
    _check_rate_limit("hivemind-fs_write")
    path_str = args.get("path", "")
    content = args.get("content", "")
    encoding = args.get("encoding", "utf-8")
    create_dirs = args.get("create_dirs", True)

    try:
        resolved = _sandbox(path_str)
    except ValueError as exc:
        return _err("access_denied", str(exc))

    try:
        if create_dirs:
            resolved.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write via temp file + rename
        dir_ = resolved.parent
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=dir_,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        os.replace(tmp_path, resolved)
    except OSError as exc:
        return _err("write_error", str(exc))

    return _ok({
        "path": str(resolved.relative_to(_workspace_root())),
        "bytes_written": len(content.encode(encoding)),
        "created": True,
    })


register_tool(
    Tool(
        name="hivemind-fs_write",
        description=(
            "Schreibe oder erstelle eine Datei im Workspace (atomisch via temp+rename). "
            "Erstellt Verzeichnisse automatisch. Überschreibt vorhandene Dateien."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Pfad zur Datei (relativ oder absolut)"},
                "content": {"type": "string", "description": "Dateiinhalt"},
                "encoding": {"type": "string", "description": "Encoding (default: utf-8)"},
                "create_dirs": {
                    "type": "boolean",
                    "description": "Verzeichnisse automatisch erstellen (default: true)",
                    "default": True,
                },
            },
            "required": ["path", "content"],
        },
    ),
    handler=_handle_fs_write,
)


# ── Tool: fs_list ──────────────────────────────────────────────────────────

_DEFAULT_IGNORE = {
    "__pycache__", ".git", "node_modules", ".venv", "*.pyc", "*.pyo",
    ".mypy_cache", ".ruff_cache", "dist", "build", "*.egg-info",
}


async def _handle_fs_list(args: dict) -> list[TextContent]:
    _check_rate_limit("hivemind-fs_list")
    path_str = args.get("path", ".")
    recursive = args.get("recursive", False)
    ignore_raw: list[str] = args.get("ignore", [])
    max_entries = min(int(args.get("max_entries", 500)), 2000)

    try:
        resolved = _sandbox(path_str)
    except ValueError as exc:
        return _err("access_denied", str(exc))

    if not resolved.exists():
        return _err("not_found", f"Path '{path_str}' does not exist.")
    if not resolved.is_dir():
        return _err("not_a_directory", f"Path '{path_str}' is not a directory.")

    ignore_patterns = _DEFAULT_IGNORE | set(ignore_raw)
    root = _workspace_root()

    def _should_ignore(p: Path) -> bool:
        name = p.name
        for pat in ignore_patterns:
            if fnmatch.fnmatch(name, pat) or name == pat:
                return True
        return False

    entries: list[dict] = []

    def _collect(directory: Path, depth: int = 0) -> None:
        if len(entries) >= max_entries:
            return
        try:
            items = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return
        for item in items:
            if len(entries) >= max_entries:
                break
            if _should_ignore(item):
                continue
            # Symlink-Traversal-Schutz: real path muss innerhalb root bleiben
            try:
                item_real = item.resolve()
                item_real.relative_to(root)
            except (ValueError, OSError):
                logger.debug("fs_list: Symlink escapes workspace, skipping: %s", item)
                continue
            try:
                rel = str(item.relative_to(root))
            except ValueError:
                rel = str(item)
            rel_normalized = rel.replace("\\", "/")
            # Deny-List-Check auch in fs_list (konsistent mit fs_read/fs_stat)
            if _is_denied(rel_normalized):
                continue
            entry: dict = {
                "path": rel_normalized,
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
            }
            if item.is_file():
                try:
                    entry["size"] = item.stat().st_size
                except OSError:
                    entry["size"] = None
            entries.append(entry)
            if recursive and item.is_dir():
                _collect(item, depth + 1)

    _collect(resolved)

    return _ok({
        "path": str(resolved.relative_to(root)).replace("\\", "/"),
        "entries": entries,
        "truncated": len(entries) >= max_entries,
    })


register_tool(
    Tool(
        name="hivemind-fs_list",
        description=(
            "Liste den Inhalt eines Verzeichnisses im Workspace. "
            "Unterstützt rekursive Auflistung und ignore-Patterns. "
            "Standard-Ignore: __pycache__, .git, node_modules, .venv, etc."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Verzeichnispfad (default: Workspace-Root)",
                    "default": ".",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Rekursiv alle Unterverzeichnisse auflisten (default: false)",
                    "default": False,
                },
                "ignore": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Zusätzliche ignore-Patterns (fnmatch-Syntax)",
                },
                "max_entries": {
                    "type": "integer",
                    "description": "Maximale Anzahl Einträge (default: 500, max: 2000)",
                    "default": 500,
                },
            },
            "required": [],
        },
    ),
    handler=_handle_fs_list,
)


# ── Tool: fs_search ────────────────────────────────────────────────────────

async def _handle_fs_search(args: dict) -> list[TextContent]:
    _check_rate_limit("hivemind-fs_search")
    pattern = args.get("pattern", "")
    search_path = args.get("path", ".")
    glob = args.get("glob", "**/*")
    is_regex = args.get("regex", False)
    case_sensitive = args.get("case_sensitive", False)
    max_results = min(int(args.get("max_results", 100)), 500)
    context_lines = min(int(args.get("context_lines", 0)), 5)

    try:
        resolved = _sandbox(search_path)
    except ValueError as exc:
        return _err("access_denied", str(exc))

    root = _workspace_root()
    results: list[dict] = []

    # Compile pattern
    try:
        if is_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled = re.compile(pattern, flags)
        else:
            escaped = re.escape(pattern)
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled = re.compile(escaped, flags)
    except re.error as exc:
        return _err("invalid_pattern", f"Regex-Fehler: {exc}")

    # Find files matching glob; skip on binary files
    try:
        candidates = list(resolved.glob(glob))
    except Exception as exc:
        return _err("glob_error", str(exc))

    for file_path in sorted(candidates):
        if not file_path.is_file():
            continue
        # Symlink-Traversal-Schutz: real path muss innerhalb root bleiben
        try:
            file_path.resolve().relative_to(root)
        except (ValueError, OSError):
            logger.debug("fs_search: Symlink escapes workspace, skipping: %s", file_path)
            continue
        try:
            rel = str(file_path.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        if _is_denied(rel):
            continue

        # Binary-Dateien überspringen (NUL-Byte-Heuristik auf ersten 8 KB)
        try:
            raw = file_path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8192]:
            continue
        text = raw.decode("utf-8", errors="replace")

        lines = text.splitlines()
        for i, line in enumerate(lines):
            if compiled.search(line):
                match: dict = {
                    "path": rel,
                    "line": i + 1,
                    "content": line,
                }
                if context_lines:
                    before = lines[max(0, i - context_lines):i]
                    after = lines[i + 1:i + 1 + context_lines]
                    match["context"] = {"before": before, "after": after}
                results.append(match)
                if len(results) >= max_results:
                    return _ok({"results": results, "truncated": True, "total": len(results)})

    return _ok({"results": results, "truncated": False, "total": len(results)})


register_tool(
    Tool(
        name="hivemind-fs_search",
        description=(
            "Durchsuche Dateien im Workspace nach einem Text- oder Regex-Muster. "
            "Unterstützt Glob-Patterns für Dateiauswahl, optionale Kontextzeilen. "
            "Überspringt Binary-Dateien und Deny-List-Einträge automatisch."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Suchbegriff oder Regex-Pattern"},
                "path": {
                    "type": "string",
                    "description": "Verzeichnis für die Suche (default: Workspace-Root)",
                    "default": ".",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob-Pattern für Dateiauswahl (default: **/*)",
                    "default": "**/*",
                },
                "regex": {
                    "type": "boolean",
                    "description": "Pattern als regulären Ausdruck interpretieren (default: false)",
                    "default": False,
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Groß-/Kleinschreibung beachten (default: false)",
                    "default": False,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximale Treffer (default: 100, max: 500)",
                    "default": 100,
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Anzahl Kontextzeilen vor/nach Treffer (default: 0, max: 5)",
                    "default": 0,
                },
            },
            "required": ["pattern"],
        },
    ),
    handler=_handle_fs_search,
)


# ── Tool: fs_stat ──────────────────────────────────────────────────────────

async def _handle_fs_stat(args: dict) -> list[TextContent]:
    _check_rate_limit("hivemind-fs_stat")
    path_str = args.get("path", "")

    try:
        resolved = _sandbox(path_str)
    except ValueError as exc:
        return _err("access_denied", str(exc))

    if not resolved.exists():
        return _err("not_found", f"Path '{path_str}' does not exist.")

    try:
        st = resolved.stat()
    except OSError as exc:
        return _err("stat_error", str(exc))

    root = _workspace_root()
    try:
        rel = str(resolved.relative_to(root)).replace("\\", "/")
    except ValueError:
        rel = str(resolved)

    entry_type = "dir" if resolved.is_dir() else "file" if resolved.is_file() else "other"

    return _ok({
        "path": rel,
        "type": entry_type,
        "size": st.st_size,
        "mtime": st.st_mtime,
        "mtime_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
        "mode": oct(st.st_mode),
        "is_symlink": resolved.is_symlink(),
    })


register_tool(
    Tool(
        name="hivemind-fs_stat",
        description=(
            "Metadaten einer Datei oder eines Verzeichnisses im Workspace abfragen. "
            "Gibt Typ, Größe, Änderungszeitpunkt, Permissions und Symlink-Status zurück."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Pfad (relativ oder absolut)"},
            },
            "required": ["path"],
        },
    ),
    handler=_handle_fs_stat,
)
