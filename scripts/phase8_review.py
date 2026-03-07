"""Move all Phase 8 tasks through state machine to in_review, then list them."""
import json
import sys
import time
sys.path.insert(0, ".")
from scripts.api_test import api_get, api_patch, api_post, mcp_call

USER_ID = "7ff11326-644a-4859-820e-18e4037239b9"
EPIC_KEY = "EPIC-PHASE-8"


def get_tasks():
    tasks = api_get(f"/api/epics/{EPIC_KEY}/tasks?limit=200")
    if not isinstance(tasks, list):
        print(f"ERROR: {tasks}")
        sys.exit(1)
    return tasks


def move_task_to_in_review(task_key: str, result_text: str):
    """Move a task from scoped → ready → in_progress → submit_result → in_review."""
    # 1. Assign
    r = mcp_call("hivemind-assign_task", {"task_key": task_key, "user_id": USER_ID})
    print(f"  assign: {_status(r)}")

    # 2. scoped → ready
    r = mcp_call("hivemind-update_task_state", {"task_key": task_key, "target_state": "ready"})
    print(f"  → ready: {_status(r)}")

    # 3. ready → in_progress
    r = mcp_call("hivemind-update_task_state", {"task_key": task_key, "target_state": "in_progress"})
    print(f"  → in_progress: {_status(r)}")

    # 4. submit_result
    r = mcp_call("hivemind-submit_result", {
        "task_key": task_key,
        "result": result_text,
        "artifacts": []
    })
    print(f"  submit_result: {_status(r)}")

    # 5. in_progress → in_review
    r = mcp_call("hivemind-update_task_state", {"task_key": task_key, "target_state": "in_review"})
    print(f"  → in_review: {_status(r)}")


def _status(r):
    if isinstance(r, dict) and "result" in r:
        text = r["result"][0].get("text", "") if r["result"] else ""
        if "error" in text.lower() or "nicht erlaubt" in text.lower():
            return f"ERROR: {text[:120]}"
        return "OK"
    return f"ERROR: {r}"


# Descriptions for each task's result
TASK_RESULTS = {
    "TASK-8-001": "Alembic migration 012_phase8_autonomy_tables.py creates all 5 Phase 8 tables: ai_provider_configs, conductor_dispatches, review_recommendations, mcp_bridge_configs, project_integrations. Includes all indexes, constraints, CHECK(namespace!='hivemind'), governance default in app_settings.",
    "TASK-8-002": "AI-Provider-Service with provider abstraction (base.py ABC), implementations for OpenAI, Anthropic, Ollama, GitHub Models, Custom providers. Provider routing via ai_provider_configs table with per-agent-role configuration. Fallback cascade: role config → global → BYOAI. API Key encryption with AES-256-GCM.",
    "TASK-8-003": "Rate-limiting (RPM/TPM) and retry with exponential backoff (1s→2s→4s→max 60s, 3 attempts on 429/503). Token calibration per provider via HIVEMIND_TOKEN_COUNT_CALIBRATION env var. Integrated into ai_provider.py service.",
    "TASK-8-004": "Conductor-Orchestrator core service with event-driven dispatch engine. Registered in scheduler.py gated by HIVEMIND_CONDUCTOR_ENABLED. conductor_dispatches table for audit trail. Handles state transitions and agent dispatching.",
    "TASK-8-005": "12 dispatch rules for Conductor covering task-state, epic-state, and event triggers. Cooldown mechanism with cooldown_key for idempotency. Parallel dispatch support via HIVEMIND_CONDUCTOR_PARALLEL.",
    "TASK-8-006": "Governance-Levels service with 3 stufen (manual, assisted, auto) × 7 decision types. Stored in app_settings.governance JSON. API endpoints in settings router for reading/updating governance config.",
    "TASK-8-007": "Reviewer-Agent MCP tools: submit_review_recommendation (confidence-based approve/reject/needs_human_review) and veto_auto_review. Implemented in reviewer_tools.py (366 lines). Does not modify task state directly.",
    "TASK-8-008": "Auto-Review Cron service: checks review_recommendations with expired grace_period_until, auto-approves if confidence >= threshold and governance.review='auto'. Registered in scheduler.py.",
    "TASK-8-009": "GitLab Webhook Consumer: POST /api/webhooks/gitlab endpoint. Processes issue.opened, merge_request.merged, pipeline.failed, push events. Writes direction='inbound' to sync_outbox. MCP tools: get_gitlab_mr, get_gitlab_pipeline.",
    "TASK-8-010": "GitHub Webhook Consumer: POST /api/webhooks/github with HMAC-SHA256 signature validation. Processes issues, pull_requests, check_run, push, workflow_run, projects_v2_item, release events. MCP tools: get_github_pr, get_github_issue, get_github_check_status.",
    "TASK-8-011": "GitHub Models Provider using OpenAI-compatible SDK with base_url=models.inference.ai.azure.com. Auth via GitHub PAT. Model catalog loading. Implemented in ai_providers/github_models.py.",
    "TASK-8-012": "GitHub Actions Agent: 3 modes (AI-Provider, Guard, Agent-in-CI). Conductor integration with execution_mode field. Workflow Dispatch trigger via GitHub API. Guard results via report_guard_result MCP tool. Commit status checks.",
    "TASK-8-013": "GitHub Projects V2 bidirectional sync via GraphQL. State mapping (incoming→Backlog, scoped→Todo, etc.). Outbound via sync_outbox, inbound via webhooks. project_integrations table for config. Board changes never auto-change Hivemind state.",
    "TASK-8-014": "MCP Bridge/Gateway core: MCP client implementation, bridge registry, proxy dispatch layer. Namespace isolation (hivemind-*, github/*, gitlab/*). Transport support: stdio, SSE, HTTP. Tool discovery from external MCP servers.",
    "TASK-8-015": "MCP Bridge RBAC + Audit: All proxied tool calls go through RBAC check, audit logging, rate-limiting. Admin API: GET/POST /api/admin/mcp-bridges. Tool blocklist (delete_repository always blocked). Env vars AES-256-GCM encrypted.",
    "TASK-8-016": "Bibliothekar Auto-Modus extension: per-agent-role provider routing integrated with Conductor dispatch. Provider-specific token calibration. Adaptive token budget based on provider capabilities.",
    "TASK-8-017": "Nexus Grid 3D Backend: GET /api/nexus/graph3d endpoint returning optimized graph data for large codebases. Aggregation for 1000+ node rendering.",
    "TASK-8-018": "Worker-Endpoint-Pool: Multi-endpoint load balancing with round_robin, weighted, least_busy strategies. Endpoints JSONB array in ai_provider_configs. Health-check with 60s cooldown. RPM-limit per endpoint. Implemented in ai_providers/pool.py.",
    "TASK-8-019": "Auto-Escalation extension: AI-powered proactive escalation. Conductor analyzes blocked tasks and decides escalation timing and backup-owner selection autonomously. Integrates with existing Phase 6 SLA cron.",
    "TASK-8-020": "Frontend AI-Provider-Config Settings UI: per-agent-role provider selection, model, endpoint, API key, token budget, RPM limit. GitHub Models model catalog browser. Endpoint pool editor. Test button. AiProviderConfigPanel.vue (658 lines).",
    "TASK-8-021": "Frontend MCP Bridge Config Settings UI (Admin-only): Bridge list with status, add/edit dialog, transport selection, env vars, tool catalog, allow/blocklist, test button, health status. McpBridgeConfigPanel.vue (686 lines).",
    "TASK-8-022": "Frontend Governance-Tab in Settings: Per decision-type dropdown (manual|assisted|auto), auto config (confidence threshold, grace period), safeguard display, autonomy spectrum visualization. GovernanceConfigPanel.vue (362 lines).",
    "TASK-8-023": "Frontend Prompt Station Auto-Modus: No prompt cards in auto mode, monitoring view (active agents, token consumption, status). 'Manuell eingreifen' button. useAutoMode.ts composable.",
    "TASK-8-024": "Frontend AI-Review-Panel in Task-Detail: For assisted mode shows review recommendation with checklist, confidence badge, 1-click approve/reject. For auto mode shows grace period countdown + intervene button. AiReviewPanel.vue (465 lines) + TaskReviewPanel.vue (625 lines).",
    "TASK-8-025": "Frontend Nexus Grid 3D (Three.js WebGL): 2D↔3D toggle, orbit controls fly-through navigation, Fog of War as transparent spheres, instanced rendering for 1000 nodes@30fps, LOD, GLSL shader fog overlay. NexusGrid3D.vue (282 lines).",
    "TASK-8-026": "Frontend KPI-Dashboard complete: All 6 KPIs with historical graphs (7/30-day time series). KPI history endpoint in kpis router.",
}


