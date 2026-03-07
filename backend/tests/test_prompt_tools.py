from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.tools.prompt_tools import _handle_get_prompt


@pytest.mark.asyncio
async def test_get_prompt_accepts_task_key_alias() -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False

    with patch("app.mcp.tools.prompt_tools.AsyncSessionLocal", return_value=session), \
         patch("app.mcp.tools.prompt_tools.PromptGenerator") as mock_generator_cls, \
         patch("app.mcp.tools.prompt_tools.count_tokens", return_value=12):
        mock_generator = mock_generator_cls.return_value
        mock_generator.generate = AsyncMock(return_value="generated prompt")

        result = await _handle_get_prompt({"type": "worker", "task_key": "TASK-88"})

    payload = json.loads(result[0].text)
    assert payload["data"]["prompt"] == "generated prompt"
    mock_generator.generate.assert_awaited_once_with(
        "worker",
        task_id="TASK-88",
        epic_id=None,
        project_id=None,
        requirement_text=None,
        priority_hint=None,
        actor_id=None,
    )


@pytest.mark.asyncio
async def test_get_prompt_supports_stratege_requirement() -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False

    with patch("app.mcp.tools.prompt_tools.AsyncSessionLocal", return_value=session), \
         patch("app.mcp.tools.prompt_tools.PromptGenerator") as mock_generator_cls, \
         patch("app.mcp.tools.prompt_tools.count_tokens", return_value=42):
        mock_generator = mock_generator_cls.return_value
        mock_generator.generate = AsyncMock(return_value="generated stratege requirement prompt")

        result = await _handle_get_prompt({
            "type": "stratege_requirement",
            "project_id": "11111111-1111-1111-1111-111111111111",
            "requirement_text": "Neue Suchfunktion",
            "priority_hint": "high",
        })

    payload = json.loads(result[0].text)
    assert payload["data"]["prompt_type"] == "stratege_requirement"
    assert payload["data"]["prompt"] == "generated stratege requirement prompt"
    mock_generator.generate.assert_awaited_once_with(
        "stratege_requirement",
        task_id=None,
        epic_id=None,
        project_id="11111111-1111-1111-1111-111111111111",
        requirement_text="Neue Suchfunktion",
        priority_hint="high",
        actor_id=None,
    )
