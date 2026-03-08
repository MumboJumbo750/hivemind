"""Fix stale dispatch records and update task state."""
import asyncio
from app.db import AsyncSessionLocal
from sqlalchemy import text


async def fix():
    async with AsyncSessionLocal() as db:
        # Check stale records
        r = await db.execute(text(
            "SELECT agent_role, status, COUNT(*) FROM conductor_dispatches "
            "WHERE status IN ('running', 'dispatched') GROUP BY agent_role, status ORDER BY agent_role"
        ))
        rows = r.fetchall()
        print("Active dispatch records:")
        for row in rows:
            print(f"  {row}")

        # Clean up stale records older than 30 minutes
        r2 = await db.execute(text(
            "UPDATE conductor_dispatches SET status='cancelled', completed_at=NOW() "
            "WHERE status IN ('running', 'dispatched') AND dispatched_at < NOW() - INTERVAL '30 minutes'"
        ))
        updated = r2.rowcount
        await db.commit()
        print(f"Cleaned up {updated} stale records")

        # Verify
        r3 = await db.execute(text(
            "SELECT agent_role, COUNT(*) FROM conductor_dispatches "
            "WHERE status IN ('running', 'dispatched') GROUP BY agent_role"
        ))
        remaining = r3.fetchall()
        print(f"Remaining active: {remaining}")


asyncio.run(fix())
