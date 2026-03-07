"""Anthropic (Claude) AI Provider — Phase 8 (TASK-8-002)."""
import json
import logging
from typing import Any, AsyncIterator

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

    async def send_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AIResponse:
        """Multi-turn conversation with Anthropic API.

        Converts generic message format to Anthropic-specific format:
        - Assistant messages with tool_calls → content blocks with tool_use
        - Tool result messages (role: "tool") → user messages with tool_result blocks
        """
        client = self._get_client()
        model_name = model or self._default_model

        # Convert MCP tool format → Anthropic tool format
        anthropic_tools = None
        if tools:
            anthropic_tools = []
            for t in tools:
                anthropic_tools.append({
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("inputSchema", {}),
                })

        # Convert messages to Anthropic format
        anthropic_messages: list[dict[str, Any]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role", "user")

            if role == "user":
                anthropic_messages.append({"role": "user", "content": msg.get("content", "")})
                i += 1

            elif role == "assistant":
                # Build content blocks for assistant
                content_blocks: list[dict[str, Any]] = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc.get("arguments", {}),
                        })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content_blocks if content_blocks else msg.get("content", ""),
                })
                i += 1

            elif role == "tool":
                # Collect consecutive tool results into a single user message
                tool_results: list[dict[str, Any]] = []
                while i < len(messages) and messages[i].get("role") == "tool":
                    tool_msg = messages[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_msg["tool_call_id"],
                        "content": tool_msg.get("content", ""),
                    })
                    i += 1
                anthropic_messages.append({"role": "user", "content": tool_results})

            else:
                # Skip system messages (handled separately)
                i += 1

        kwargs: dict = {
            "model": model_name,
            "max_tokens": 8192,
            "messages": anthropic_messages,
        }
        if system:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

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
