from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.prompt_generator import PromptGenerator


@pytest.mark.asyncio
async def test_generate_appends_thread_policy_block() -> None:
    db = AsyncMock()
    db.add = lambda *_args, **_kwargs: None
    generator = PromptGenerator(db)
    generator._settings = None

    with patch.object(generator, "_worker", AsyncMock(return_value="Worker Prompt")), \
         patch.object(generator, "_load_task", AsyncMock(return_value=None)), \
         patch(
             "app.services.agent_threading.AgentThreadService.resolve_context",
             AsyncMock(
                 return_value={
                     "prompt_block": "## Thread-Policy\n- Modell: `attempt_stateful`\n- Scope: `attempt:TASK-1 v2 / qa#0`"
                 }
             ),
         ):
        prompt = await generator.generate("worker", task_id=str(uuid.uuid4()))

    assert "Worker Prompt" in prompt
    assert "## Thread-Policy" in prompt
    assert "attempt_stateful" in prompt
