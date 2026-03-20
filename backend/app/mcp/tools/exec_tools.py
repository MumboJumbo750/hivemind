"""MCP Execution Tools — Guard Execution & Shell Commands.

Tools:
  hivemind-execute_guard  — Führt einen Guard-Command aus (pytest, ruff, eslint, etc.)
  hivemind-run_command    — Führt einen allowlisted Shell-Command aus

Sicherheit:
  - Allowlist: nur Befehle die HIVEMIND_GUARD_ALLOWLIST matchen werden ausgeführt
  - Timeout: max HIVEMIND_GUARD_TIMEOUT Sekunden (Default: 120)
  - Parallelität: max HIVEMIND_GUARD_PARALLEL gleichzeitig (Default: 2)
  - Kein shell=True — Commands als Array, keine Shell-Injection
  - Output gecapped: stdout 4096, stderr 1024 Zeichen
  - Execution via asyncio.to_thread — blockiert NICHT den Event Loop
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import shlex
import subprocess
from datetime import datetime, timezone
from typing import Any

from mcp.types import TextContent, Tool

from app.config import settings
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

_DEFAULT_ALLOWLIST = "pytest*,ruff *,eslint*,npm run *,make *,cargo test*,go test*,python -m pytest*,npx *,tsc*,mypy*,flake8*,black --check*,isort --check*"
_DEFAULT_TIMEOUT = 120
_DEFAULT_PARALLEL = 2
_STDOUT_CAP = 4096
_STDERR_CAP = 1024


def _get_allowlist() -> list[str]:
    raw = getattr(settings, "hivemind_guard_allowlist", "") or _DEFAULT_ALLOWLIST
    return [p.strip() for p in raw.split(",") if p.strip()]


def _get_timeout() -> int:
    return int(getattr(settings, "hivemind_guard_timeout", _DEFAULT_TIMEOUT))


def _get_parallel() -> int:
    return int(getattr(settings, "hivemind_guard_parallel", _DEFAULT_PARALLEL))


_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_get_parallel())
    return _semaphore


def _is_allowed(command_str: str) -> tuple[bool, str | None]:
    """Check command against allowlist. Returns (allowed, matching_pattern)."""
    for pattern in _get_allowlist():
        if fnmatch.fnmatch(command_str, pattern):
            return True, pattern
    return False, None


def _workspace_root() -> str:
    from pathlib import Path
    root = Path(settings.hivemind_workspace_root).resolve()
    if not root.exists():
        root = Path.cwd().resolve()
    return str(root)


# ── Execute Guard Tool ───────────────────────────────────────────────────────

async def _handle_execute_guard(args: dict[str, Any]) -> list[TextContent]:
    """Execute a guard command for a specific task guard."""
    import json
    import uuid

    task_key = args.get("task_key", "")
    guard_id = args.get("guard_id", "")
    command = args.get("command", "")
    cwd = args.get("cwd", "")

    if not task_key or not guard_id:
        return [TextContent(type="text", text=json.dumps({
            "error": "task_key and guard_id are required"
        }))]

    if not command:
        # Try to load command from guard definition
        from app.db import async_session_factory
        from sqlalchemy import select
        from app.models.guard import Guard
        async with async_session_factory() as session:
            result = await session.execute(
                select(Guard).where(Guard.id == uuid.UUID(guard_id))
            )
            guard = result.scalar_one_or_none()
            if guard and guard.command:
                command = guard.command
            else:
                return [TextContent(type="text", text=json.dumps({
                    "error": "No command provided and guard has no command configured"
                }))]

    # Parse command
    if isinstance(command, str):
        cmd_parts = shlex.split(command)
    else:
        cmd_parts = list(command)

    joined_command = " ".join(cmd_parts)

    # Allowlist check
    allowed, matched_pattern = _is_allowed(joined_command)
    if not allowed:
        logger.warning("Guard command BLOCKED: %s (no allowlist match)", joined_command)
        # Update guard status to failed
        exec_result = {
            "status": "failed",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"BLOCKED: Command '{joined_command}' is not on the guard execution allowlist",
            "command": joined_command,
            "blocked": True,
            "allowlist": _get_allowlist(),
        }
        await _update_task_guard(task_key, guard_id, "failed", exec_result["stderr"])
        return [TextContent(type="text", text=json.dumps(exec_result))]

    logger.info("Guard command ALLOWED: %s (pattern: %s)", joined_command, matched_pattern)

    # Execute
    work_dir = cwd or _workspace_root()
    timeout = _get_timeout()

    exec_result = await _run_command_safe(cmd_parts, work_dir, timeout)
    exec_result["command"] = joined_command
    exec_result["allowlist_pattern"] = matched_pattern

    # Update task guard status
    guard_status = "passed" if exec_result["exit_code"] == 0 else "failed"
    result_text = exec_result.get("stdout", "") or exec_result.get("stderr", "")
    await _update_task_guard(task_key, guard_id, guard_status, result_text[:4096])

    return [TextContent(type="text", text=json.dumps(exec_result))]


async def _update_task_guard(task_key: str, guard_id: str, status: str, result_text: str) -> None:
    """Update the task_guard record with execution result."""
    import uuid
    try:
        from app.db import async_session_factory
        from sqlalchemy import select, and_
        from app.models.guard import TaskGuard
        from app.models.task import Task

        async with async_session_factory() as session:
            # Find task
            task_result = await session.execute(
                select(Task).where(Task.task_key == task_key)
            )
            task = task_result.scalar_one_or_none()
            if not task:
                logger.warning("execute_guard: task %s not found", task_key)
                return

            # Find or create task_guard
            tg_result = await session.execute(
                select(TaskGuard).where(and_(
                    TaskGuard.task_id == task.id,
                    TaskGuard.guard_id == uuid.UUID(guard_id),
                ))
            )
            tg = tg_result.scalar_one_or_none()
            if not tg:
                tg = TaskGuard(
                    task_id=task.id,
                    guard_id=uuid.UUID(guard_id),
                )
                session.add(tg)

            tg.status = status
            tg.result = result_text
            tg.checked_at = datetime.now(timezone.utc)
            await session.commit()
    except Exception:
        logger.exception("Failed to update task_guard for %s / %s", task_key, guard_id)


# ── Run Command Tool ────────────────────────────────────────────────────────

async def _handle_run_command(args: dict[str, Any]) -> list[TextContent]:
    """Execute an allowlisted shell command in the workspace."""
    import json

    command = args.get("command", "")
    cwd = args.get("cwd", "")

    if not command:
        return [TextContent(type="text", text=json.dumps({
            "error": "command is required"
        }))]

    # Parse command
    if isinstance(command, str):
        cmd_parts = shlex.split(command)
    else:
        cmd_parts = list(command)

    joined_command = " ".join(cmd_parts)

    # Allowlist check
    allowed, matched_pattern = _is_allowed(joined_command)
    if not allowed:
        logger.warning("Command BLOCKED: %s (no allowlist match)", joined_command)
        return [TextContent(type="text", text=json.dumps({
            "status": "blocked",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"BLOCKED: Command '{joined_command}' is not on the execution allowlist. Allowed patterns: {', '.join(_get_allowlist())}",
            "command": joined_command,
        }))]

    logger.info("Command ALLOWED: %s (pattern: %s)", joined_command, matched_pattern)

    work_dir = cwd or _workspace_root()
    timeout = _get_timeout()

    result = await _run_command_safe(cmd_parts, work_dir, timeout)
    result["command"] = joined_command
    result["allowlist_pattern"] = matched_pattern

    return [TextContent(type="text", text=json.dumps(result))]


# ── Shared Execution Logic ──────────────────────────────────────────────────

def _build_env(cwd: str) -> dict[str, str]:
    """Build environment with workspace-aware PATH (venv, node_modules, etc.)."""
    import os
    env = os.environ.copy()
    extra_paths: list[str] = []
    from pathlib import Path
    workspace = Path(cwd)

    # Python venv
    for venv_dir in [".venv", "venv", "env"]:
        bin_dir = workspace / venv_dir / "bin"
        if bin_dir.is_dir():
            extra_paths.append(str(bin_dir))
            break

    # Node modules
    npm_bin = workspace / "node_modules" / ".bin"
    if npm_bin.is_dir():
        extra_paths.append(str(npm_bin))

    # Hivemind backend venv (for testing hivemind itself)
    hm_venv = Path("/app/.venv/bin")
    if hm_venv.is_dir():
        extra_paths.append(str(hm_venv))

    if extra_paths:
        env["PATH"] = ":".join(extra_paths) + ":" + env.get("PATH", "")

    # Ensure Python output is unbuffered
    env["PYTHONUNBUFFERED"] = "1"

    return env


async def _run_command_safe(
    cmd_parts: list[str],
    cwd: str,
    timeout: int,
) -> dict[str, Any]:
    """Run a subprocess safely via asyncio.to_thread with semaphore."""
    sem = _get_semaphore()
    env = _build_env(cwd)

    async with sem:
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd_parts,
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
                shell=False,
                env=env,
            )
            return {
                "status": "passed" if result.returncode == 0 else "failed",
                "exit_code": result.returncode,
                "stdout": result.stdout.decode(errors="replace")[:_STDOUT_CAP],
                "stderr": result.stderr.decode(errors="replace")[:_STDERR_CAP],
                "timeout": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "exit_code": -1,
                "stdout": "",
                "stderr": f"TIMEOUT: Command exceeded {timeout}s limit",
                "timeout": True,
            }
        except FileNotFoundError as e:
            return {
                "status": "failed",
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command not found: {e}",
                "timeout": False,
            }
        except Exception as e:
            logger.exception("Unexpected error executing command")
            return {
                "status": "failed",
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Execution error: {e}",
                "timeout": False,
            }


# ── Tool Registration ───────────────────────────────────────────────────────

register_tool(
    Tool(
        name="hivemind-execute_guard",
        description=(
            "Execute a guard command (test/lint/typecheck) for a task. "
            "Runs the guard's configured command or a provided command, "
            "checks it against the allowlist, executes it, and updates "
            "the task_guard status automatically. "
            "Allowed commands: " + ", ".join(_get_allowlist())
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {
                    "type": "string",
                    "description": "Task key (e.g. TASK-42)",
                },
                "guard_id": {
                    "type": "string",
                    "description": "Guard UUID or guard_key",
                },
                "command": {
                    "type": "string",
                    "description": "Command to execute (e.g. 'pytest backend/tests/ -x'). If omitted, uses the guard's configured command.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (default: workspace root)",
                },
            },
            "required": ["task_key", "guard_id"],
        },
    ),
    _handle_execute_guard,
)

register_tool(
    Tool(
        name="hivemind-run_command",
        description=(
            "Execute an allowlisted shell command in the workspace. "
            "Use this to run tests, linters, type checkers, or build commands. "
            "The command must match the allowlist patterns. "
            "Allowed: " + ", ".join(_get_allowlist())
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to run (e.g. 'pytest backend/tests/ -x --tb=short', 'ruff check backend/', 'npm run lint')",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (default: workspace root)",
                },
            },
            "required": ["command"],
        },
    ),
    _handle_run_command,
)
