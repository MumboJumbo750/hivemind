"""Tests for prompt minification and token_count_minified (TASK-AE2-003)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.prompt_generator import count_tokens, minify_prompt


# ── minify_prompt unit tests ─────────────────────────────────────────────────

def test_minify_collapses_blank_lines() -> None:
    """TASK-AE2-003: Multiple blank lines collapse to single blank line."""
    text = "line1\n\n\n\n\nline2"
    result = minify_prompt(text)
    assert result == "line1\n\nline2"


def test_minify_strips_trailing_whitespace() -> None:
    """TASK-AE2-003: Trailing whitespace per line is removed."""
    text = "line1   \nline2\t\t\nline3"
    result = minify_prompt(text)
    assert "   \n" not in result
    assert "\t\t\n" not in result


def test_minify_collapses_inline_spaces() -> None:
    """TASK-AE2-003: Multiple inline spaces collapse to single space."""
    text = "hello    world"
    result = minify_prompt(text)
    assert result == "hello world"


def test_minify_removes_horizontal_rules() -> None:
    """TASK-AE2-003: Markdown horizontal rules (--- or ***) are removed."""
    text = "section1\n---\nsection2\n***\nsection3"
    result = minify_prompt(text)
    assert "---" not in result
    assert "***" not in result
    assert "section1" in result
    assert "section2" in result


def test_minify_removes_empty_headers() -> None:
    """TASK-AE2-003: Empty markdown headers are removed."""
    text = "# Title\n##\n### \ncontent"
    result = minify_prompt(text)
    assert "# Title" in result
    assert "content" in result


def test_minify_preserves_indentation() -> None:
    """TASK-AE2-003: Leading indentation is preserved (code blocks etc)."""
    text = "def foo():\n    return 42"
    result = minify_prompt(text)
    assert "    return 42" in result


def test_minify_reduces_token_count() -> None:
    """TASK-AE2-003: Minification reduces token count on typical prompts."""
    bloated = """
# Agent Aufgabe

---

Du bist ein Worker-Agent.



Hier sind die   Details:

---

## Task

Implementiere   Feature X.



## Kontext

***

Dateien:
  - src/main.py
  - src/utils.py

---

Ende.
"""
    original_tokens = count_tokens(bloated)
    minified = minify_prompt(bloated)
    minified_tokens = count_tokens(minified)

    assert minified_tokens < original_tokens, (
        f"Minified ({minified_tokens}) should be less than original ({original_tokens})"
    )


def test_minify_idempotent() -> None:
    """TASK-AE2-003: Applying minify twice gives same result."""
    text = "line1\n\n\n\nline2   \n---\nline3"
    once = minify_prompt(text)
    twice = minify_prompt(once)
    assert once == twice


# ── PromptGenerator token_count_minified persistence ─────────────────────────

@pytest.mark.asyncio
async def test_prompt_generator_stores_minified_token_count() -> None:
    """TASK-AE2-003: PromptGenerator stores token_count_minified on history entry."""
    from app.services.prompt_generator import PromptGenerator

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    # Mock all dependencies of generate()
    mock_settings = MagicMock()
    mock_settings.hivemind_prompt_minify = True
    mock_settings.hivemind_token_budget = 8000
    mock_settings.hivemind_token_count_calibration = ""

    generator = PromptGenerator(db, settings=mock_settings)

    # Build a bloated prompt that will be minified
    bloated_prompt = "Task\n\n\n\n---\n\nImplementiere Feature X.\n\n\n\n---\n\nEnde."

    # Mock the generate flow to return our bloated prompt
    with patch.object(generator, "_worker", AsyncMock(return_value=bloated_prompt)), \
         patch.object(generator, "_load_task", AsyncMock(return_value=None)), \
         patch.object(generator, "_load_epic_by_key", AsyncMock(return_value=None)), \
         patch.object(generator, "_build_thread_policy_block", AsyncMock(return_value="")), \
         patch("app.services.prompt_generator.record_prompt_learning_context", AsyncMock()):
        result = await generator.generate("worker", task_id="TASK-42")

    # Check that db.add was called with a PromptHistory that has token_count_minified
    assert db.add.called
    entry = db.add.call_args[0][0]
    assert entry.token_count is not None
    assert entry.token_count_minified is not None
    assert entry.token_count_minified < entry.token_count


@pytest.mark.asyncio
async def test_prompt_generator_skips_minified_when_disabled() -> None:
    """TASK-AE2-003: No minified count when hivemind_prompt_minify is False."""
    from app.services.prompt_generator import PromptGenerator

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    mock_settings = MagicMock()
    mock_settings.hivemind_prompt_minify = False
    mock_settings.hivemind_token_budget = 8000
    mock_settings.hivemind_token_count_calibration = ""

    generator = PromptGenerator(db, settings=mock_settings)

    with patch.object(generator, "_worker", AsyncMock(return_value="short prompt")), \
         patch.object(generator, "_load_task", AsyncMock(return_value=None)), \
         patch.object(generator, "_load_epic_by_key", AsyncMock(return_value=None)), \
         patch.object(generator, "_build_thread_policy_block", AsyncMock(return_value="")), \
         patch("app.services.prompt_generator.record_prompt_learning_context", AsyncMock()):
        await generator.generate("worker", task_id="TASK-42")

    entry = db.add.call_args[0][0]
    assert entry.token_count_minified is None
