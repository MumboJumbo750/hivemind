"""YouTrack outbound sync service for task state and assignee updates."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import or_, select

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.sync import SyncOutbox
from app.models.task import Task
from app.models.user import User
from app.services.sync_errors import PermanentSyncError

logger = logging.getLogger(__name__)

DEFAULT_STATE_MAPPING: dict[str, str] = {
    "incoming": "Open",
    "scoped": "Open",
    "ready": "Open",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "done": "Resolved",
    "blocked": "Blocked",
    "cancelled": "Won't fix",
}


class YouTrackSyncService:
    """Sync Hivemind task updates to YouTrack issues."""

    def __init__(self, timeout: float = 10.0) -> None:
        self.base_url = settings.hivemind_youtrack_url.rstrip("/")
        self.token = settings.hivemind_youtrack_token
        self.timeout = timeout
        self.state_mapping = self._load_state_mapping(settings.hivemind_youtrack_state_mapping)

    async def process_outbound(self, outbox_entry: SyncOutbox) -> None:
        """Dispatch state + assignee sync for one outbound outbox entry."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            await asyncio.gather(
                self.sync_task_state(outbox_entry, client),
                self.sync_assignee(outbox_entry, client),
            )

    async def process_inbound(self, payload: dict[str, Any]) -> None:
        """Placeholder for inbound YouTrack handling (implemented in later tasks)."""
        _ = payload

    async def sync_task_state(self, outbox_entry: SyncOutbox, client: httpx.AsyncClient) -> None:
        """Sync task state to the mapped YouTrack state field."""
        external_id = self._resolve_external_id(outbox_entry)
        state = await self._resolve_state(outbox_entry)
        if not state:
            return

        mapped_state = self.state_mapping.get(state, state)
        payload = {
            "customFields": [
                {
                    "name": "State",
                    "value": {"name": mapped_state},
                }
            ]
        }
        await self._patch_issue(external_id, payload, client)

    async def sync_assignee(self, outbox_entry: SyncOutbox, client: httpx.AsyncClient) -> None:
        """Sync task assignee to YouTrack Assignee field when available."""
        external_id = self._resolve_external_id(outbox_entry)
        assignee_login = await self._resolve_assignee_login(outbox_entry)
        if not assignee_login:
            return

        payload = {
            "customFields": [
                {
                    "name": "Assignee",
                    "value": {"login": assignee_login},
                }
            ]
        }
        await self._patch_issue(external_id, payload, client)

    async def _patch_issue(
        self,
        external_id: str,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> None:
        if not self.base_url:
            raise RuntimeError("HIVEMIND_YOUTRACK_URL is not configured")
        if not self.token:
            raise RuntimeError("HIVEMIND_YOUTRACK_TOKEN is not configured")

        response = await client.patch(
            f"{self.base_url}/api/issues/{external_id}",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            params={"fields": "id,idReadable,customFields(name,value(name,login))"},
        )

        if 200 <= response.status_code < 300:
            return

        error = (
            f"YouTrack sync failed for issue {external_id} "
            f"(HTTP {response.status_code}): {response.text[:300]}"
        )
        if 400 <= response.status_code < 500:
            logger.warning(error)
            raise PermanentSyncError(error)

        raise RuntimeError(error)

    async def _resolve_state(self, outbox_entry: SyncOutbox) -> str | None:
        payload = dict(outbox_entry.payload or {})
        state = payload.get("state")
        if isinstance(state, str) and state:
            return state

        task = await self._fetch_task(outbox_entry)
        if task and task.state:
            return task.state
        return None

    async def _resolve_assignee_login(self, outbox_entry: SyncOutbox) -> str | None:
        payload = dict(outbox_entry.payload or {})
        for key in ("assignee_login", "assigned_to_username", "assigned_to_login"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value

        assigned_to = payload.get("assigned_to")
        if isinstance(assigned_to, str) and assigned_to:
            if not _is_uuid(assigned_to):
                return assigned_to
            login = await self._lookup_user_login(uuid.UUID(assigned_to))
            if login:
                return login

        task = await self._fetch_task(outbox_entry)
        if not task or not task.assigned_to:
            return None
        return await self._lookup_user_login(task.assigned_to)

    async def _lookup_user_login(self, user_id: uuid.UUID) -> str | None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                return None
            return user.username or user.email

    async def _fetch_task(self, outbox_entry: SyncOutbox) -> Task | None:
        payload = dict(outbox_entry.payload or {})
        candidates = [
            payload.get("task_id"),
            payload.get("task_key"),
            payload.get("external_id"),
            outbox_entry.entity_id,
        ]

        uuid_candidates: list[uuid.UUID] = []
        str_candidates: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate:
                continue
            if _is_uuid(candidate):
                uuid_candidates.append(uuid.UUID(candidate))
            str_candidates.append(candidate)

        async with AsyncSessionLocal() as db:
            if uuid_candidates:
                result = await db.execute(select(Task).where(Task.id.in_(uuid_candidates)))
                task = result.scalars().first()
                if task:
                    return task

            if str_candidates:
                result = await db.execute(
                    select(Task).where(
                        or_(
                            Task.task_key.in_(str_candidates),
                            Task.external_id.in_(str_candidates),
                        )
                    )
                )
                return result.scalars().first()

        return None

    def _resolve_external_id(self, outbox_entry: SyncOutbox) -> str:
        payload = dict(outbox_entry.payload or {})
        external_id = payload.get("external_id") or payload.get("youtrack_issue_id") or outbox_entry.entity_id
        if not external_id:
            raise PermanentSyncError("Missing YouTrack external id in outbound payload")
        return str(external_id)

    @staticmethod
    def _load_state_mapping(raw_mapping: str) -> dict[str, str]:
        mapping = dict(DEFAULT_STATE_MAPPING)
        if not raw_mapping:
            return mapping

        try:
            decoded = json.loads(raw_mapping)
        except json.JSONDecodeError:
            logger.warning("Invalid HIVEMIND_YOUTRACK_STATE_MAPPING, using defaults")
            return mapping

        if not isinstance(decoded, dict):
            logger.warning("HIVEMIND_YOUTRACK_STATE_MAPPING is not an object, using defaults")
            return mapping

        for key, value in decoded.items():
            if isinstance(key, str) and isinstance(value, str):
                mapping[key] = value
        return mapping


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
