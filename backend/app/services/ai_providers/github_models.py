"""GitHub Models AI Provider — Phase 8 (TASK-8-011).

Uses OpenAI-compatible SDK with GitHub PAT.
base_url = 'https://models.inference.ai.azure.com'
"""
import logging

from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"


class GitHubModelsProvider(OpenAIProvider):
    """GitHub Models via Azure-hosted OpenAI-compatible API."""

    def __init__(self, github_token: str, default_model_name: str = "gpt-4o"):
        super().__init__(
            api_key=github_token,
            default_model_name=default_model_name,
            base_url=GITHUB_MODELS_BASE_URL,
        )
        self._github_token = github_token

    def default_model(self) -> str:
        return self._default_model

    @staticmethod
    async def list_available_models(github_token: str) -> list[dict]:
        """Fetch available models from GitHub Models catalog."""
        import httpx
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GITHUB_MODELS_BASE_URL}/models",
                    headers=headers,
                    timeout=10.0,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error("Failed to fetch GitHub Models catalog: %s", e)
            return []
