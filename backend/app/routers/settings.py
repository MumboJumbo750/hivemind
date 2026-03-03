"""Settings-API + Task-Assignment (TASK-2-009).

GET  /api/settings                       — aktuellen Modus + notification_mode lesen
PATCH /api/settings                      — Modus umschalten (solo | team)
GET  /api/settings/routing-threshold     — Routing-Threshold lesen (TASK-7-007)
PATCH /api/settings/routing-threshold    — Routing-Threshold setzen (TASK-7-007)
GET  /api/settings/routing_threshold     — Alias (DoD/compat)
PATCH /api/settings/routing_threshold    — Alias (DoD/compat)

GET  /api/settings/ai-providers          — list all AI provider configs (TASK-8-002)
PUT  /api/settings/ai-providers/{role}   — create/update AI provider config (TASK-8-002)
DELETE /api/settings/ai-providers/{role} — delete AI provider config (TASK-8-002)
POST /api/settings/ai-providers/{role}/test — test provider connectivity (TASK-8-002)

GET  /api/settings/governance            — get governance config (TASK-8-006)
PUT  /api/settings/governance            — update governance config (TASK-8-006)
"""
from datetime import UTC, datetime
from typing import Literal, Optional
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import has_routing_threshold_env_override, settings
from app.db import get_db
from app.models.settings import AppSettings
from app.routers.deps import get_current_actor, require_role
from app.schemas.auth import CurrentActor
from app.schemas.ai_provider import AIProviderConfigIn, AIProviderConfigOut
from app.schemas.ai_credential import AICredentialCreate, AICredentialUpdate, AICredentialOut
from app.schemas.governance import GovernanceConfig
from app.services.audit import write_audit

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    mode: str
    notification_mode: str


class SettingsUpdate(BaseModel):
    mode: Literal["solo", "team"]


async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(AppSettings).where(AppSettings.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


@router.get("", response_model=SettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> SettingsResponse:
    mode = await _get_setting(db, "hivemind_mode", "solo")
    notification_mode = await _get_setting(db, "notification_mode", "client")
    return SettingsResponse(mode=mode, notification_mode=notification_mode)


@router.patch("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> SettingsResponse:
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "hivemind_mode")
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = body.mode
        row.updated_by = actor.id
    else:
        db.add(AppSettings(key="hivemind_mode", value=body.mode, updated_by=actor.id))

    await db.flush()
    # _get_app_mode in deps.py liest bei jedem Request frisch aus der DB → kein Cache nötig

    notification_mode = await _get_setting(db, "notification_mode", "client")
    return SettingsResponse(mode=body.mode, notification_mode=notification_mode)


# ── Routing-Threshold (TASK-7-007) ────────────────────────────────────────────

class RoutingThresholdResponse(BaseModel):
    current_value: float
    source: Literal["env", "db"]
    last_updated: Optional[datetime] = None
    updated_by: Optional[str] = None


class RoutingThresholdUpdate(BaseModel):
    value: float = Field(..., ge=0.0, le=1.0, description="Threshold between 0.0 and 1.0")


@router.get("/routing-threshold", response_model=RoutingThresholdResponse)
@router.get("/routing_threshold", response_model=RoutingThresholdResponse, include_in_schema=False)
async def get_routing_threshold(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> RoutingThresholdResponse:
    del actor
    # If env var is explicitly set, report env source (even if value equals default).
    if has_routing_threshold_env_override():
        return RoutingThresholdResponse(
            current_value=settings.hivemind_routing_threshold,
            source="env",
        )

    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "routing_threshold")
    )
    row = result.scalar_one_or_none()
    if row:
        try:
            value = float(row.value)
        except (ValueError, TypeError):
            value = 0.85
        return RoutingThresholdResponse(
            current_value=value,
            source="db",
            last_updated=row.updated_at,
            updated_by=str(row.updated_by) if row.updated_by else None,
        )

    return RoutingThresholdResponse(current_value=0.85, source="db")


@router.patch("/routing-threshold", response_model=RoutingThresholdResponse)
@router.patch("/routing_threshold", response_model=RoutingThresholdResponse, include_in_schema=False)
async def update_routing_threshold(
    body: RoutingThresholdUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> RoutingThresholdResponse:
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "routing_threshold")
    )
    row = result.scalar_one_or_none()
    new_value_str = str(body.value)

    if row:
        row.value = new_value_str
        row.updated_by = actor.id
        row.updated_at = datetime.now(UTC)
    else:
        db.add(
            AppSettings(
                key="routing_threshold",
                value=new_value_str,
                updated_by=actor.id,
                updated_at=datetime.now(UTC),
            )
        )

    await db.flush()

    await write_audit(
        tool_name="update_routing_threshold",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload={"new_value": body.value},
    )

    # Invalidate the in-memory cache in routing_service
    from app.services.routing_service import invalidate_threshold_cache
    invalidate_threshold_cache()

    result2 = await db.execute(
        select(AppSettings).where(AppSettings.key == "routing_threshold")
    )
    updated = result2.scalar_one_or_none()
    return RoutingThresholdResponse(
        current_value=body.value,
        source="db",
        last_updated=updated.updated_at if updated else None,
        updated_by=str(actor.id),
    )


