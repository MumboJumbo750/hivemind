"""REST endpoint for gamification achievements — TASK-5-022.

Endpoints:
  GET /api/users/me/achievements — Current user's EXP, level, badges.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import CurrentActor, require_role
from app.services.gamification import get_user_achievements

router = APIRouter(prefix="/users", tags=["gamification"])


@router.get("/me/achievements")
async def my_achievements(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin", "owner", "member")),
):
    """Get current user's gamification achievements."""
    return await get_user_achievements(db, actor.id)
