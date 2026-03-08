"""Agentic Dispatch Service — Tool-executing loop for AI workers.

When a prompt is dispatched via the Conductor, this service:
1. Collects available MCP tools from the registry
2. Sends the prompt to the AI provider with tools + system context
3. Executes tool_calls via the MCP tool handlers
4. Feeds tool results back to the AI for multi-turn conversation
5. Repeats until the AI finishes (no more tool_calls) or max iterations

This enables the AI worker to actually operate on the workspace filesystem
and interact with Hivemind's MCP tools autonomously.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.services.ai_providers.base import AIResponse, ToolCall

logger = logging.getLogger(__name__)

# Maximum number of tool-call loop iterations to prevent runaway agents
MAX_ITERATIONS = 25

# Maximum total tool calls across all iterations
MAX_TOTAL_TOOL_CALLS = 100

# Safety truncation limit for prompts (skill content can make prompts 400KB+)
MAX_PROMPT_CHARS = 60_000


@dataclass
class AgenticResult:
    """Result of an agentic dispatch execution."""
    content: str | None = None
    tool_calls_executed: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    model: str = ""
    finish_reason: str = ""
    error: str | None = None


def _get_mcp_tools_as_dicts() -> list[dict[str, Any]]:
    """Collect all MCP tool definitions and convert to plain dicts for AI providers."""
    from app.mcp.server import _tool_definitions

    tools = []
    for tool_def in _tool_definitions:
        tools.append({
            "name": tool_def.name,
            "description": tool_def.description or "",
            "inputSchema": tool_def.inputSchema or {"type": "object", "properties": {}},
        })
    return tools


COMMON_TOOL_PREFIXES = ("hivemind-fs_",)

COMMON_TOOL_NAMES = {
    "hivemind-get_task",
    "hivemind-get_epic",
    "hivemind-get_doc",
    "hivemind-get_guards",
    "hivemind-get_skills",
    "hivemind-get_skill_versions",
    "hivemind-get_wiki_article",
    "hivemind-search_wiki",
    "hivemind-get_prompt",
    "hivemind-list_tasks",
    "hivemind-list_skills",
    "hivemind-semantic_search",
}

ROLE_TOOL_NAMES: dict[str, set[str]] = {
    "worker": {
        "hivemind-submit_result",
        "hivemind-report_guard_result",
        "hivemind-create_decision_request",
        "hivemind-update_task_state",
    },
    "reviewer": {
        "hivemind-approve_review",
        "hivemind-reject_review",
        "hivemind-reenter_from_qa_failed",
        "hivemind-cancel_task",
        "hivemind-submit_review_recommendation",
        "hivemind-veto_auto_review",
        "hivemind-get_review_recommendations",
    },
    "gaertner": {
        "hivemind-propose_skill",
        "hivemind-propose_skill_change",
        "hivemind-submit_skill_proposal",
        "hivemind-create_wiki_article",
        "hivemind-update_wiki_article",
        "hivemind-create_decision_record",
        "hivemind-update_doc",
    },
    "kartograph": {
        "hivemind-create_wiki_article",
        "hivemind-update_wiki_article",
        "hivemind-create_epic_doc",
        "hivemind-link_wiki_to_epic",
        "hivemind-propose_guard",
        "hivemind-propose_guard_change",
        "hivemind-submit_guard_proposal",
        "hivemind-propose_epic_restructure",
    },
    "architekt": {
        "hivemind-decompose_epic",
        "hivemind-create_task",
        "hivemind-create_subtask",
        "hivemind-link_skill",
        "hivemind-set_context_boundary",
        "hivemind-assign_task",
        "hivemind-update_task_state",
    },
    "stratege": {
        "hivemind-propose_epic",
        "hivemind-update_epic_proposal",
        "hivemind-accept_epic_proposal",
        "hivemind-reject_epic_proposal",
        "hivemind-draft_requirement",
    },
    "triage": {
        "hivemind-route_event",
        "hivemind-ignore_event",
        "hivemind-assign_bug",
        "hivemind-accept_epic_proposal",
        "hivemind-reject_epic_proposal",
        "hivemind-merge_skill",
        "hivemind-reject_skill",
        "hivemind-accept_skill_change",
        "hivemind-reject_skill_change",
        "hivemind-merge_guard",
        "hivemind-reject_guard",
        "hivemind-accept_epic_restructure",
        "hivemind-reject_epic_restructure",
        "hivemind-resolve_decision_request",
        "hivemind-resolve_escalation",
        "hivemind-reassign_epic_owner",
        "hivemind-list_decision_requests",
    },
}


def _normalize_agent_role(agent_role: str) -> str:
    normalized = (agent_role or "").strip().lower()
    return normalized if normalized in ROLE_TOOL_NAMES else "worker"


def _filter_tools_for_agent(
    all_tools: list[dict[str, Any]],
    agent_role: str,
    allowed_tool_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter MCP tools to the subset relevant for the selected agent role."""
    normalized_role = _normalize_agent_role(agent_role)
    allowed_names = COMMON_TOOL_NAMES | ROLE_TOOL_NAMES[normalized_role]
    if allowed_tool_names is not None:
        allowed_names &= set(allowed_tool_names)

    seen: set[str] = set()
    result = []
    for tool in all_tools:
        name = tool["name"]
        if name in seen:
            continue
        if name in allowed_names or any(name.startswith(prefix) for prefix in COMMON_TOOL_PREFIXES):
            seen.add(name)
            result.append(tool)
    return result


