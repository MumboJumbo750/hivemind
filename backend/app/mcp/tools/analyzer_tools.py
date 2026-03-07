"""MCP Analyzer Tool — TASK-WFS-003.

Tool:
  hivemind-run_analyzer — Führt Health-Analyzer im Container aus und liefert JSON-Report.

Features:
  - analyzer_name : einzelner Name, kommagetrennte Liste, oder "all" (default)
  - root_path     : Pfad zum Repo-Root (default: /workspace)
  - min_severity  : "error" | "warning" | "info" — filtert Findings nach Mindest-Schwere
  - deep_scan     : bool (default: True) — an unterstützende Analyzer weitergegeben
  - Timeout       : max 60 s pro Analyzer (danach: Warning-Finding, Run geht weiter)
  - Fehler-Isolation: ein kaputter Analyzer stoppt nicht den gesamten Run
  - Caching       : In-Memory-Cache; Skip wenn Report-Hash unverändert
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import multiprocessing
import multiprocessing.queues
import sys
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

from app.config import settings
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)

# ── Konstanten ────────────────────────────────────────────────────────────

_ANALYZER_TIMEOUT: float = 60.0   # Sekunden pro Analyzer
_OUTER_TIMEOUT: float = 600.0     # 10-min-Guard fürs Gesamt-Async-Wait

# ── Multiprocessing-Kontext ───────────────────────────────────────────────
# 'fork' auf Linux (Container): Kind-Prozess erbt Speicher, kein Pickle nötig
# für Analyzer-Instanzen. Prozesse können via terminate()/kill() hart beendet
# werden — kein Zombie-Thread wie bei threading.Thread.
try:
    _MP_CTX = multiprocessing.get_context("fork")
except ValueError:  # pragma: no cover — Windows-Fallback (kein Fork)
    _MP_CTX = None  # type: ignore[assignment]
    logger.warning("analyzer_tools: fork-Kontext nicht verfügbar, Timeout-Isolation eingeschränkt")

# Workspace-Root im Container; Fallback auf Repo-Root beim Entwickeln auf dem Host
def _workspace_sys_path() -> str | None:
    """Gibt den Pfad zurück, der scripts.analyzers erreichbar macht, oder None.

    Sucht von HIVEMIND_WORKSPACE_ROOT (default /workspace) und aufsteigend
    entlang __file__ nach scripts/analyzers/__init__.py.
    """
    candidates: list[Path] = [
        Path(settings.hivemind_workspace_root),
        Path("/workspace"),  # Hivemind-interner Container-Pfad (Fallback bei externem WORKSPACE_ROOT)
    ]

    # Aufsteigend alle übergeordneten Verzeichnisse von __file__ — ohne feste Index-Annahme
    here = Path(__file__).resolve()
    candidates.extend(here.parents)

    # Duplikate entfernen (Reihenfolge beibehalten)
    seen: set[Path] = set()
    unique: list[Path] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    candidates = unique

    for candidate in candidates:
        try:
            if (candidate / "scripts" / "analyzers" / "__init__.py").exists():
                return str(candidate)
        except (OSError, PermissionError):
            continue
    return None


# sys.path beim Modulimport einmal erweitern
_ws_path = _workspace_sys_path()
if _ws_path and _ws_path not in sys.path:
    sys.path.insert(0, _ws_path)
    logger.info("analyzer_tools: Added %s to sys.path", _ws_path)


def _ensure_workspace_scripts_importable() -> None:
    """Stellt sicher, dass scripts.analyzers aus /workspace importierbar ist.

    Bereinigt veraltete scripts.*-Einträge in sys.modules, die auf /app/scripts
    (Backend-Skripte) zeigen, damit der folgende Import aus /workspace/scripts
    aufgelöst wird und nicht durch die Backend-Scripts-Package kollisioniert.
    """
    ws = _workspace_sys_path()
    if ws is None:
        raise RuntimeError(
            "scripts.analyzers konnte nicht gefunden werden "
            f"(kein Mount unter {settings.hivemind_workspace_root}?). "
            f"sys.path: {sys.path}"
        )

    # Veraltete scripts.* entfernen, die NICHT zum Workspace gehören
    for key in list(sys.modules):
        if key == "scripts" or key.startswith("scripts."):
            mod = sys.modules[key]
            mod_file = getattr(mod, "__file__", None) or ""
            if mod_file and ws not in str(Path(mod_file).resolve()):
                logger.debug("analyzer_tools: Purging stale sys.modules[%s] → %s", key, mod_file)
                del sys.modules[key]

    if ws not in sys.path:
        sys.path.insert(0, ws)
        logger.info("analyzer_tools: (re-)added %s to sys.path[0]", ws)
    elif sys.path[0] != ws:
        # /workspace ist vorhanden, aber nicht an Position 0 → /app/scripts würde
        # sonst scripts.analyzers verdrängen
        sys.path.remove(ws)
        sys.path.insert(0, ws)
        logger.debug("analyzer_tools: moved %s to sys.path[0]", ws)


# ── Subprocess-Worker (top-level, pickleable) ─────────────────────────────

def _analyzer_worker(result_queue: "multiprocessing.queues.Queue", analyzer_instance: object, root_path: str) -> None:  # noqa: ANN001
    """Läuft im separaten fork-Prozess. Gibt das Ergebnis via Queue zurück.

    Muss auf Modul-Ebene definiert sein (pickleable für multiprocessing).
    Mit fork-Kontext ererbt der Kind-Prozess alle Objekte des Eltern-Prozesses
    ohne Serialisierung — lokale Test-Klassen funktionieren daher problemlos.
    """
    try:
        findings = list(analyzer_instance.analyze(Path(root_path)))  # type: ignore[attr-defined]
        result_queue.put(("ok", findings))
    except Exception as exc:  # noqa: BLE001
        result_queue.put(("err", str(exc)))

# ── In-Memory-Cache ───────────────────────────────────────────────────────

_cache: dict[str, dict[str, Any]] = {}  # key → {"hash": str, "report_dict": dict}


def _cache_key(
    analyzer_names: list[str] | None,
    root_path: str,
    min_severity: str | None,
    deep_scan: bool,
) -> str:
    parts = [
        ",".join(sorted(analyzer_names)) if analyzer_names else "__all__",
        root_path,
        min_severity or "",
        "1" if deep_scan else "0",
    ]
    return "|".join(parts)


def _report_hash(report_dict: dict) -> str:
    payload = json.dumps(report_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Kern-Analyse (synchron, läuft im Thread-Executor) ────────────────────


def _run_analyzers_sync(
    root_path: str,
    analyzer_names: list[str] | None,
    min_severity: str | None,
    deep_scan: bool,
) -> dict:
    """Führt Analyzer synchron aus (wird via asyncio.run_in_executor aufgerufen)."""
    _ensure_workspace_scripts_importable()
    try:
        from scripts.analyzers import (  # type: ignore[import]
            AnalyzerRegistry,
            Finding,
            Report,
            SEVERITY_ORDER,
            detect_stack,
        )
    except ImportError as exc:
        raise RuntimeError(
            f"scripts.analyzers konnte nicht importiert werden: {exc}. "
            f"sys.path enthält: {sys.path}"
        ) from exc

    root = Path(root_path).resolve()
    if not root.is_dir():
        raise ValueError(f"root_path '{root_path}' ist kein Verzeichnis.")

    stack = detect_stack(root)
    registered = AnalyzerRegistry.discover()

    if analyzer_names:
        registered = [a for a in registered if a.name in analyzer_names]

    all_findings: list[Finding] = []
    analyzer_stats: dict[str, dict] = {}

    for analyzer_cls in registered:
        aname = analyzer_cls.name

        # Instanz erstellen — deep_scan wenn Konstruktor es unterstützt
        try:
            sig = inspect.signature(analyzer_cls.__init__)
            if "deep_scan" in sig.parameters:
                instance = analyzer_cls(deep_scan=deep_scan)
            else:
                instance = analyzer_cls()
        except Exception as exc:
            all_findings.append(
                Finding(
                    analyzer="framework",
                    severity="warning",
                    file="<init>",
                    line=None,
                    message=f"Analyzer '{aname}' konnte nicht instanziiert werden: {exc}",
                    category="analyzer-error",
                )
            )
            analyzer_stats[aname] = {"status": "init_error", "error": str(exc)}
            continue

        # Per-Analyzer-Isolation via fork-Prozess.
        # Im Unterschied zu daemon-Threads kann ein hängender Prozess via
        # terminate() / kill() hart beendet werden — keine Zombie-Threads,
        # kein blockierendes pytest-Teardown.
        if _MP_CTX is not None:
            result_q: multiprocessing.queues.Queue = _MP_CTX.Queue(maxsize=1)
            p = _MP_CTX.Process(
                target=_analyzer_worker,
                args=(result_q, instance, str(root)),
                daemon=True,
                name=f"analyzer-{aname}",
            )
            p.start()
            p.join(timeout=_ANALYZER_TIMEOUT)
            timed_out = p.is_alive()
            if timed_out:
                # Hart terminieren — SIGTERM, dann SIGKILL
                p.terminate()
                p.join(timeout=2.0)
                if p.is_alive():
                    p.kill()
                    p.join(timeout=1.0)
        else:
            # Fallback: daemon-Thread (kein hard-kill, aber besser als nix)
            import queue as _queue
            import threading
            result_q_t: _queue.Queue = _queue.Queue(maxsize=1)

            def _run_t(fn=instance.analyze, r=root, q=result_q_t) -> None:  # type: ignore[misc]
                try:
                    q.put(("ok", fn(r)))
                except Exception as _exc:  # noqa: BLE001
                    q.put(("err", _exc))

            t = threading.Thread(target=_run_t, daemon=True, name=f"analyzer-{aname}")
            t.start()
            t.join(timeout=_ANALYZER_TIMEOUT)
            timed_out = t.is_alive()
            result_q = result_q_t  # type: ignore[assignment]

        if timed_out:
            all_findings.append(
                Finding(
                    analyzer="framework",
                    severity="warning",
                    file="<timeout>",
                    line=None,
                    message=(
                        f"Analyzer '{aname}' hat das Timeout"
                        f" von {_ANALYZER_TIMEOUT:.0f}s überschritten."
                    ),
                    category="analyzer-timeout",
                )
            )
            analyzer_stats[aname] = {"status": "timeout"}
            logger.warning("Analyzer '%s' timed out after %ss", aname, _ANALYZER_TIMEOUT)
        else:
            try:
                kind, value = result_q.get_nowait()
            except Exception:
                kind, value = "err", "Kein Ergebnis (Prozess/Thread ohne Result beendet)"
            if kind == "ok":
                all_findings.extend(value)
                analyzer_stats[aname] = {"status": "ok", "findings_count": len(value)}
                logger.debug("Analyzer '%s': %d finding(s)", aname, len(value))
            else:
                exc = value
                all_findings.append(
                    Finding(
                        analyzer="framework",
                        severity="warning",
                        file="<error>",
                        line=None,
                        message=f"Analyzer '{aname}' hat eine Ausnahme ausgelöst: {exc}",
                        category="analyzer-error",
                    )
                )
                analyzer_stats[aname] = {"status": "error", "error": str(exc)}
                logger.warning("Analyzer '%s' raised: %s", aname, exc)

    # Schwere-Filter
    if min_severity and min_severity in SEVERITY_ORDER:
        threshold = SEVERITY_ORDER[min_severity]
        all_findings = [f for f in all_findings if SEVERITY_ORDER.get(f.severity, 99) <= threshold]

    report = Report(findings=all_findings, root_path=str(root), stack=stack)
    report._recompute_summary()

    report_dict = json.loads(report.to_json())
    report_dict["analyzer_stats"] = analyzer_stats
    return report_dict


# ── MCP-Handler ────────────────────────────────────────────────────────────


async def _handle_run_analyzer(args: dict) -> list[TextContent]:
    # Parameter auslesen
    analyzer_name: str | None = args.get("analyzer_name") or None
    root_path: str = args.get("root_path") or settings.hivemind_workspace_root
    min_severity: str | None = args.get("min_severity") or None
    deep_scan: bool = bool(args.get("deep_scan", True))

    # analyzer_name → analyzer_names (Liste)
    analyzer_names: list[str] | None = None
    if analyzer_name and analyzer_name.strip().lower() not in ("", "all"):
        analyzer_names = [a.strip() for a in analyzer_name.split(",") if a.strip()]

    # Validierung min_severity
    valid_severities = ("error", "warning", "info")
    if min_severity and min_severity not in valid_severities:
        return _err(
            "invalid_argument",
            f"min_severity muss einer von {valid_severities} sein, nicht '{min_severity}'.",
        )

    # ── Cache-Check VOR dem Analyzer-Run ──────────────────────────────────
    # Echter Skip: wenn Cache-Eintrag vorhanden, wird _run_analyzers_sync NICHT aufgerufen.
    key = _cache_key(analyzer_names, root_path, min_severity, deep_scan)
    if key in _cache:
        cached_entry = _cache[key]
        return _ok(
            {
                "cached": True,
                "report_hash": cached_entry["hash"],
                "report": cached_entry["report_dict"],
            }
        )

    # ── Analyzer ausführen (kein Cache-Hit) ────────────────────────────────
    try:
        loop = asyncio.get_event_loop()
        report_dict = await asyncio.wait_for(
            loop.run_in_executor(
                None,  # Default-ThreadPool — kein globaler Executor nötig
                _run_analyzers_sync,
                root_path,
                analyzer_names,
                min_severity,
                deep_scan,
            ),
            timeout=_OUTER_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return _err("timeout", f"Analyzer-Run hat das Gesamt-Timeout von {_OUTER_TIMEOUT:.0f}s überschritten.")
    except Exception as exc:
        logger.exception("run_analyzer fehlgeschlagen")
        return _err("internal_error", str(exc))

    # ── Ergebnis cachen ────────────────────────────────────────────────────
    new_hash = _report_hash(report_dict)
    _cache[key] = {"hash": new_hash, "report_dict": report_dict}

    return _ok(
        {
            "cached": False,
            "report_hash": new_hash,
            "report": report_dict,
        }
    )


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data}, default=str))]


def _err(code: str, message: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": {"code": code, "message": message}}))]


# ── Tool-Registrierung ─────────────────────────────────────────────────────

register_tool(
    Tool(
        name="hivemind-run_analyzer",
        description=(
            "Führt den Hivemind Health-Scanner im Container aus und liefert einen JSON-Report.\n"
            "Jeder Analyzer hat ein eigenes Timeout von 60 s. "
            "Ein fehlerhafter Analyzer stoppt nicht den Rest. "
            "Ergebnisse werden in-memory gecached (Skip wenn Report-Hash unverändert)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "analyzer_name": {
                    "type": "string",
                    "description": (
                        "Name des Analyzers (oder 'all' für alle). "
                        "Kann eine kommagetrennte Liste sein, z.B. 'hardcoded-css,magic-numbers'. "
                        "Default: alle Analyzer."
                    ),
                },
                "root_path": {
                    "type": "string",
                    "description": (
                        "Pfad zum Repo-Root. "
                        "Default: HIVEMIND_WORKSPACE_ROOT (default /workspace)."
                    ),
                },
                "min_severity": {
                    "type": "string",
                    "enum": ["error", "warning", "info"],
                    "description": (
                        "Mindest-Schweregrad für Findings. "
                        "'error' zeigt nur Fehler, 'warning' Fehler+Warnungen, 'info' alles."
                    ),
                },
                "deep_scan": {
                    "type": "boolean",
                    "description": (
                        "Deep-Scan aktivieren (Phase 2 bei unterstützenden Analyzern, "
                        "z.B. Duplikatserkennung via difflib). Default: true."
                    ),
                    "default": True,
                },
            },
            "required": [],
        },
    ),
    handler=_handle_run_analyzer,
)
