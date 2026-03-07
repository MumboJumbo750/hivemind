"""AI Provider Service — Phase 8 (TASK-8-002 + TASK-8-003).

Routing:
  1. ai_provider_configs[agent_role]  (per-role DB config)
  2. app_settings.ai_provider         (global fallback key)
  3. HIVEMIND_AI_API_KEY env var       (env fallback)
  4. NeedsManualMode                   (BYOAI — Prompt Station)

Encryption: AES-256-GCM with HKDF-SHA256 from HIVEMIND_KEY_PASSPHRASE.

Rate-Limiting & Retry (TASK-8-003):
  - Exponential backoff: 1s → 2s → 4s → max 60s, max 3 attempts on 429/503
  - RPM token-bucket: min_interval = 60.0 / rpm_limit
  - Token-count calibration via HIVEMIND_TOKEN_COUNT_CALIBRATION env var
"""
import asyncio
import json
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


class NeedsManualMode(Exception):
    """Raised when no AI provider is configured — fall back to Prompt Station."""


class RateLimiter:
    """Per-role token-bucket rate limiter."""

    def __init__(self, rpm_limit: int):
        self.min_interval = 60.0 / rpm_limit if rpm_limit > 0 else 0.0
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


def _derive_aes_key(passphrase: str) -> bytes:
    """Derive AES-256 key from passphrase using HKDF-SHA256."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"hivemind-api-key-encryption",
        info=b"ai-provider-key",
    )
    return hkdf.derive(passphrase.encode())


def decrypt_api_key(encrypted: bytes, nonce: bytes, passphrase: str) -> str:
    """Decrypt an AES-256-GCM encrypted API key."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _derive_aes_key(passphrase)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, encrypted, None)
    return plaintext.decode()


def encrypt_api_key(plaintext: str, passphrase: str) -> tuple[bytes, bytes]:
    """Encrypt an API key with AES-256-GCM. Returns (ciphertext, nonce)."""
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _derive_aes_key(passphrase)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return ciphertext, nonce


def get_token_calibration() -> dict[str, float]:
    """Load token-count calibration factors from env var."""
    raw = settings.hivemind_token_count_calibration
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def calibrate_token_count(count: int, provider: str) -> int:
    """Apply calibration factor to a token count estimate."""
    factors = get_token_calibration()
    factor = factors.get(provider, 1.0)
    return int(count * factor)


_rate_limiters: dict[str, RateLimiter] = {}


def _get_rate_limiter(agent_role: str, rpm_limit: int) -> RateLimiter:
    key = f"{agent_role}:{rpm_limit}"
    if key not in _rate_limiters:
        _rate_limiters[key] = RateLimiter(rpm_limit)
    return _rate_limiters[key]


async def get_provider(agent_role: str, db: AsyncSession) -> Any:
    """Return configured AIProvider for the given agent_role.

    Routing chain:
    1. ai_provider_configs[agent_role]
    2. HIVEMIND_AI_API_KEY env var (global default → Anthropic)
    3. raise NeedsManualMode
    """
    from sqlalchemy import select
    from app.models.ai_provider import AIProviderConfig

    # 1. Per-role config from DB
    result = await db.execute(
        select(AIProviderConfig).where(
            AIProviderConfig.agent_role == agent_role,
            AIProviderConfig.enabled == True,
        )
    )
    config = result.scalar_one_or_none()

    if config:
        provider = _build_provider_from_config(config)
        setattr(provider, "_hivemind_rpm_limit", config.rpm_limit or settings.hivemind_ai_rpm_limit)
        setattr(provider, "_hivemind_token_budget_daily", config.token_budget_daily)
        return provider

    # 2. Global env-var fallback
    global_key = settings.hivemind_ai_api_key
    if global_key:
        from app.services.ai_providers.anthropic import AnthropicProvider
        provider = AnthropicProvider(api_key=global_key)
        setattr(provider, "_hivemind_rpm_limit", settings.hivemind_ai_rpm_limit)
        return provider

    # 3. No provider → BYOAI
    raise NeedsManualMode(f"No AI provider configured for role '{agent_role}'")


