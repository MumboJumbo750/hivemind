from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_thread_session import AgentThreadSession
from app.models.ai_provider import AIProviderConfig
from app.models.epic import Epic
from app.models.project import Project
from app.models.task import Task

logger = logging.getLogger(__name__)


THREAD_POLICY_STATELESS = "stateless"
THREAD_POLICY_ATTEMPT = "attempt_stateful"
THREAD_POLICY_EPIC = "epic_stateful"
THREAD_POLICY_PROJECT = "project_stateful"

SUPPORTED_THREAD_POLICIES = {
    THREAD_POLICY_STATELESS,
    THREAD_POLICY_ATTEMPT,
    THREAD_POLICY_EPIC,
    THREAD_POLICY_PROJECT,
}
STATEFUL_THREAD_POLICIES = {
    THREAD_POLICY_ATTEMPT,
    THREAD_POLICY_EPIC,
    THREAD_POLICY_PROJECT,
}
ROLE_DEFAULT_THREAD_POLICIES: dict[str, str] = {
    "worker": THREAD_POLICY_ATTEMPT,
    "reviewer": THREAD_POLICY_ATTEMPT,
    "gaertner": THREAD_POLICY_STATELESS,
    "architekt": THREAD_POLICY_EPIC,
    "stratege": THREAD_POLICY_PROJECT,
    "kartograph": THREAD_POLICY_PROJECT,
    "triage": THREAD_POLICY_PROJECT,
}