if __name__ == "__main__":
    tasks = get_tasks()
    task_keys = sorted([t["task_key"] for t in tasks])
    
    print(f"Found {len(task_keys)} Phase 8 tasks")
    print("=" * 60)
    
    for tk in task_keys:
        task = next(t for t in tasks if t["task_key"] == tk)
        state = task["state"]
        print(f"\n{tk} [{state}]: {task['title'][:60]}")
        
        if state == "in_review":
            print("  Already in_review — skipping")
            continue
        elif state == "done":
            print("  Already done — skipping")
            continue
        elif state == "in_progress":
            # Just need submit_result + transition
            result_text = TASK_RESULTS.get(tk, f"Phase 8 implementation for {tk}")
            r = mcp_call("hivemind-submit_result", {"task_key": tk, "result": result_text, "artifacts": []})
            print(f"  submit_result: {_status(r)}")
            r = mcp_call("hivemind-update_task_state", {"task_key": tk, "target_state": "in_review"})
            print(f"  → in_review: {_status(r)}")
            continue
        elif state == "ready":
            result_text = TASK_RESULTS.get(tk, f"Phase 8 implementation for {tk}")
            r = mcp_call("hivemind-update_task_state", {"task_key": tk, "target_state": "in_progress"})
            print(f"  → in_progress: {_status(r)}")
            r = mcp_call("hivemind-submit_result", {"task_key": tk, "result": result_text, "artifacts": []})
            print(f"  submit_result: {_status(r)}")
            r = mcp_call("hivemind-update_task_state", {"task_key": tk, "target_state": "in_review"})
            print(f"  → in_review: {_status(r)}")
            continue
        elif state != "scoped":
            print(f"  Unexpected state '{state}' — skipping")
            continue
        
        result_text = TASK_RESULTS.get(tk, f"Phase 8 implementation for {tk}")
        move_task_to_in_review(tk, result_text)
    
    print("\n" + "=" * 60)
    print("Final state of all Phase 8 tasks:")
    final = get_tasks()
    for t in sorted(final, key=lambda x: x["task_key"]):
        print(f"  {t['task_key']:12s} | {t['state']:12s} | {t['title'][:50]}")