def _build_provider_from_config(config: Any) -> Any:
    """Build the concrete AIProvider from a DB config row.

    Key resolution order:
      1. Inline key (api_key_encrypted on the config itself)
      2. Linked credential (credential_id → ai_credentials.api_key_encrypted)
      3. Global env fallback (HIVEMIND_AI_API_KEY)
    """
    passphrase = settings.hivemind_key_passphrase
    api_key = ""

    # 1. Inline key
    if config.api_key_encrypted and config.api_key_nonce and passphrase:
        try:
            api_key = decrypt_api_key(config.api_key_encrypted, config.api_key_nonce, passphrase)
        except Exception as e:
            logger.error("Failed to decrypt inline API key for role %s: %s", config.agent_role, e)

    # 2. Linked credential (falls kein inline key)
    if not api_key and hasattr(config, "credential") and config.credential:
        cred = config.credential
        if cred.api_key_encrypted and cred.api_key_nonce and passphrase:
            try:
                api_key = decrypt_api_key(cred.api_key_encrypted, cred.api_key_nonce, passphrase)
            except Exception as e:
                logger.error("Failed to decrypt credential '%s' for role %s: %s", cred.name, config.agent_role, e)
        # Use credential's endpoint if config has none
        if not config.endpoint and cred.endpoint:
            config.endpoint = cred.endpoint

    # 3. Global env fallback
    if not api_key and not passphrase:
        global_key = settings.hivemind_ai_api_key
        if global_key:
            api_key = global_key

    provider = config.provider
    model = config.model
    endpoint = config.endpoint

    if provider == "anthropic":
        from app.services.ai_providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=api_key, default_model_name=model or "claude-sonnet-4-6")
    elif provider == "openai":
        from app.services.ai_providers.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=api_key, default_model_name=model or "gpt-4o")
    elif provider == "github_models":
        from app.services.ai_providers.github_models import GitHubModelsProvider
        return GitHubModelsProvider(
            github_token=api_key or settings.hivemind_github_token,
            default_model_name=model or "gpt-4o",
        )
    elif provider == "github_copilot":
        from app.services.ai_providers.github_copilot import GitHubCopilotProvider
        return GitHubCopilotProvider(
            github_token=api_key or settings.hivemind_github_token,
            default_model_name=model or "gpt-4o",
        )
    elif provider == "ollama":
        from app.services.ai_providers.ollama import OllamaProvider
        return OllamaProvider(
            base_url=endpoint or settings.hivemind_ollama_url,
            default_model_name=model or "llama3.1",
        )
    elif provider == "custom":
        from app.services.ai_providers.custom import CustomProvider
        return CustomProvider(api_key=api_key, base_url=endpoint or "", default_model_name=model or "default")
    else:
        raise ValueError(f"Unknown provider type: {provider}")


async def send_with_retry(
    provider: Any,
    prompt: str,
    tools: list[dict] | None = None,
    model: str | None = None,
    system: str | None = None,
    max_attempts: int = 3,
    agent_role: str = "default",
    rpm_limit: int = 0,
) -> Any:
    """Send prompt with exponential backoff retry (TASK-8-003).

    Retries on HTTP 429 and 503. Raises on other errors.
    """
    # Rate-limit before sending
    limiter = _get_rate_limiter(agent_role, rpm_limit or settings.hivemind_ai_rpm_limit)
    await limiter.acquire()

    delay = 1.0
    last_error = None
    for attempt in range(max_attempts):
        try:
            return await provider.send_prompt(prompt, tools, model, system)
        except Exception as e:
            # Check for rate-limit / server errors
            status = None
            if hasattr(e, "status_code"):
                status = e.status_code
            elif hasattr(e, "response") and hasattr(e.response, "status_code"):
                status = e.response.status_code

            if status in (429, 503) and attempt < max_attempts - 1:
                logger.warning(
                    "AI provider %s (attempt %d/%d), retrying in %.0fs",
                    status, attempt + 1, max_attempts, delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)
                last_error = e
                continue
            raise

    raise last_error


