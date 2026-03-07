"""AI Provider ABC — base class for all AI providers (Phase 8, TASK-8-002)."""
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class AIMessage:
    role: str  # 'user' | 'assistant' | 'system'
    content: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AIResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    finish_reason: str = ""


@dataclass
class AIChunk:
    delta: str = ""
    tool_call_delta: dict | None = None
    finish_reason: str = ""


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def send_prompt(
        self,
        prompt: str,
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AIResponse:
        """Send a prompt and return the full response."""

    async def send_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AIResponse:
        """Send a multi-turn conversation and return the response.

        Default implementation: extract last user message and delegate to send_prompt.
        Subclasses should override for proper multi-turn support.
        """
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break
        return await self.send_prompt(last_user, tools, model, system)

    @abstractmethod
    async def stream_prompt(
        self,
        prompt: str,
        tools: list[dict] | None = None,
        model: str | None = None,
        system: str | None = None,
    ) -> AsyncIterator[AIChunk]:
        """Stream a prompt response."""
        # default implementation: fallback to send_prompt
        response = await self.send_prompt(prompt, tools, model, system)
        yield AIChunk(delta=response.content or "", finish_reason=response.finish_reason)

    @abstractmethod
    def supports_tool_calling(self) -> bool:
        """Return True if this provider supports tool calling."""

    @abstractmethod
    def default_model(self) -> str:
        """Return the default model name."""

    async def health_check(self) -> bool:
        """Check if the provider is reachable. Default: always True."""
        return True