def get_allowed_tool_names_for_role(agent_role: str) -> set[str]:
    normalized_role = _normalize_agent_role(agent_role)
    return set(COMMON_TOOL_NAMES | ROLE_TOOL_NAMES[normalized_role])


def _parse_text_tool_calls(content: str) -> list[ToolCall]:
    """Parse tool calls written as XML in content (fallback for models with broken tool-call API).

    Some Claude models via Copilot REST proxy emit tool calls as text:
        <tool_call>{"name": "hivemind-get_task", "arguments": {...}}</tool_call>
    instead of returning them via the API tool_calls field.
    """
    tool_calls: list[ToolCall] = []
    pattern = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
    for i, match in enumerate(pattern.finditer(content)):
        try:
            data = json.loads(match.group(1))
            name = data.get("name", "")
            args = data.get("arguments") or data.get("parameters") or {}
            if name:
                tool_calls.append(ToolCall(id=f"text_call_{i}", name=name, arguments=args))
        except Exception:
            pass
    return tool_calls


async def _execute_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    agent_role: str,
) -> str:
    """Execute a single MCP tool call and return the result as a string."""
    from app.mcp.server import call_tool

    try:
        call_args = dict(arguments or {})
        call_args.setdefault("_actor_role", agent_role)
        result_contents = await call_tool(tool_name, call_args)
        # call_tool returns list[TextContent]
        parts = []
        for content in result_contents:
            if hasattr(content, "text"):
                parts.append(content.text)
            else:
                parts.append(str(content))
        return "\n".join(parts)
    except Exception as exc:
        logger.exception("Tool execution failed: %s", tool_name)
        return json.dumps({"error": {"code": "execution_error", "message": str(exc)}})


def _build_tool_docs(tools: list[dict[str, Any]]) -> str:
    """Generate compact text documentation for tools to embed in the system prompt."""
    if not tools:
        return ""
    lines = ["## Verfügbare Tools", ""]
    for tool in tools:
        name = tool["name"]
        desc = (tool.get("description") or "").strip()
        schema = tool.get("inputSchema") or {}
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        params_parts = []
        for param, pdef in props.items():
            ptype = pdef.get("type", "any")
            req_marker = "*" if param in required else "?"
            pdesc = pdef.get("description", "")
            params_parts.append(f"  {param}{req_marker} ({ptype}): {pdesc}" if pdesc else f"  {param}{req_marker} ({ptype})")
        params_str = "\n".join(params_parts) if params_parts else "  (keine Parameter)"
        lines.append(f"### {name}")
        if desc:
            lines.append(desc)
        lines.append(f"Parameter:\n{params_str}")
        lines.append("")
    lines.append("Legende: * = Pflichtfeld, ? = optional")
    return "\n".join(lines)


