"""Quick check: task_skills linkages and pinned_skills JSONB."""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

engine = create_async_engine("postgresql+asyncpg://hivemind:hivemind@postgres/hivemind")
Session = sessionmaker(engine, class_=AsyncSession)


async def main():
    async with Session() as db:
        r = await db.execute(text(
            "SELECT t.task_key, s.title, s.id as skill_id, s.lifecycle "
            "FROM task_skills ts "
            "JOIN tasks t ON t.id = ts.task_id "
            "JOIN skills s ON s.id = ts.skill_id "
            "ORDER BY t.task_key LIMIT 20"
        ))
        print("=== task_skills linkages ===")
        for row in r.fetchall():
            print(f"  {row.task_key}: [{row.lifecycle}] {row.title} ({row.skill_id})")

        r2 = await db.execute(text(
            "SELECT task_key, pinned_skills "
            "FROM tasks "
            "WHERE pinned_skills IS NOT NULL AND pinned_skills::text != '[]' "
            "LIMIT 10"
        ))
        print("\n=== tasks with pinned_skills ===")
        for row in r2.fetchall():
            print(f"  {row.task_key}: {row.pinned_skills}")

        r3 = await db.execute(text(
            "SELECT id, title, lifecycle, source_slug FROM skills WHERE source_slug IS NOT NULL ORDER BY source_slug LIMIT 20"
        ))
        print("\n=== Skills mit source_slug (erste 20) ===")
        for row in r3.fetchall():
            print(f"  {row.source_slug} → [{row.lifecycle}] {row.title}")

        r4 = await db.execute(text(
            "SELECT COUNT(*) as total, COUNT(source_slug) as with_slug FROM skills WHERE lifecycle='active'"
        ))
        row = r4.fetchone()
        print(f"\n=== Skills: {row.with_slug}/{row.total} haben source_slug ===")


asyncio.run(main())
