"""Anthropic (Claude) AI Provider — Phase 8 (TASK-8-002)."""
import logging
from typing import AsyncIterator

from .base import AIChunk, AIMessage, AIProvider, AIResponse, ToolCall

logger = logging.getLogger(__name__)


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, default_model_name: str = "claude-sonnet-4-6"):
        self._api_key = api_key
        self._default_model = default_model_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
            except ImportError:
                raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
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
        kwargs: dict = {
            "model": model_name,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = await client.messages.create(**kwargs)
        tool_calls = []
        content_text = ""
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input or {},
                ))

        return AIResponse(
            content=content_text or None,
            tool_calls=tool_calls,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            finish_reason=response.stop_reason or "",
        )

    async def stream_prompt(
        self,
        prompt: str,
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AsyncIterator[AIChunk]:
        client = self._get_client()
        model_name = model or self._default_model
        kwargs: dict = {
            "model": model_name,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield AIChunk(delta=text)
        yield AIChunk(finish_reason="end_turn")

    def supports_tool_calling(self) -> bool:
        return True

    def default_model(self) -> str:
        return self._default_model