def _build_system_prompt(
    agent_role: str,
    task_key: str | None = None,
    epic_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    """Build a system prompt that gives the AI worker context about its environment."""
    parts = [
        "Du bist ein AI-Worker im Hivemind-Projektmanagement-System.",
        "Du hast Zugriff auf MCP-Tools, mit denen du das Workspace-Dateisystem lesen/schreiben kannst,",
        "sowie auf Hivemind-Tools für Tasks, Skills, Epics, Wiki-Artikel und Dokumente.",
        "",
        "## WICHTIG: Tool-Aufruf-Format",
        "Wenn du ein Tool aufrufen möchtest, MUSST du exakt dieses XML-Format verwenden:",
        "<tool_call>",
        '{\"name\": \"tool-name\", \"arguments\": {\"param\": \"wert\"}}',
        "</tool_call>",
        "Schreibe NIEMALS Tool-Responses selbst — das System führt den Tool-Aufruf aus und gibt dir das Ergebnis zurück.",
        "Nutze IMMER das <tool_call>-Format für jeden Tool-Aufruf, auch wenn du mehrere Tools aufrufen möchtest.",
        "",
        "## Workspace",
        "Das Workspace-Root ist `/workspace` (gemounted vom Host-Projekt).",
        "Du kannst mit `hivemind-fs_read`, `hivemind-fs_write`, `hivemind-fs_list`, `hivemind-fs_search`",
        "und `hivemind-fs_stat` auf Dateien im Workspace zugreifen.",
        "",
        "## Arbeitsweise",
        "1. Lies zuerst den Task und die zugehörigen Skills, um die Anforderungen zu verstehen.",
        "2. Nutze die Filesystem-Tools, um den relevanten Code zu finden und zu verstehen.",
        "3. Implementiere die Änderungen gemäß den DoD-Kriterien (Definition of Done).",
        "4. Wenn du fertig bist, nutze `hivemind-submit_result` um dein Ergebnis abzuliefern.",
        "",
        "## Regeln",
        "- Ändere nur Dateien, die für den Task relevant sind.",
        "- Halte dich an die bestehenden Code-Konventionen im Projekt.",
        "- Arbeite inkrementell — lies erst, plane, dann schreibe.",
        "- Wenn du dir unsicher bist, lies weitere Dateien für Kontext.",
    ]

    if tools:
        parts.append("")
        parts.append(_build_tool_docs(tools))

    if task_key:
        parts.append(f"\n## Aktueller Task: {task_key}")
        parts.append(f"Lies den Task mit `hivemind-get_task` (task_key: '{task_key}') für Details.")

    if epic_id:
        parts.append(f"\n## Epic: {epic_id}")
        parts.append(f"Lies das Epic mit `hivemind-get_epic` (epic_key: '{epic_id}') für Kontext.")

    parts.append(f"\n## Rolle: {agent_role}")

    return "\n".join(parts)


async def agentic_dispatch(
    provider: Any,
    prompt: str,
    agent_role: str = "worker",
    task_key: str | None = None,
    epic_id: str | None = None,
    max_iterations: int = MAX_ITERATIONS,
    allowed_tool_names: set[str] | None = None,
    token_budget: int | None = None,
) -> AgenticResult:
    """Execute an agentic dispatch loop with tool calling.

    Args:
        provider: An AIProvider instance (must support send_messages for best results).
        prompt: The user prompt to send.
        agent_role: The agent role (worker, gaertner, etc.).
        task_key: Optional task key for context.
        epic_id: Optional epic ID for context.
        max_iterations: Maximum number of agentic loop iterations.
        token_budget: Per-dispatch token budget from policy (limits prompt size).

    Returns:
        AgenticResult with the final content and execution history.
    """
    result = AgenticResult()
    t0 = time.perf_counter()

    # 0. Truncate prompt if too large for API (skill content can make prompts 400KB+)
    # token_budget is approx tokens; 1 token ≈ 4 chars; leave headroom for response
    max_prompt_chars = MAX_PROMPT_CHARS
    if token_budget and token_budget > 0:
        max_prompt_chars = min(max_prompt_chars, token_budget * 3)
    if len(prompt) > max_prompt_chars:
        logger.warning(
            "Prompt truncated from %d to %d chars for role '%s' (token_budget=%s)",
            len(prompt), max_prompt_chars, agent_role, token_budget,
        )
        prompt = prompt[:max_prompt_chars] + "\n\n[... Prompt gekürzt — nutze MCP-Tools für weiteren Kontext ...]"

    # 1. Collect and filter MCP tools
    all_tools = _get_mcp_tools_as_dicts()
    tools = _filter_tools_for_agent(all_tools, agent_role, allowed_tool_names)
    logger.info(
        "Agentic dispatch: %d tools available (of %d total) for role '%s'",
        len(tools), len(all_tools), agent_role,
    )

    # 2. Build system prompt — include tool docs inline so the model knows what's available
    # We do NOT pass tools via native API (causes BadRequest with Copilot proxy for Claude models);
    # instead the model uses <tool_call> text format parsed by _parse_text_tool_calls.
    system = _build_system_prompt(agent_role, task_key, epic_id, tools=tools)

    # 3. Initialize messages
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": prompt},
    ]

    total_tool_calls = 0

    # 4. Agentic loop
    for iteration in range(max_iterations):
        result.iterations = iteration + 1
        logger.info("Agentic dispatch iteration %d/%d", iteration + 1, max_iterations)

        try:
            from app.services.ai_provider import acquire_provider_capacity

            await acquire_provider_capacity(agent_role, provider)
            # Use send_messages for multi-turn; tools are NOT passed via native API
            # (Copilot proxy returns BadRequest with 21+ tools for Claude models).
            # Tool descriptions are embedded in the system prompt; the model uses
            # <tool_call> text format which _parse_text_tool_calls() handles below.
            response: AIResponse = await provider.send_messages(
                messages=messages,
                tools=[],
                system=system,
            )
        except Exception as exc:
            logger.exception("AI provider error in iteration %d", iteration + 1)
            result.error = str(exc)
            break

        # Track token usage
        result.total_input_tokens += response.input_tokens
        result.total_output_tokens += response.output_tokens
        result.model = response.model
        result.finish_reason = response.finish_reason

        # Fallback: parse text-format tool calls (Claude via Copilot proxy has broken tool_calls)
        effective_tool_calls = list(response.tool_calls or [])
        if not effective_tool_calls and response.content:
            effective_tool_calls = _parse_text_tool_calls(response.content)
            if effective_tool_calls:
                logger.info(
                    "Parsed %d text-format tool call(s) from content (tool_calls API not supported)",
                    len(effective_tool_calls),
                )

        # If no tool calls → we're done
        if not effective_tool_calls:
            result.content = response.content
            logger.info("Agentic dispatch completed after %d iterations", iteration + 1)
            break

        # Guard: max total tool calls
        total_tool_calls += len(effective_tool_calls)
        if total_tool_calls > MAX_TOTAL_TOOL_CALLS:
            result.content = response.content
            result.error = f"Max total tool calls ({MAX_TOTAL_TOOL_CALLS}) exceeded"
            logger.warning("Agentic dispatch aborted: too many tool calls (%d)", total_tool_calls)
            break

        # Append assistant message with tool_calls to conversation
        # Strip any fake <tool_call>/<tool_response> blocks from content before adding to history
        clean_content = re.split(r"<tool_call>", response.content or "", maxsplit=1)[0].strip()
        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if clean_content:
            assistant_msg["content"] = clean_content
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id or f"call_{iteration}_{i}",
                "name": tc.name,
                "arguments": tc.arguments,
            }
            for i, tc in enumerate(effective_tool_calls)
        ]
        messages.append(assistant_msg)

        # Execute each tool call and collect results
        for tc in effective_tool_calls:
            tc_id = tc.id or f"call_{iteration}_{effective_tool_calls.index(tc)}"
            logger.info("Executing tool: %s (id=%s)", tc.name, tc_id)

            tool_result = await _execute_tool_call(tc.name, tc.arguments, agent_role=agent_role)

            # Track execution
            result.tool_calls_executed.append({
                "iteration": iteration + 1,
                "tool": tc.name,
                "arguments": tc.arguments,
                "result_preview": tool_result[:500] if tool_result else "",
            })

            # Append tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": tool_result,
            })

        # If this was the last iteration, note it
        if iteration + 1 >= max_iterations:
            result.error = f"Max iterations ({max_iterations}) reached"
            result.content = response.content
            logger.warning("Agentic dispatch reached max iterations")

    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "Agentic dispatch finished: %d iterations, %d tool calls, %dms, %d in/%d out tokens",
        result.iterations,
        len(result.tool_calls_executed),
        duration_ms,
        result.total_input_tokens,
        result.total_output_tokens,
    )

    return result