def normalize_thread_policy(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in SUPPORTED_THREAD_POLICIES else None


def default_thread_policy(agent_role: str) -> str:
    return ROLE_DEFAULT_THREAD_POLICIES.get((agent_role or "").strip().lower(), THREAD_POLICY_STATELESS)


def resolve_thread_policy_for_role(agent_role: str, configured_policy: Any) -> str:
    return normalize_thread_policy(configured_policy) or default_thread_policy(agent_role)


class AgentThreadService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_context(
        self,
        *,
        agent_role: str,
        task_id: str | None = None,
        epic_id: str | None = None,
        project_id: str | None = None,
        create_session: bool = False,
    ) -> dict[str, Any]:
        normalized_role = (agent_role or "").strip().lower() or "worker"
        task = await self._load_task(task_id) if task_id else None
        epic = await self._resolve_epic(task=task, epic_ref=epic_id)
        project = await self._resolve_project(task=task, epic=epic, project_ref=project_id)

        configured_policy = await self._load_provider_thread_policy(normalized_role)
        role_policy = resolve_thread_policy_for_role(normalized_role, configured_policy)
        effective_policy, scope_label = self._resolve_effective_policy(
            role_policy,
            task=task,
            epic=epic,
            project=project,
        )
        project_policy = self._resolve_project_override(project, normalized_role)
        if project_policy:
            effective_policy, scope_label = self._resolve_effective_policy(
                project_policy,
                task=task,
                epic=epic,
                project=project,
            )

        thread_key = self._build_thread_key(
            agent_role=normalized_role,
            policy=effective_policy,
            task=task,
            epic=epic,
            project=project,
        )
        session = None
        if thread_key and create_session:
            session = await self._get_or_create_session(
                thread_key=thread_key,
                agent_role=normalized_role,
                policy=effective_policy,
                task=task,
                epic=epic,
                project=project,
            )
        elif thread_key:
            session = await self._get_session_by_key(thread_key)

        history = self._session_history(session)
        return {
            "agent_role": normalized_role,
            "policy": effective_policy,
            "configured_policy": role_policy,
            "project_override_policy": project_policy,
            "thread_key": thread_key,
            "scope": scope_label,
            "reuse_enabled": bool(thread_key),
            "session_id": str(session.id) if session is not None else None,
            "project_id": str(project.id) if project is not None else None,
            "epic_id": str(epic.id) if epic is not None else None,
            "task_id": str(task.id) if task is not None else None,
            "history": history,
            "prompt_block": self._render_prompt_block(
                policy=effective_policy,
                scope_label=scope_label,
                thread_key=thread_key,
                history=history,
            ),
        }

    async def record_dispatch_outcome(
        self,
        *,
        thread_context: dict[str, Any] | None,
        dispatch_id: str,
        prompt_type: str,
        trigger_detail: str,
        status: str,
        content: str | None = None,
        model: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        if not thread_context or not thread_context.get("thread_key"):
            return
        try:
            session = await self._get_session_by_key(str(thread_context["thread_key"]))
            if session is None:
                return

            metadata = dict(session.session_metadata or {})
            history = metadata.get("history")
            if not isinstance(history, list):
                history = []

            excerpt = (content or "").strip().replace("\n", " ")
            if len(excerpt) > 240:
                excerpt = excerpt[:239].rstrip() + "…"

            history.append(
                {
                    "dispatch_id": dispatch_id,
                    "prompt_type": prompt_type,
                    "trigger_detail": trigger_detail,
                    "status": status,
                    "model": model,
                    "tool_call_count": len(tool_calls or []),
                    "content_excerpt": excerpt,
                    "at": datetime.now(UTC).isoformat(),
                }
            )
            metadata["history"] = history[-6:]
            session.session_metadata = metadata
            session.dispatch_count = int(session.dispatch_count or 0) + 1
            session.last_activity_at = datetime.now(UTC)
            session.summary = self._build_summary(metadata["history"])
            await self.db.flush()
        except Exception:
            logger.exception("record_dispatch_outcome failed for thread %s", thread_context.get("thread_key"))

    async def _load_provider_thread_policy(self, agent_role: str) -> str | None:
        result = await self.db.execute(
            select(AIProviderConfig.thread_policy).where(AIProviderConfig.agent_role == agent_role)
        )
        return normalize_thread_policy(result.scalar_one_or_none())

    async def _load_task(self, task_ref: str) -> Task | None:
        try:
            task_uuid = uuid.UUID(str(task_ref))
        except (TypeError, ValueError):
            task_uuid = None
        if task_uuid is not None:
            result = await self.db.execute(select(Task).where(Task.id == task_uuid))
            task = result.scalar_one_or_none()
            if task is not None:
                return task

        result = await self.db.execute(select(Task).where(Task.task_key == str(task_ref)))
        return result.scalar_one_or_none()

    async def _resolve_epic(self, *, task: Task | None, epic_ref: str | None) -> Epic | None:
        epic_id = getattr(task, "epic_id", None)
        if epic_id is not None:
            result = await self.db.execute(select(Epic).where(Epic.id == epic_id))
            epic = result.scalar_one_or_none()
            if epic is not None:
                return epic

        if not epic_ref:
            return None
        try:
            epic_uuid = uuid.UUID(str(epic_ref))
            result = await self.db.execute(select(Epic).where(Epic.id == epic_uuid))
            epic = result.scalar_one_or_none()
            if epic is not None:
                return epic
        except (TypeError, ValueError):
            pass

        result = await self.db.execute(select(Epic).where(Epic.epic_key == str(epic_ref)))
        return result.scalar_one_or_none()

    async def _resolve_project(
        self,
        *,
        task: Task | None,
        epic: Epic | None,
        project_ref: str | None,
    ) -> Project | None:
        project_id = getattr(epic, "project_id", None)
        if project_id is not None:
            result = await self.db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if project is not None:
                return project

        del task
        if not project_ref:
            return None
        try:
            project_uuid = uuid.UUID(str(project_ref))
            result = await self.db.execute(select(Project).where(Project.id == project_uuid))
            project = result.scalar_one_or_none()
            if project is not None:
                return project
        except (TypeError, ValueError):
            pass
        return None

    def _resolve_project_override(self, project: Project | None, agent_role: str) -> str | None:
        if project is None:
            return None
        overrides = dict(getattr(project, "agent_thread_overrides", None) or {})
        return normalize_thread_policy(overrides.get(agent_role))

    def _resolve_effective_policy(
        self,
        policy: str,
        *,
        task: Task | None,
        epic: Epic | None,
        project: Project | None,
    ) -> tuple[str, str]:
        if policy == THREAD_POLICY_ATTEMPT:
            if task is not None:
                attempt_label = f"{task.task_key} v{int(task.version or 0)} / qa#{int(task.qa_failed_count or 0)}"
                return THREAD_POLICY_ATTEMPT, f"attempt:{attempt_label}"
            return THREAD_POLICY_STATELESS, "stateless:fallback"
        if policy == THREAD_POLICY_EPIC:
            if epic is not None:
                return THREAD_POLICY_EPIC, f"epic:{epic.epic_key}"
            return THREAD_POLICY_STATELESS, "stateless:fallback"
        if policy == THREAD_POLICY_PROJECT:
            if project is not None:
                return THREAD_POLICY_PROJECT, f"project:{project.slug}"
            return THREAD_POLICY_STATELESS, "stateless:fallback"
        return THREAD_POLICY_STATELESS, "stateless"

    def _build_thread_key(
        self,
        *,
        agent_role: str,
        policy: str,
        task: Task | None,
        epic: Epic | None,
        project: Project | None,
    ) -> str | None:
        if policy == THREAD_POLICY_STATELESS:
            return None
        if policy == THREAD_POLICY_ATTEMPT and task is not None:
            return (
                f"{agent_role}:attempt:{task.task_key}:"
                f"v{int(task.version or 0)}:qa{int(task.qa_failed_count or 0)}"
            )
        if policy == THREAD_POLICY_EPIC and epic is not None:
            return f"{agent_role}:epic:{epic.epic_key}"
        if policy == THREAD_POLICY_PROJECT and project is not None:
            return f"{agent_role}:project:{project.slug}"
        return None

    async def _get_or_create_session(
        self,
        *,
        thread_key: str,
        agent_role: str,
        policy: str,
        task: Task | None,
        epic: Epic | None,
        project: Project | None,
    ) -> AgentThreadSession:
        session = await self._get_session_by_key(thread_key)
        if session is not None:
            return session

        session = AgentThreadSession(
            id=uuid.uuid4(),
            thread_key=thread_key,
            agent_role=agent_role,
            thread_policy=policy,
            project_id=getattr(project, "id", None),
            epic_id=getattr(epic, "id", None),
            task_id=getattr(task, "id", None),
            status="active",
            dispatch_count=0,
            session_metadata={"history": []},
            started_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def _get_session_by_key(self, thread_key: str) -> AgentThreadSession | None:
        result = await self.db.execute(
            select(AgentThreadSession).where(AgentThreadSession.thread_key == thread_key)
        )
        return result.scalar_one_or_none()

    def _session_history(self, session: AgentThreadSession | None) -> list[dict[str, Any]]:
        if session is None:
            return []
        metadata = dict(session.session_metadata or {})
        history = metadata.get("history")
        return history if isinstance(history, list) else []

    def _build_summary(self, history: list[dict[str, Any]]) -> str | None:
        if not history:
            return None
        parts: list[str] = []
        for item in history[-3:]:
            excerpt = str(item.get("content_excerpt") or "").strip()
            status = str(item.get("status") or "unknown")
            label = str(item.get("prompt_type") or "dispatch")
            text = f"{label}/{status}"
            if excerpt:
                text += f": {excerpt}"
            parts.append(text)
        return " | ".join(parts)[:1000]

    def _render_prompt_block(
        self,
        *,
        policy: str,
        scope_label: str,
        thread_key: str | None,
        history: list[dict[str, Any]],
    ) -> str:
        lines = [
            "## Thread-Policy",
            f"- Modell: `{policy}`",
            f"- Scope: `{scope_label}`",
        ]
        if policy == THREAD_POLICY_STATELESS:
            lines.append("- Verhalten: Frischer Lauf. Verwende nur den aktuellen Prompt- und Shared-Context.")
            return "\n".join(lines)

        if thread_key:
            lines.append(f"- Thread-Key: `{thread_key}`")

        if policy == THREAD_POLICY_ATTEMPT:
            lines.append("- Resume-Regel: Neuer QA-Reentry erzeugt einen neuen Attempt-Thread.")

        if history:
            lines.append("- Vorherige Session-Hinweise:")
            for item in history[-3:]:
                excerpt = str(item.get("content_excerpt") or "").strip()
                if not excerpt:
                    excerpt = str(item.get("status") or "ohne Ergebnis")
                lines.append(
                    f"  - {item.get('prompt_type') or 'dispatch'}: {excerpt}"
                )
        else:
            lines.append("- Session-Historie: Noch kein frueherer Lauf in diesem Thread.")

        return "\n".join(lines)
