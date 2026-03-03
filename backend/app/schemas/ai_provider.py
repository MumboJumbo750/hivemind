"""Pydantic schemas for AI Provider Config — Phase 8."""
from pydantic import BaseModel


class AIProviderConfigIn(BaseModel):
    provider: str  # anthropic, openai, ollama, github_models, github_copilot, custom
    model: str | None = None
    endpoint: str | None = None
    api_key: str | None = None  # plaintext — encrypted server-side (inline key)
    credential_id: str | None = None  # reference to shared credential (preferred)
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    token_budget_daily: int | None = None
    enabled: bool = True


class AIProviderConfigOut(BaseModel):
    agent_role: str
    provider: str
    model: str | None
    endpoint: str | None
    rpm_limit: int | None
    tpm_limit: int | None
    token_budget_daily: int | None
    enabled: bool
    has_api_key: bool  # True if inline encrypted key is stored
    credential_id: str | None = None
    credential_name: str | None = None  # display name of linked credential

    class Config:
        from_attributes = True