# ── AI Provider Config (TASK-8-002) ───────────────────────────────────────────

@router.get("/ai-providers/models")
async def list_provider_models(
    provider: str,
    api_key: str = "",
    endpoint: str = "",
    credential_id: str = "",
    agent_role: str = "",
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> list[dict]:
    """List available models for a given provider type.

    Key resolution order:
    1. Explicit api_key query param (e.g. user pasted inline key)
    2. credential_id → decrypt from ai_credentials table
    3. agent_role → look up existing provider config's key/credential
    4. Fall back to well-known defaults
    """
    from app.services.ai_provider import list_models_for_provider, decrypt_api_key

    resolved_key = api_key

    # Try credential_id
    if not resolved_key and credential_id:
        from app.models.ai_credential import AICredential
        cred = await db.get(AICredential, _uuid.UUID(credential_id))
        if cred and cred.api_key_encrypted and settings.hivemind_key_passphrase:
            resolved_key = decrypt_api_key(cred.api_key_encrypted, cred.api_key_nonce, settings.hivemind_key_passphrase)

    # Try existing provider config for role
    if not resolved_key and agent_role:
        from app.models.ai_provider import AIProviderConfig
        result = await db.execute(
            select(AIProviderConfig).where(AIProviderConfig.agent_role == agent_role)
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            if cfg.credential and cfg.credential.api_key_encrypted and settings.hivemind_key_passphrase:
                resolved_key = decrypt_api_key(cfg.credential.api_key_encrypted, cfg.credential.api_key_nonce, settings.hivemind_key_passphrase)
            elif cfg.api_key_encrypted and settings.hivemind_key_passphrase:
                resolved_key = decrypt_api_key(cfg.api_key_encrypted, cfg.api_key_nonce, settings.hivemind_key_passphrase)
            if not endpoint and cfg.endpoint:
                endpoint = cfg.endpoint

    return await list_models_for_provider(provider, api_key=resolved_key, endpoint=endpoint)


@router.get("/ai-providers", response_model=list[AIProviderConfigOut])
async def list_ai_providers(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> list[AIProviderConfigOut]:
    """List all AI provider configurations."""
    from app.models.ai_provider import AIProviderConfig
    result = await db.execute(select(AIProviderConfig))
    configs = result.scalars().all()
    return [
        AIProviderConfigOut(
            agent_role=c.agent_role,
            provider=c.provider,
            model=c.model,
            endpoint=c.endpoint,
            rpm_limit=c.rpm_limit,
            tpm_limit=c.tpm_limit,
            token_budget_daily=c.token_budget_daily,
            enabled=c.enabled,
            has_api_key=bool(c.api_key_encrypted),
            credential_id=str(c.credential_id) if c.credential_id else None,
            credential_name=c.credential.name if c.credential else None,
        )
        for c in configs
    ]


@router.put("/ai-providers/{agent_role}", response_model=AIProviderConfigOut)
async def upsert_ai_provider(
    agent_role: str,
    body: AIProviderConfigIn,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> AIProviderConfigOut:
    """Create or update AI provider config for an agent role."""
    from app.models.ai_provider import AIProviderConfig
    from app.services.ai_provider import encrypt_api_key
    import uuid as _uuid

    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.agent_role == agent_role)
    )
    config = result.scalar_one_or_none()

    # Encrypt API key if provided (inline key)
    api_key_encrypted = None
    api_key_nonce = None
    if body.api_key and settings.hivemind_key_passphrase:
        api_key_encrypted, api_key_nonce = encrypt_api_key(body.api_key, settings.hivemind_key_passphrase)
    elif body.api_key and not settings.hivemind_key_passphrase:
        raise HTTPException(
            status_code=400,
            detail="HIVEMIND_KEY_PASSPHRASE must be set to store encrypted API keys",
        )

    # Resolve credential_id
    cred_id = _uuid.UUID(body.credential_id) if body.credential_id else None

    if config is None:
        config = AIProviderConfig(
            agent_role=agent_role,
            provider=body.provider,
            model=body.model,
            endpoint=body.endpoint,
            credential_id=cred_id,
            rpm_limit=body.rpm_limit,
            tpm_limit=body.tpm_limit,
            token_budget_daily=body.token_budget_daily,
            enabled=body.enabled,
        )
        if api_key_encrypted is not None:
            config.api_key_encrypted = api_key_encrypted
            config.api_key_nonce = api_key_nonce
        db.add(config)
    else:
        config.provider = body.provider
        config.model = body.model
        config.endpoint = body.endpoint
        config.credential_id = cred_id
        config.rpm_limit = body.rpm_limit
        config.tpm_limit = body.tpm_limit
        config.token_budget_daily = body.token_budget_daily
        config.enabled = body.enabled
        config.updated_at = datetime.now(UTC)
        if api_key_encrypted is not None:
            config.api_key_encrypted = api_key_encrypted
            config.api_key_nonce = api_key_nonce
        # If credential_id set and inline key provided, clear inline key
        # (credential takes precedence — but allow override)

    await db.commit()
    await db.refresh(config)

    return AIProviderConfigOut(
        agent_role=config.agent_role,
        provider=config.provider,
        model=config.model,
        endpoint=config.endpoint,
        rpm_limit=config.rpm_limit,
        tpm_limit=config.tpm_limit,
        token_budget_daily=config.token_budget_daily,
        enabled=config.enabled,
        has_api_key=bool(config.api_key_encrypted),
        credential_id=str(config.credential_id) if config.credential_id else None,
        credential_name=config.credential.name if config.credential else None,
    )


@router.delete("/ai-providers/{agent_role}", status_code=204)
async def delete_ai_provider(
    agent_role: str,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> None:
    """Delete AI provider config for an agent role."""
    from app.models.ai_provider import AIProviderConfig

    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.agent_role == agent_role)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="AI provider config not found")
    await db.delete(config)
    await db.commit()


@router.post("/ai-providers/{agent_role}/test")
async def test_ai_provider(
    agent_role: str,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> dict:
    """Test connectivity for the configured AI provider of an agent role."""
    from app.services.ai_provider import NeedsManualMode, get_provider

    try:
        provider = await get_provider(agent_role, db)
    except NeedsManualMode as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        healthy = await provider.health_check()
        if not healthy:
            return {"ok": False, "error": "Provider health check failed"}
        return {"ok": True, "provider": type(provider).__name__, "model": provider.default_model()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── AI Credentials (zentrale Key-Verwaltung) ──────────────────────────────────

@router.get("/credentials", response_model=list[AICredentialOut])
async def list_credentials(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> list[AICredentialOut]:
    """List all AI credentials."""
    from app.models.ai_credential import AICredential
    from app.models.ai_provider import AIProviderConfig
    from sqlalchemy import func

    # Subquery: count how many provider configs reference each credential
    usage_sq = (
        select(
            AIProviderConfig.credential_id,
            func.count().label("cnt"),
        )
        .where(AIProviderConfig.credential_id.isnot(None))
        .group_by(AIProviderConfig.credential_id)
        .subquery()
    )

    result = await db.execute(
        select(AICredential, func.coalesce(usage_sq.c.cnt, 0).label("usage_count"))
        .outerjoin(usage_sq, AICredential.id == usage_sq.c.credential_id)
    )
    rows = result.all()
    return [
        AICredentialOut(
            id=str(cred.id),
            name=cred.name,
            provider_type=cred.provider_type,
            endpoint=cred.endpoint,
            note=cred.note,
            has_api_key=bool(cred.api_key_encrypted),
            usage_count=usage_count,
        )
        for cred, usage_count in rows
    ]


@router.post("/credentials", response_model=AICredentialOut, status_code=201)
async def create_credential(
    body: AICredentialCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> AICredentialOut:
    """Create a new AI credential."""
    from app.models.ai_credential import AICredential
    from app.services.ai_provider import encrypt_api_key

    api_key_encrypted = None
    api_key_nonce = None
    if body.api_key and settings.hivemind_key_passphrase:
        api_key_encrypted, api_key_nonce = encrypt_api_key(body.api_key, settings.hivemind_key_passphrase)
    elif body.api_key and not settings.hivemind_key_passphrase:
        raise HTTPException(
            status_code=400,
            detail="HIVEMIND_KEY_PASSPHRASE must be set to store encrypted API keys",
        )

    cred = AICredential(
        name=body.name,
        provider_type=body.provider_type,
        api_key_encrypted=api_key_encrypted,
        api_key_nonce=api_key_nonce,
        endpoint=body.endpoint,
        note=body.note,
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)

    return AICredentialOut(
        id=str(cred.id),
        name=cred.name,
        provider_type=cred.provider_type,
        endpoint=cred.endpoint,
        note=cred.note,
        has_api_key=bool(cred.api_key_encrypted),
        usage_count=0,
    )


@router.put("/credentials/{credential_id}", response_model=AICredentialOut)
async def update_credential(
    credential_id: str,
    body: AICredentialUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> AICredentialOut:
    """Update an existing AI credential."""
    from app.models.ai_credential import AICredential
    from app.models.ai_provider import AIProviderConfig
    from app.services.ai_provider import encrypt_api_key
    from sqlalchemy import func
    import uuid as _uuid

    result = await db.execute(
        select(AICredential).where(AICredential.id == _uuid.UUID(credential_id))
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=404, detail="Credential not found")

    if body.name is not None:
        cred.name = body.name
    if body.provider_type is not None:
        cred.provider_type = body.provider_type
    if body.endpoint is not None:
        cred.endpoint = body.endpoint
    if body.note is not None:
        cred.note = body.note
    if body.api_key is not None:
        if not settings.hivemind_key_passphrase:
            raise HTTPException(
                status_code=400,
                detail="HIVEMIND_KEY_PASSPHRASE must be set to store encrypted API keys",
            )
        cred.api_key_encrypted, cred.api_key_nonce = encrypt_api_key(
            body.api_key, settings.hivemind_key_passphrase
        )
    cred.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(cred)

    # Count usage
    usage_result = await db.execute(
        select(func.count()).where(AIProviderConfig.credential_id == cred.id)
    )
    usage_count = usage_result.scalar() or 0

    return AICredentialOut(
        id=str(cred.id),
        name=cred.name,
        provider_type=cred.provider_type,
        endpoint=cred.endpoint,
        note=cred.note,
        has_api_key=bool(cred.api_key_encrypted),
        usage_count=usage_count,
    )


@router.delete("/credentials/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: str,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> None:
    """Delete an AI credential. FK on provider configs is SET NULL."""
    from app.models.ai_credential import AICredential
    import uuid as _uuid

    result = await db.execute(
        select(AICredential).where(AICredential.id == _uuid.UUID(credential_id))
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    await db.delete(cred)
    await db.commit()


# ── Governance Levels (TASK-8-006) ────────────────────────────────────────────

@router.get("/governance", response_model=GovernanceConfig)
async def get_governance_config(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> GovernanceConfig:
    """Return the current governance configuration."""
    from app.services.governance import get_governance
    data = await get_governance(db)
    return GovernanceConfig(**data)


@router.put("/governance", response_model=GovernanceConfig)
async def update_governance_config(
    body: GovernanceConfig,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> GovernanceConfig:
    """Update the governance configuration (admin only)."""
    from app.services.governance import update_governance
    try:
        updated = await update_governance(db, body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return GovernanceConfig(**updated)
