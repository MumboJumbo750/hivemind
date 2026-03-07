"""OpenAI AI Provider — Phase 8 (TASK-8-002)."""
import json
import logging
from typing import Any, AsyncIterator

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

    async def send_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AIResponse:
        """Multi-turn conversation with tool support (OpenAI format)."""
        client = self._get_client()
        model_name = model or self._default_model

        # Build OpenAI messages array
        oai_messages: list[dict[str, Any]] = []
        if system:
            oai_messages.append({"role": "system", "content": system})

        # Map for tool-name translation (MCP uses hyphens, OpenAI needs underscores)
        name_to_oai: dict[str, str] = {}
        oai_to_name: dict[str, str] = {}

        for msg in messages:
            role = msg.get("role", "user")
            if role == "assistant":
                oai_msg: dict[str, Any] = {"role": "assistant"}
                if msg.get("content"):
                    oai_msg["content"] = msg["content"]
                if msg.get("tool_calls"):
                    oai_msg["tool_calls"] = []
                    for tc in msg["tool_calls"]:
                        oai_name = tc["name"].replace("/", "__").replace("-", "_")
                        name_to_oai[tc["name"]] = oai_name
                        oai_to_name[oai_name] = tc["name"]
                        oai_msg["tool_calls"].append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": oai_name,
                                "arguments": json.dumps(tc.get("arguments", {})),
                            },
                        })
                oai_messages.append(oai_msg)
            elif role == "tool":
                oai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg.get("content", ""),
                })
            else:
                oai_messages.append({"role": role, "content": msg.get("content", "")})

        kwargs: dict[str, Any] = {"model": model_name, "messages": oai_messages}
        if tools:
            openai_tools = []
            for t in tools:
                oai_name = t["name"].replace("/", "__").replace("-", "_")
                name_to_oai[t["name"]] = oai_name
                oai_to_name[oai_name] = t["name"]
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": oai_name,
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
                original_name = oai_to_name.get(tc.function.name, tc.function.name)
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=original_name,
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
