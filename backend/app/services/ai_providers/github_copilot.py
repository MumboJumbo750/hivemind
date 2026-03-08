"""GitHub Copilot AI Provider — uses Copilot's OpenAI-compatible API.

Endpoint: https://api.githubcopilot.com
Auth: GitHub token (from `gh auth token` or PAT with copilot scope).

Models: gpt-4o, gpt-4.1, claude-sonnet-4, o3-mini, etc.
  → depends on Copilot subscription level.
"""
import logging
from typing import Any

from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

GITHUB_COPILOT_BASE_URL = "https://api.githubcopilot.com"


class GitHubCopilotProvider(OpenAIProvider):
    """GitHub Copilot via OpenAI-compatible API."""

    def __init__(self, github_token: str, default_model_name: str = "gpt-4o"):
        super().__init__(
            api_key=github_token,
            default_model_name=default_model_name,
            base_url=GITHUB_COPILOT_BASE_URL,
        )
        self._github_token = github_token

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self._github_token,
                    base_url=GITHUB_COPILOT_BASE_URL,
                    default_headers={"Copilot-Integration-Id": "hivemind"},
                )
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._client

    def default_model(self) -> str:
        return self._default_model

    @staticmethod
    async def list_available_models(github_token: str) -> list[dict]:
        """Fetch available models from GitHub Copilot API."""
        import httpx
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json",
            "Copilot-Integration-Id": "hivemind",
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GITHUB_COPILOT_BASE_URL}/models",
                    headers=headers,
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                # Copilot returns {"data": [...]} like OpenAI
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            logger.error("Failed to fetch Copilot models: %s", e)
            return []