async def acquire_provider_capacity(agent_role: str, provider: Any) -> None:
    """Apply the effective per-role RPM limiter before a provider request."""
    rpm_limit = getattr(provider, "_hivemind_rpm_limit", settings.hivemind_ai_rpm_limit)
    limiter = _get_rate_limiter(agent_role, int(rpm_limit or 0))
    await limiter.acquire()


# ── Model Listing ─────────────────────────────────────────────────────────────

async def list_models_for_provider(
    provider_type: str,
    api_key: str = "",
    endpoint: str = "",
) -> list[dict]:
    """Fetch available models for a given provider type.

    Returns list of {"id": "model-name", "name": "display name", ...}.
    """
    if provider_type == "anthropic":
        return await _list_anthropic_models(api_key)
    elif provider_type == "openai":
        return await _list_openai_models(api_key)
    elif provider_type == "github_models":
        return await _list_github_models(api_key)
    elif provider_type == "github_copilot":
        return await _list_github_copilot_models(api_key)
    elif provider_type == "ollama":
        return await _list_ollama_models(endpoint)
    elif provider_type == "custom":
        return await _list_openai_compatible_models(api_key, endpoint)
    else:
        return []


async def _list_anthropic_models(api_key: str) -> list[dict]:
    """List models from Anthropic API or return known defaults."""
    if not api_key:
        # Return well-known Anthropic models
        return [
            {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6"},
            {"id": "claude-opus-4-6", "name": "Claude Opus 4.6"},
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
            {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku"},
        ]
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            return [{"id": m["id"], "name": m.get("display_name", m["id"])} for m in models]
    except Exception as e:
        logger.warning("Anthropic model listing failed (%s), using defaults", e)
        return [
            {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6"},
            {"id": "claude-opus-4-6", "name": "Claude Opus 4.6"},
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
            {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku"},
        ]


async def _list_openai_models(api_key: str) -> list[dict]:
    """List models from OpenAI API or return known defaults."""
    if not api_key:
        return [
            {"id": "gpt-4o", "name": "GPT-4o"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
            {"id": "gpt-4.1", "name": "GPT-4.1"},
            {"id": "o3-mini", "name": "o3-mini"},
        ]
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            # Filter to chat models only
            chat_models = [m for m in models if any(
                prefix in m["id"]
                for prefix in ("gpt-4", "gpt-3.5", "o1", "o3", "chatgpt")
            )]
            chat_models.sort(key=lambda m: m["id"])
            return [{"id": m["id"], "name": m["id"]} for m in chat_models]
    except Exception as e:
        logger.warning("OpenAI model listing failed (%s), using defaults", e)
        return [
            {"id": "gpt-4o", "name": "GPT-4o"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
            {"id": "gpt-4.1", "name": "GPT-4.1"},
            {"id": "o3-mini", "name": "o3-mini"},
        ]


async def _list_github_models(github_token: str) -> list[dict]:
    """List models from GitHub Models catalog."""
    from app.services.ai_providers.github_models import GitHubModelsProvider
    token = github_token or settings.hivemind_github_token
    if not token:
        return [
            {"id": "gpt-4o", "name": "GPT-4o"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
            {"id": "Mistral-large", "name": "Mistral Large"},
        ]
    raw = await GitHubModelsProvider.list_available_models(token)
    if isinstance(raw, list):
        return [{"id": m.get("id", m.get("name", "")), "name": m.get("friendly_name", m.get("name", m.get("id", "")))} for m in raw]
    return []


async def _list_github_copilot_models(github_token: str) -> list[dict]:
    """List models from GitHub Copilot API with premium multipliers.

    Multipliers are derived from `model_picker_category` — the same source
    VS Code uses.  GitHub Copilot pricing docs define:
      powerful   → 50×  premium requests
      versatile  → 1×   premium requests
      lightweight → 0.25× premium requests
    """
    from app.services.ai_providers.github_copilot import GitHubCopilotProvider
    token = github_token or settings.hivemind_github_token
    if not token:
        return [
            {"id": "gpt-4o", "name": "GPT-4o", "premium_multiplier": 1, "category": "versatile"},
            {"id": "gpt-4.1", "name": "GPT-4.1", "premium_multiplier": 1, "category": "versatile"},
            {"id": "claude-sonnet-4", "name": "Claude Sonnet 4", "premium_multiplier": 1, "category": "versatile"},
            {"id": "o3-mini", "name": "o3-mini", "premium_multiplier": 0.25, "category": "lightweight"},
        ]

    CATEGORY_MULTIPLIER: dict[str, float] = {
        "powerful": 50,
        "versatile": 1,
        "lightweight": 0.25,
    }

    raw = await GitHubCopilotProvider.list_available_models(token)
    if isinstance(raw, list):
        results = []
        for m in raw:
            # Skip models not meant for the picker (old versions, embeddings)
            if not m.get("model_picker_enabled", False):
                continue

            mid = m.get("id", m.get("name", ""))
            category = m.get("model_picker_category", "")
            multiplier = CATEGORY_MULTIPLIER.get(category, 1)

            # Extract context limits from capabilities
            caps = m.get("capabilities", {})
            limits = caps.get("limits", {})
            supports = caps.get("supports", {})

            results.append({
                "id": mid,
                "name": m.get("name", m.get("id", "")),
                "vendor": m.get("vendor", ""),
                "category": category,
                "premium_multiplier": multiplier,
                "max_context_tokens": limits.get("max_context_window_tokens"),
                "max_prompt_tokens": limits.get("max_prompt_tokens"),
                "max_output_tokens": limits.get("max_output_tokens"),
                "supports_vision": bool(limits.get("vision")),
                "supports_tool_calls": supports.get("tool_calls", False),
                "supports_streaming": supports.get("streaming", False),
            })
        # Sort: lightweight first, then versatile, then powerful
        cat_order = {"lightweight": 0, "versatile": 1, "powerful": 2, "": 3}
        results.sort(key=lambda x: (cat_order.get(x["category"], 3), x["name"]))
        return results
    return []


async def _list_ollama_models(endpoint: str) -> list[dict]:
    """List models from a local Ollama instance."""
    import httpx
    base = endpoint or settings.hivemind_ollama_url
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{base}/api/tags", timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            return [{"id": m["name"], "name": m["name"]} for m in models]
    except Exception as e:
        logger.warning("Ollama model listing failed (%s)", e)
        return []


async def _list_openai_compatible_models(api_key: str, endpoint: str) -> list[dict]:
    """List models from an OpenAI-compatible endpoint."""
    if not endpoint:
        return []
    import httpx
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient() as client:
            url = endpoint.rstrip("/") + "/models"
            resp = await client.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(models, list):
                return [{"id": m.get("id", m.get("name", "")), "name": m.get("id", m.get("name", ""))} for m in models]
            return []
    except Exception as e:
        logger.warning("Custom endpoint model listing failed (%s)", e)
        return []


# ── Credential CRUD (used by settings router) ─────────────────────────────────

async def list_credentials_with_usage(db: AsyncSession) -> list:
    """Return all AICredentials joined with their usage count in ai_provider_configs."""
    from sqlalchemy import func, select
    from app.models.ai_credential import AICredential
    from app.models.ai_provider import AIProviderConfig

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
    return result.all()


async def get_credential_by_id(db: AsyncSession, credential_id: Any) -> Any:
    """Return AICredential by UUID (string or UUID), or None."""
    import uuid as _uuid
    from sqlalchemy import select
    from app.models.ai_credential import AICredential

    if not isinstance(credential_id, _uuid.UUID):
        credential_id = _uuid.UUID(str(credential_id))
    result = await db.execute(
        select(AICredential).where(AICredential.id == credential_id)
    )
    return result.scalar_one_or_none()


async def create_credential_record(
    db: AsyncSession,
    *,
    name: str,
    provider_type: str,
    api_key_encrypted: Any = None,
    api_key_nonce: Any = None,
    endpoint: str | None = None,
    note: str | None = None,
) -> Any:
    """Insert a new AICredential row. Does NOT commit — caller must commit."""
    from app.models.ai_credential import AICredential

    cred = AICredential(
        name=name,
        provider_type=provider_type,
        api_key_encrypted=api_key_encrypted,
        api_key_nonce=api_key_nonce,
        endpoint=endpoint,
        note=note,
    )
    db.add(cred)
    return cred


async def get_credential_usage_count(db: AsyncSession, cred_id: Any) -> int:
    """Return number of provider configs referencing this credential."""
    from sqlalchemy import func, select
    from app.models.ai_provider import AIProviderConfig

    result = await db.execute(
        select(func.count()).where(AIProviderConfig.credential_id == cred_id)
    )
    return result.scalar() or 0


# ── Provider Config CRUD ───────────────────────────────────────────────────────

async def list_provider_configs(db: AsyncSession) -> list:
    """Return all AIProviderConfig rows."""
    from sqlalchemy import select
    from app.models.ai_provider import AIProviderConfig

    result = await db.execute(select(AIProviderConfig))
    return list(result.scalars().all())


async def get_provider_config_by_role(db: AsyncSession, agent_role: str) -> Any:
    """Return AIProviderConfig for the given agent_role, or None."""
    from sqlalchemy import select
    from app.models.ai_provider import AIProviderConfig

    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.agent_role == agent_role)
    )
    return result.scalar_one_or_none()


async def upsert_provider_config(
    db: AsyncSession,
    agent_role: str,
    *,
    provider: str,
    model: str | None,
    endpoint: str | None,
    credential_id: Any,
    rpm_limit: int,
    tpm_limit: int | None,
    token_budget_daily: int | None,
    thread_policy: str | None,
    enabled: bool,
    api_key_encrypted: Any = None,
    api_key_nonce: Any = None,
) -> Any:
    """Create or update AIProviderConfig. Does NOT commit — caller must commit."""
    from datetime import UTC, datetime
    from app.models.ai_provider import AIProviderConfig

    config = await get_provider_config_by_role(db, agent_role)
    if config is None:
        config = AIProviderConfig(
            agent_role=agent_role,
            provider=provider,
            model=model,
            endpoint=endpoint,
            credential_id=credential_id,
            rpm_limit=rpm_limit,
            tpm_limit=tpm_limit,
            token_budget_daily=token_budget_daily,
            thread_policy=thread_policy,
            enabled=enabled,
        )
        if api_key_encrypted is not None:
            config.api_key_encrypted = api_key_encrypted
            config.api_key_nonce = api_key_nonce
        db.add(config)
    else:
        config.provider = provider
        config.model = model
        config.endpoint = endpoint
        config.credential_id = credential_id
        config.rpm_limit = rpm_limit
        config.tpm_limit = tpm_limit
        config.token_budget_daily = token_budget_daily
        config.thread_policy = thread_policy
        config.enabled = enabled
        config.updated_at = datetime.now(UTC)
        if api_key_encrypted is not None:
            config.api_key_encrypted = api_key_encrypted
            config.api_key_nonce = api_key_nonce
    return config


async def delete_provider_config_by_role(db: AsyncSession, agent_role: str) -> Any:
    """Delete AIProviderConfig for role. Returns the config if found, else None."""
    config = await get_provider_config_by_role(db, agent_role)
    if config is not None:
        await db.delete(config)
    return config
