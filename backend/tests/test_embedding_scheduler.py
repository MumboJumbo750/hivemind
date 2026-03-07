from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_embedding_backfill_job_enqueues_missing_embeddings() -> None:
    embedding_service = MagicMock()
    embedding_service.enqueue_missing_embeddings = AsyncMock(
        return_value={"epics": 2, "skills": 1, "wiki_articles": 0, "docs": 3}
    )

    with patch(
        "app.services.embedding_service.get_embedding_service",
        return_value=embedding_service,
    ):
        from app.services.scheduler import _embedding_backfill_job

        await _embedding_backfill_job()

    embedding_service.enqueue_missing_embeddings.assert_awaited_once()
