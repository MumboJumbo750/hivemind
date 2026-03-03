"""Ollama AI Provider — Phase 8 (TASK-8-002)."""
import json
import logging
from typing import AsyncIterator

import httpx

from .base import AIChunk, AIProvider, AIResponse, ToolCall

logger = logging.getLogger(__name__)


class OllamaProvider(AIProvider):
    def __init__(self, base_url: str, default_model_name: str = "llama3.1"):
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model_name

    async def send_prompt(
        self,
        prompt: str,
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AIResponse:
        model_name = model or self._default_model
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {"model": model_name, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()

        msg = data.get("message", {})
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            tool_calls.append(ToolCall(
                id=str(hash(fn.get("name", "") + str(fn.get("arguments", {})))),
                name=fn.get("name", ""),
                arguments=fn.get("arguments", {}),
            ))

        return AIResponse(
            content=msg.get("content"),
            tool_calls=tool_calls,
            model=data.get("model", model_name),
            finish_reason=data.get("done_reason", ""),
        )

    async def stream_prompt(
        self,
        prompt: str,
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AsyncIterator[AIChunk]:
        response = await self.send_prompt(prompt, tools, model, system)
        yield AIChunk(delta=response.content or "", finish_reason=response.finish_reason)

    def supports_tool_calling(self) -> bool:
        return True

    def default_model(self) -> str:
        return self._default_model

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._base_url}/api/tags", timeout=5.0)
                return resp.status_code == 200
        except Exception:
            return False
