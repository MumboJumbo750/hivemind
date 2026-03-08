"""Check DB tables and learning artifacts state."""
import asyncio
from app.db import AsyncSessionLocal
from sqlalchemy import text


async def check():
    async with AsyncSessionLocal() as db:
        # Check if learning_artifacts table exists
        r = await db.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='learning_artifacts'"
        ))
        rows = r.fetchall()
        print(f"learning_artifacts table exists: {bool(rows)}")

        # Check if prompt_history has context_refs column
        r = await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='prompt_history' ORDER BY ordinal_position"
        ))
        cols = [row[0] for row in r.fetchall()]
        print(f"prompt_history columns: {cols}")

        # Check conductor_dispatches for learning-related status
        r = await db.execute(text(
            "SELECT status, COUNT(*) FROM conductor_dispatches "
            "GROUP BY status ORDER BY status"
        ))
        print("conductor_dispatches statuses:")
        for row in r.fetchall():
            print(f"  {row[0]}: {row[1]}")


asyncio.run(check())
