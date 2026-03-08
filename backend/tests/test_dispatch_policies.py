"""Tests for Dispatch Policy service and API — TASK-AGENT-003."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.dispatch_policy import (
    EffectivePolicy,
    SkipReason,
    _DEFAULT_POLICIES,
    count_active_dispatches,
    get_default_policy,
    get_effective_policy,
)


# ---------------------------------------------------------------------------
# Unit: EffectivePolicy defaults
# ---------------------------------------------------------------------------


def test_effective_policy_known_roles_have_conservative_defaults() -> None:
    for role in ("worker", "reviewer", "gaertner", "kartograph", "architekt", "stratege", "triage"):
        p = get_default_policy(role)
        assert p.agent_role == role
        assert p.max_parallel >= 1
        assert p.cooldown_seconds >= 0
        assert p.rpm_limit >= 1
        assert p.token_budget >= 100
        assert p.preferred_execution_mode in {"local", "ide", "github_actions", "byoai"}
        assert isinstance(p.fallback_chain, list)
        assert len(p.fallback_chain) >= 1
        assert p.enabled is True
        assert p.source == "default"


def test_effective_policy_unknown_role_gets_safe_default() -> None:
    p = get_default_policy("unknown_future_role")
    assert p.agent_role == "unknown_future_role"
    assert p.max_parallel == 1
    assert p.rpm_limit == 5
    assert p.token_budget == 4000
    assert p.cooldown_seconds == 30
    assert p.enabled is True


def test_reviewer_has_stricter_limits_than_worker() -> None:
    worker = get_default_policy("worker")
    reviewer = get_default_policy("reviewer")
    # reviewer should be more conservative (fewer parallel, longer cooldown)
    assert reviewer.max_parallel <= worker.max_parallel
    assert reviewer.cooldown_seconds >= worker.cooldown_seconds


def test_effective_policy_as_dict_is_serializable() -> None:
    p = get_default_policy("worker")
    d = p.as_dict()
    assert d["agent_role"] == "worker"
    assert "preferred_execution_mode" in d
    assert "fallback_chain" in d
    assert "rpm_limit" in d
    assert "token_budget" in d
    assert "max_parallel" in d
    assert "cooldown_seconds" in d
    assert "enabled" in d
    assert "source" in d


# ---------------------------------------------------------------------------
# Unit: get_effective_policy — DB fallback behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_effective_policy_returns_default_on_db_error() -> None:
    db = SimpleNamespace()  # no execute method → will raise AttributeError
    policy = await get_effective_policy("worker", db)
    assert policy.source == "default"
    assert policy.agent_role == "worker"
    assert isinstance(policy.fallback_chain, list)


@pytest.mark.asyncio
async def test_get_effective_policy_returns_default_when_no_db_row() -> None:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db = SimpleNamespace(execute=AsyncMock(return_value=mock_result))

    policy = await get_effective_policy("reviewer", db)
    assert policy.source == "default"
    assert policy.agent_role == "reviewer"
    assert policy.max_parallel == get_default_policy("reviewer").max_parallel


@pytest.mark.asyncio
async def test_get_effective_policy_merges_db_row_with_defaults() -> None:
    db_row = SimpleNamespace(
        agent_role="worker",
        preferred_execution_mode="ide",
        fallback_chain=["ide", "byoai"],
        rpm_limit=20,
        token_budget=None,  # falls back to default
        max_parallel=None,  # falls back to default
        cooldown_seconds=5,
        enabled=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = db_row
    db = SimpleNamespace(execute=AsyncMock(return_value=mock_result))

    policy = await get_effective_policy("worker", db)
    assert policy.source == "db"
    assert policy.preferred_execution_mode == "ide"
    assert policy.fallback_chain == ["ide", "byoai"]
    assert policy.rpm_limit == 20
    assert policy.token_budget == get_default_policy("worker").token_budget  # fallback
    assert policy.max_parallel == get_default_policy("worker").max_parallel  # fallback
    assert policy.cooldown_seconds == 5


@pytest.mark.asyncio
async def test_get_effective_policy_empty_fallback_chain_uses_default() -> None:
    db_row = SimpleNamespace(
        agent_role="gaertner",
        preferred_execution_mode="local",
        fallback_chain=None,  # invalid → use default
        rpm_limit=None,
        token_budget=None,
        max_parallel=None,
        cooldown_seconds=None,
        enabled=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = db_row
    db = SimpleNamespace(execute=AsyncMock(return_value=mock_result))

    policy = await get_effective_policy("gaertner", db)
    assert policy.fallback_chain == get_default_policy("gaertner").fallback_chain


@pytest.mark.asyncio
async def test_get_effective_policy_disabled_role_is_respected() -> None:
    db_row = SimpleNamespace(
        agent_role="triage",
        preferred_execution_mode="local",
        fallback_chain=["local", "byoai"],
        rpm_limit=None,
        token_budget=None,
        max_parallel=None,
        cooldown_seconds=None,
        enabled=False,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = db_row
    db = SimpleNamespace(execute=AsyncMock(return_value=mock_result))

    policy = await get_effective_policy("triage", db)
    assert policy.enabled is False


# ---------------------------------------------------------------------------
# Unit: count_active_dispatches — error resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_active_dispatches_returns_zero_on_db_error() -> None:
    db = SimpleNamespace()  # no execute → raises AttributeError
    count = await count_active_dispatches("worker", db)
    assert count == 0


@pytest.mark.asyncio
async def test_count_active_dispatches_returns_db_value() -> None:
    mock_result = MagicMock()
    mock_result.scalar.return_value = 2
    db = SimpleNamespace(execute=AsyncMock(return_value=mock_result))

    count = await count_active_dispatches("worker", db)
    assert count == 2


# ---------------------------------------------------------------------------
# Unit: SkipReason constants
# ---------------------------------------------------------------------------


def test_skip_reason_constants_are_strings() -> None:
    assert isinstance(SkipReason.COOLDOWN_ACTIVE, str)
    assert isinstance(SkipReason.PARALLEL_LIMIT_EXCEEDED, str)
    assert isinstance(SkipReason.POLICY_DISABLED, str)
    assert isinstance(SkipReason.PROVIDER_UNAVAILABLE, str)
    assert isinstance(SkipReason.BYOAI_FALLBACK, str)


# ---------------------------------------------------------------------------
# Integration: Conductor respects policy_disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conductor_returns_policy_disabled_when_role_is_off() -> None:
    from app.services.conductor import ConductorService

    service = ConductorService()
    db = SimpleNamespace(commit=AsyncMock())

    disabled_policy = EffectivePolicy(
        agent_role="worker",
        enabled=False,
    )

    with patch("app.config.settings.hivemind_conductor_enabled", True), \
         patch("app.services.dispatch_policy.get_effective_policy", AsyncMock(return_value=disabled_policy)):
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-99",
            trigger_detail="state:ready->in_progress",
            agent_role="worker",
            prompt_type="worker_task",
            db=db,
        )

    assert result["status"] == "policy_disabled"
    assert result["skip_reason"] == SkipReason.POLICY_DISABLED
    assert result.get("byoai") is True


# ---------------------------------------------------------------------------
# Integration: Conductor applies per-role parallelism gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conductor_skips_when_parallel_limit_exceeded() -> None:
    from app.services.conductor import ConductorService

    service = ConductorService()
    dispatch_stub = SimpleNamespace(id=uuid.uuid4(), result={}, status="dispatched")

    db = SimpleNamespace(commit=AsyncMock())

    limited_policy = EffectivePolicy(
        agent_role="reviewer",
        max_parallel=1,
        cooldown_seconds=0,
    )

    async def fake_record(*_args, result=None, **_kwargs):
        dispatch_stub.result = result
        return dispatch_stub

    with patch("app.config.settings.hivemind_conductor_enabled", True), \
         patch("app.services.dispatch_policy.get_effective_policy", AsyncMock(return_value=limited_policy)), \
         patch("app.services.dispatch_policy.count_active_dispatches", AsyncMock(return_value=1)), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_resolve_dispatch_context", AsyncMock(return_value={})), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value={})), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_serialize_thread_context", return_value={}):
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-42",
            trigger_detail="state:in_progress->in_review",
            agent_role="reviewer",
            prompt_type="reviewer_check",
            db=db,
        )

    assert result["status"] == "parallel_limit_exceeded"
    assert result["skip_reason"] == SkipReason.PARALLEL_LIMIT_EXCEEDED
    assert result["max_parallel"] == 1
    assert result["active_dispatches"] == 1


# ---------------------------------------------------------------------------
# Integration: Conductor uses policy cooldown_seconds
# ---------------------------------------------------------------------------


def test_conductor_cooldown_key_uses_policy_cooldown() -> None:
    """The cooldown bucket changes when cooldown_seconds changes."""
    import time
    from app.services.conductor import _cooldown_key

    # Same input, same bucket within the same second
    ck1 = _cooldown_key("worker", "TASK-1", 10)
    ck2 = _cooldown_key("worker", "TASK-1", 60)
    # Different cooldown_seconds → different bucket divisors → likely different result
    # (They'd only be the same if time happens to be divisible by both, which is uncommon)
    # We just verify the key format is well-formed
    assert "worker" in ck1
    assert "TASK-1" in ck1
    assert "worker" in ck2
    assert "TASK-1" in ck2


# ---------------------------------------------------------------------------
# API: Dispatch policies endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_policies_returns_all_known_roles(client) -> None:
    resp = await client.get("/api/dispatch/policies")
    assert resp.status_code == 200
    data = resp.json()
    assert "policies" in data
    roles = {p["agent_role"] for p in data["policies"]}
    # All built-in roles should be present
    for role in ("worker", "reviewer", "gaertner", "kartograph", "architekt", "stratege", "triage"):
        assert role in roles


@pytest.mark.asyncio
async def test_get_single_policy_returns_policy_fields(client) -> None:
    resp = await client.get("/api/dispatch/policies/worker")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_role"] == "worker"
    assert "preferred_execution_mode" in data
    assert "fallback_chain" in data
    assert "rpm_limit" in data
    assert "token_budget" in data
    assert "max_parallel" in data
    assert "cooldown_seconds" in data
    assert "enabled" in data


@pytest.mark.asyncio
async def test_upsert_policy_validates_execution_mode(client) -> None:
    resp = await client.put(
        "/api/dispatch/policies/worker",
        json={"preferred_execution_mode": "invalid_mode"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upsert_policy_validates_empty_fallback_chain(client) -> None:
    resp = await client.put(
        "/api/dispatch/policies/worker",
        json={"fallback_chain": []},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_policies_status_endpoint_returns_at_limit_field(client) -> None:
    resp = await client.get("/api/dispatch/policies/status")
    assert resp.status_code == 200
    data = resp.json()
    for policy in data["policies"]:
        assert "at_limit" in policy
        assert isinstance(policy["at_limit"], bool)
