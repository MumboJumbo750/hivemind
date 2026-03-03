"""Pydantic schemas for AI Credentials."""
from pydantic import BaseModel


class AICredentialCreate(BaseModel):
    name: str
    provider_type: str  # anthropic, openai, github_copilot, github_models, ollama, custom
    api_key: str | None = None  # plaintext — encrypted server-side
    endpoint: str | None = None
    note: str | None = None


class AICredentialUpdate(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    api_key: str | None = None  # plaintext — encrypted server-side; None = keep unchanged
    endpoint: str | None = None
    note: str | None = None


class AICredentialOut(BaseModel):
    id: str
    name: str
    provider_type: str
    endpoint: str | None
    note: str | None
    has_api_key: bool
    usage_count: int = 0  # how many provider configs reference this credential

    class Config:
        from_attributes = True
