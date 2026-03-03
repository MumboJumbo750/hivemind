"""OpenAI AI Provider — Phase 8 (TASK-8-002)."""
import logging
from typing import AsyncIterator

from .base import AIChunk, AIProvider, AIResponse, ToolCall

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, default_model_name: str = "gpt-4o", base_url: str | None = None):
        self._api_key = api_key
        self._default_model = default_model_name
        self._base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                kwargs = {"api_key": self._api_key}
                if self._base_url:
                    kwargs["base_url"] = self._base_url
                self._client = AsyncOpenAI(**kwargs)
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._client

    async def send_prompt(
        self,
        prompt: str,
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AIResponse:
        client = self._get_client()
        model_name = model or self._default_model
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {"model": model_name, "messages": messages}
        if tools:
            # Convert MCP tool format to OpenAI format
            openai_tools = []
            for t in tools:
                tool_name = t["name"].replace("/", "__").replace("-", "_")
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": t.get("description", ""),
                        "parameters": t.get("inputSchema", {}),
                    },
                })
            kwargs["tools"] = openai_tools

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                import json
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name.replace("__", "/"),
                    arguments=json.loads(tc.function.arguments or "{}"),
                ))

        return AIResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            model=response.model,
            finish_reason=choice.finish_reason or "",
        )

    async def stream_prompt(
        self,
        prompt: str,
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AsyncIterator[AIChunk]:
        # fallback: use non-streaming
        response = await self.send_prompt(prompt, tools, model, system)
        yield AIChunk(delta=response.content or "", finish_reason=response.finish_reason)

    def supports_tool_calling(self) -> bool:
        return True

    def default_model(self) -> str:
        return self._default_model
