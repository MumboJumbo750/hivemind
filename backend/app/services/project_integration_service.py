from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_integration import ProjectIntegration
from app.services.project_service import ProjectService

IntegrationProvider = Literal["youtrack", "sentry", "in_app", "github_projects"]
IntegrationStatus = Literal["active", "incomplete", "error", "disabled"]

PING_TIMEOUT_SECONDS = 4.0


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _unique_candidates(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


class ProjectIntegrationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.project_service = ProjectService(db)

    async def list_for_project(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        await self.project_service.get(project_id)
        result = await self.db.execute(
            select(ProjectIntegration)
            .where(ProjectIntegration.project_id == project_id)
            .order_by(ProjectIntegration.integration_type.asc(), ProjectIntegration.created_at.asc())
        )
        return [self._serialize(item) for item in result.scalars().all()]

    async def create(self, project_id: uuid.UUID, data: Any) -> dict[str, Any]:
        await self.project_service.get(project_id)
        integration = ProjectIntegration(project_id=project_id, integration_type=data.provider)
        self._apply_fields(integration, data, is_create=True)
        self.db.add(integration)
        await self.db.flush()
        await self.db.refresh(integration)
        return self._serialize(integration)

    async def update(self, project_id: uuid.UUID, integration_id: uuid.UUID, data: Any) -> dict[str, Any]:
        integration = await self._get_integration(project_id, integration_id)
        self._apply_fields(integration, data, is_create=False)
        await self.db.flush()
        await self.db.refresh(integration)
        return self._serialize(integration)

    async def check(self, project_id: uuid.UUID, integration_id: uuid.UUID) -> dict[str, Any]:
        integration = await self._get_integration(project_id, integration_id)
        checked_at = datetime.now(UTC)
        status_value, detail = self._configuration_status(integration)

        if status_value == "active" and integration.integration_type == "youtrack":
            status_value, detail = await self._check_youtrack(integration)
        elif status_value == "active" and integration.integration_type == "sentry":
            status_value, detail = await self._check_sentry(integration)

        integration.last_health_state = status_value
        integration.last_health_detail = detail
        integration.health_checked_at = checked_at
        await self.db.flush()
        await self.db.refresh(integration)
        return self._serialize(integration)

    async def resolve_inbound_target(
        self,
        *,
        provider: str,
        normalized_payload: dict[str, Any],
        raw_payload: dict[str, Any],
        explicit_project_id: str | None = None,
        explicit_project_slug: str | None = None,
        explicit_integration_key: str | None = None,
    ) -> dict[str, Any]:
        project: Project | None = None
        matched_by = "none"

        if explicit_integration_key:
            result = await self.db.execute(
                select(ProjectIntegration).where(
                    ProjectIntegration.integration_key == explicit_integration_key,
                    ProjectIntegration.integration_type == provider,
                )
            )
            integration = result.scalar_one_or_none()
            if integration:
                project = await self.project_service.get(integration.project_id)
                return self._resolved_target(project, integration, matched_by="integration_key")

        if explicit_project_id:
            try:
                project = await self.project_service.get(uuid.UUID(explicit_project_id))
                matched_by = "project_id"
            except (ValueError, HTTPException):
                project = None

        if project is None and explicit_project_slug:
            result = await self.db.execute(select(Project).where(Project.slug == explicit_project_slug))
            project = result.scalar_one_or_none()
            if project:
                matched_by = "project_slug"

        if project is not None:
            integration = await self._find_project_provider_integration(project.id, provider)
            if integration:
                return self._resolved_target(project, integration, matched_by=matched_by)
            return self._unresolved_target(
                reason=f"project matched via {matched_by}, but no {provider} integration is configured"
            )

        integration = await self._match_provider_integration(provider, normalized_payload, raw_payload)
        if integration is None:
            return self._unresolved_target(reason=f"no {provider} integration matched payload selectors")

        project = await self.project_service.get(integration.project_id)
        return self._resolved_target(project, integration, matched_by="selector")

    async def mark_inbound_accepted(self, integration_id: uuid.UUID | None, *, detail: str | None = None) -> None:
        if integration_id is None:
            return
        integration = await self.db.get(ProjectIntegration, integration_id)
        if integration is None:
            return
        integration.last_event_at = datetime.now(UTC)
        integration.last_error_at = None
        integration.last_error_detail = None
        if detail:
            integration.last_health_detail = detail
        await self.db.flush()

    async def mark_inbound_error(self, integration_id: uuid.UUID | None, *, detail: str) -> None:
        if integration_id is None:
            return
        integration = await self.db.get(ProjectIntegration, integration_id)
        if integration is None:
            return
        integration.last_error_at = datetime.now(UTC)
        integration.last_error_detail = detail
        integration.last_health_state = "error"
        integration.last_health_detail = detail
        await self.db.flush()

    async def _get_integration(self, project_id: uuid.UUID, integration_id: uuid.UUID) -> ProjectIntegration:
        result = await self.db.execute(
            select(ProjectIntegration).where(
                ProjectIntegration.id == integration_id,
                ProjectIntegration.project_id == project_id,
            )
        )
        integration = result.scalar_one_or_none()
        if integration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration nicht gefunden.")
        return integration

    async def _find_project_provider_integration(
        self,
        project_id: uuid.UUID,
        provider: str,
    ) -> ProjectIntegration | None:
        result = await self.db.execute(
            select(ProjectIntegration)
            .where(
                ProjectIntegration.project_id == project_id,
                ProjectIntegration.integration_type == provider,
                ProjectIntegration.sync_enabled == True,
            )
            .order_by(ProjectIntegration.created_at.asc())
        )
        return result.scalars().first()

    async def _match_provider_integration(
        self,
        provider: str,
        normalized_payload: dict[str, Any],
        raw_payload: dict[str, Any],
    ) -> ProjectIntegration | None:
        result = await self.db.execute(
            select(ProjectIntegration)
            .where(
                ProjectIntegration.integration_type == provider,
                ProjectIntegration.sync_enabled == True,
            )
            .order_by(ProjectIntegration.created_at.asc())
        )
        integrations = list(result.scalars().all())
        for integration in integrations:
            if self._matches_selector(integration, provider, normalized_payload, raw_payload):
                return integration
        return None

    def _matches_selector(
        self,
        integration: ProjectIntegration,
        provider: str,
        normalized_payload: dict[str, Any],
        raw_payload: dict[str, Any],
    ) -> bool:
        selector = integration.project_selector or {}
        if provider == "sentry":
            raw_project = raw_payload.get("project")
            candidates = _unique_candidates(
                [
                    normalized_payload.get("project"),
                    raw_project.get("slug") if isinstance(raw_project, dict) else raw_project,
                    raw_project.get("name") if isinstance(raw_project, dict) else None,
                ]
            )
        elif provider == "youtrack":
            issue = raw_payload.get("issue") or {}
            project = issue.get("project") or {}
            candidates = _unique_candidates(
                [
                    normalized_payload.get("project_key"),
                    normalized_payload.get("project_name"),
                    project.get("id"),
                    project.get("shortName"),
                    project.get("name"),
                ]
            )
        else:
            candidates = _unique_candidates([normalized_payload.get("project"), normalized_payload.get("external_id")])

        expected = _unique_candidates(
            [
                integration.external_project_key,
                selector.get("project"),
                selector.get("project_id"),
                selector.get("project_key"),
                selector.get("project_slug"),
                selector.get("project_name"),
                *(selector.get("aliases") or []),
            ]
        )
        if not expected:
            return False
        return any(candidate in expected for candidate in candidates)

    def _apply_fields(self, integration: ProjectIntegration, data: Any, *, is_create: bool) -> None:
        fields_set = getattr(data, "model_fields_set", set())
        if is_create or "display_name" in fields_set:
            integration.display_name = data.display_name
        if is_create or "integration_key" in fields_set:
            integration.integration_key = data.integration_key
        if is_create or "base_url" in fields_set:
            integration.base_url = data.base_url
        if is_create or "external_project_key" in fields_set:
            integration.external_project_key = data.external_project_key
        if is_create or "project_selector" in fields_set:
            integration.project_selector = data.project_selector
        if is_create or "status_mapping" in fields_set:
            integration.status_mapping = data.status_mapping
        if is_create or "routing_hints" in fields_set:
            integration.routing_hints = data.routing_hints
        if is_create or "config" in fields_set:
            integration.config = data.config
        if is_create or "webhook_secret" in fields_set:
            integration.webhook_secret = data.webhook_secret
        if is_create or "access_token" in fields_set:
            integration.access_token = data.access_token
        if is_create or "sync_enabled" in fields_set:
            integration.sync_enabled = data.sync_enabled
        if is_create or "sync_direction" in fields_set:
            integration.sync_direction = data.sync_direction
        if is_create or "github_repo" in fields_set:
            integration.github_repo = data.github_repo
        if is_create or "github_project_id" in fields_set:
            integration.github_project_id = data.github_project_id
        if is_create or "status_field_id" in fields_set:
            integration.status_field_id = data.status_field_id
        if is_create or "priority_field_id" in fields_set:
            integration.priority_field_id = data.priority_field_id
        integration.updated_at = datetime.utcnow()

    def _serialize(self, integration: ProjectIntegration) -> dict[str, Any]:
        status_value, detail = self._configuration_status(integration)
        if integration.last_health_state == "error":
            status_value = "error"
            detail = integration.last_health_detail or integration.last_error_detail or detail
        return {
            "id": str(integration.id),
            "project_id": str(integration.project_id),
            "provider": integration.integration_type,
            "display_name": integration.display_name,
            "integration_key": integration.integration_key,
            "base_url": integration.base_url,
            "external_project_key": integration.external_project_key,
            "project_selector": integration.project_selector,
            "status_mapping": integration.status_mapping,
            "routing_hints": integration.routing_hints,
            "config": integration.config,
            "sync_enabled": integration.sync_enabled,
            "sync_direction": integration.sync_direction,
            "github_repo": integration.github_repo,
            "github_project_id": integration.github_project_id,
            "status_field_id": integration.status_field_id,
            "priority_field_id": integration.priority_field_id,
            "has_webhook_secret": bool(integration.webhook_secret),
            "has_access_token": bool(integration.access_token),
            "status": status_value,
            "status_detail": detail,
            "last_health_state": integration.last_health_state,
            "last_health_detail": integration.last_health_detail,
            "health_checked_at": integration.health_checked_at,
            "last_event_at": integration.last_event_at,
            "last_error_at": integration.last_error_at,
            "last_error_detail": integration.last_error_detail,
            "created_at": integration.created_at,
            "updated_at": integration.updated_at,
        }

    def _configuration_status(self, integration: ProjectIntegration) -> tuple[IntegrationStatus, str]:
        if not integration.sync_enabled:
            return "disabled", "Synchronisierung ist deaktiviert"

        provider = integration.integration_type
        missing: list[str] = []
        if provider == "youtrack":
            if not integration.base_url:
                missing.append("base_url")
            if not integration.access_token:
                missing.append("access_token")
            if not integration.external_project_key and not (integration.project_selector or {}).get("aliases"):
                missing.append("external_project_key")
        elif provider == "sentry":
            if not integration.external_project_key and not (integration.project_selector or {}).get("aliases"):
                missing.append("external_project_key")
        elif provider == "github_projects":
            if not integration.github_repo:
                missing.append("github_repo")
            if not integration.github_project_id:
                missing.append("github_project_id")

        if missing:
            return "incomplete", f"Fehlende Felder: {', '.join(missing)}"
        return "active", "Konfiguration vollständig"

    async def _check_youtrack(self, integration: ProjectIntegration) -> tuple[IntegrationStatus, str]:
        url = f"{str(integration.base_url).rstrip('/')}/api/admin/projects?fields=id&$top=1"
        try:
            async with httpx.AsyncClient(timeout=PING_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {integration.access_token}",
                        "Accept": "application/json",
                    },
                )
            if 200 <= response.status_code < 300:
                return "active", "YouTrack erreichbar"
            return "error", f"YouTrack HTTP {response.status_code}"
        except Exception as exc:
            return "error", str(exc)

    async def _check_sentry(self, integration: ProjectIntegration) -> tuple[IntegrationStatus, str]:
        if not integration.base_url or not integration.access_token:
            return "incomplete", "Sentry-Healthcheck braucht base_url und access_token"
        url = f"{str(integration.base_url).rstrip('/')}/api/0/"
        try:
            async with httpx.AsyncClient(timeout=PING_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {integration.access_token}",
                        "Accept": "application/json",
                    },
                )
            if 200 <= response.status_code < 300:
                return "active", "Sentry erreichbar"
            return "error", f"Sentry HTTP {response.status_code}"
        except Exception as exc:
            return "error", str(exc)

    def _resolved_target(
        self,
        project: Project,
        integration: ProjectIntegration,
        *,
        matched_by: str,
    ) -> dict[str, Any]:
        return {
            "matched": True,
            "project_id": str(project.id),
            "project_slug": project.slug,
            "integration_id": str(integration.id),
            "integration_key": integration.integration_key,
            "matched_by": matched_by,
            "reason": None,
        }

    def _unresolved_target(self, *, reason: str) -> dict[str, Any]:
        return {
            "matched": False,
            "project_id": None,
            "project_slug": None,
            "integration_id": None,
            "integration_key": None,
            "matched_by": None,
            "reason": reason,
        }
