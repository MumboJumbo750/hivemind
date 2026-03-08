import asyncio, sys, traceback
sys.path.insert(0, '/app')
from app.db import AsyncSessionLocal
from app.services.ai_provider import get_provider
from app.services.agentic_dispatch import _get_mcp_tools_as_dicts, _filter_tools_for_agent

async def main():
    async with AsyncSessionLocal() as db:
        try:
            provider = await get_provider("worker", db)
            all_tools = _get_mcp_tools_as_dicts()
            tools = _filter_tools_for_agent(all_tools, "worker")
            print(f"Tools count: {len(tools)}")
            if tools:
                print(f"First tool: {tools[0]['name']}")

            response = await provider.send_messages(
                messages=[{"role": "user", "content": "Just say hello."}],
                tools=tools,
                system="You are a helpful assistant.",
            )
            print(f"SUCCESS! Content: {response.content[:100] if response.content else None}")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

asyncio.run(main())
