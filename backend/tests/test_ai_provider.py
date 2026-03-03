"""Tests for AI Provider Service — Phase 8 (TASK-8-002).

Covers:
- Provider ABC interface
- Routing: DB config → env var fallback → NeedsManualMode
- Encrypt / decrypt round-trip
- Token calibration
- Rate limiter
"""
import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Encryption round-trip ─────────────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip():
    """encrypt_api_key → decrypt_api_key returns original."""
    from app.services.ai_provider import encrypt_api_key, decrypt_api_key
    passphrase = "test-passphrase-xyz"
    original = "sk-test-key-12345"
    ciphertext, nonce = encrypt_api_key(original, passphrase)
    assert ciphertext != original.encode()
    decrypted = decrypt_api_key(ciphertext, nonce, passphrase)
    assert decrypted == original


def test_encrypt_decrypt_wrong_passphrase():
    """Decryption with wrong passphrase fails."""
    from app.services.ai_provider import encrypt_api_key, decrypt_api_key
    ciphertext, nonce = encrypt_api_key("secret", "correct-passphrase")
    with pytest.raises(Exception):
        decrypt_api_key(ciphertext, nonce, "wrong-passphrase")


# ── Token calibration ─────────────────────────────────────────────────────────

def test_calibrate_token_count_default():
    """Without calibration config, factor is 1.0."""
    from app.services.ai_provider import calibrate_token_count
    with patch("app.services.ai_provider.settings") as mock_settings:
        mock_settings.hivemind_token_count_calibration = ""
        assert calibrate_token_count(1000, "anthropic") == 1000


def test_calibrate_token_count_with_factor():
    """Calibration factor is applied."""
    from app.services.ai_provider import calibrate_token_count
    with patch("app.services.ai_provider.settings") as mock_settings:
        mock_settings.hivemind_token_count_calibration = '{"anthropic": 1.05, "openai": 1.0}'
        assert calibrate_token_count(1000, "anthropic") == 1050
        assert calibrate_token_count(1000, "openai") == 1000
        assert calibrate_token_count(1000, "unknown") == 1000


# ── Rate limiter ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limiter_acquire():
    """RateLimiter allows first call immediately."""
    from app.services.ai_provider import RateLimiter
    limiter = RateLimiter(rpm_limit=600)  # 10 per second
    await limiter.acquire()  # Should not block


@pytest.mark.asyncio
async def test_rate_limiter_zero_rpm():
    """RateLimiter with 0 RPM does not block."""
    from app.services.ai_provider import RateLimiter
    limiter = RateLimiter(rpm_limit=0)
    await limiter.acquire()


# ── Provider routing ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_provider_from_db_config():
    """When DB has a config for the role, builds that provider."""
    from app.services.ai_provider import get_provider

    mock_config = MagicMock()
    mock_config.agent_role = "worker"
    mock_config.provider = "openai"
    mock_config.model = "gpt-4o"
    mock_config.endpoint = None
    mock_config.api_key_encrypted = None
    mock_config.api_key_nonce = None
    mock_config.enabled = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_config

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    with patch("app.services.ai_provider.settings") as mock_settings:
        mock_settings.hivemind_key_passphrase = ""
        mock_settings.hivemind_ai_api_key = ""
        provider = await get_provider("worker", mock_db)

    from app.services.ai_providers.openai_provider import OpenAIProvider
    assert isinstance(provider, OpenAIProvider)


@pytest.mark.asyncio
async def test_get_provider_env_fallback():
    """When no DB config, falls back to HIVEMIND_AI_API_KEY → AnthropicProvider."""
    from app.services.ai_provider import get_provider

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    with patch("app.services.ai_provider.settings") as mock_settings:
        mock_settings.hivemind_ai_api_key = "sk-test-key"
        provider = await get_provider("worker", mock_db)

    from app.services.ai_providers.anthropic import AnthropicProvider
    assert isinstance(provider, AnthropicProvider)


@pytest.mark.asyncio
async def test_get_provider_no_config_raises():
    """When no DB config and no env var, raises NeedsManualMode."""
    from app.services.ai_provider import NeedsManualMode, get_provider

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    with patch("app.services.ai_provider.settings") as mock_settings:
        mock_settings.hivemind_ai_api_key = ""
        with pytest.raises(NeedsManualMode):
            await get_provider("worker", mock_db)


# ── Provider implementations (mock HTTP) ──────────────────────────────────────

def test_anthropic_provider_interface():
    """AnthropicProvider implements all ABC methods."""
    from app.services.ai_providers.anthropic import AnthropicProvider
    p = AnthropicProvider(api_key="test-key")
    assert p.supports_tool_calling() is True
    assert p.default_model() != ""


def test_openai_provider_interface():
    """OpenAIProvider implements all ABC methods."""
    from app.services.ai_providers.openai_provider import OpenAIProvider
    p = OpenAIProvider(api_key="test-key")
    assert p.supports_tool_calling() is True
    assert p.default_model() != ""


def test_ollama_provider_interface():
    """OllamaProvider implements all ABC methods."""
    from app.services.ai_providers.ollama import OllamaProvider
    p = OllamaProvider(base_url="http://localhost:11434")
    assert p.supports_tool_calling() is True
    assert p.default_model() != ""


def test_github_models_provider_interface():
    """GitHubModelsProvider implements all ABC methods."""
    from app.services.ai_providers.github_models import GitHubModelsProvider
    p = GitHubModelsProvider(github_token="test-token")
    assert p.supports_tool_calling() is True
    assert p.default_model() != ""


def test_custom_provider_interface():
    """CustomProvider implements all ABC methods."""
    from app.services.ai_providers.custom import CustomProvider
    p = CustomProvider(api_key="test-key", base_url="http://localhost:8080")
    assert p.supports_tool_calling() is True
    assert p.default_model() != ""


# ── Build provider from config ────────────────────────────────────────────────

def test_build_provider_all_types():
    """_build_provider_from_config creates correct type for each provider."""
    from app.services.ai_provider import _build_provider_from_config

    for ptype, expected_cls in [
        ("anthropic", "AnthropicProvider"),
        ("openai", "OpenAIProvider"),
        ("github_models", "GitHubModelsProvider"),
        ("ollama", "OllamaProvider"),
        ("custom", "CustomProvider"),
    ]:
        config = MagicMock()
        config.provider = ptype
        config.model = "test-model"
        config.endpoint = "http://localhost:8080"
        config.api_key_encrypted = None
        config.api_key_nonce = None
        config.agent_role = "worker"

        with patch("app.services.ai_provider.settings") as mock_settings:
            mock_settings.hivemind_key_passphrase = ""
            mock_settings.hivemind_ai_api_key = ""
            mock_settings.hivemind_github_token = "gh-token"
            mock_settings.hivemind_ollama_url = "http://ollama:11434"
            provider = _build_provider_from_config(config)

        assert type(provider).__name__ == expected_cls, f"Expected {expected_cls} for {ptype}, got {type(provider).__name__}"


def test_build_provider_unknown_raises():
    """Unknown provider type raises ValueError."""
    from app.services.ai_provider import _build_provider_from_config

    config = MagicMock()
    config.provider = "nonexistent"
    config.api_key_encrypted = None
    config.api_key_nonce = None
    config.agent_role = "worker"

    with patch("app.services.ai_provider.settings") as mock_settings:
        mock_settings.hivemind_key_passphrase = ""
        mock_settings.hivemind_ai_api_key = ""
        with pytest.raises(ValueError, match="Unknown provider type"):
            _build_provider_from_config(config)
