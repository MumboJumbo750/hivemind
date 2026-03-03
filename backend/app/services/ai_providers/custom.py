"""Custom (OpenAI-compatible) AI Provider — Phase 8 (TASK-8-002)."""
from .openai_provider import OpenAIProvider


class CustomProvider(OpenAIProvider):
    """Custom OpenAI-compatible endpoint provider."""

    def __init__(self, api_key: str, base_url: str, default_model_name: str = "default"):
        super().__init__(api_key=api_key, default_model_name=default_model_name, base_url=base_url)
