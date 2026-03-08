import asyncio, sys, traceback
sys.path.insert(0, '/app')
from app.db import AsyncSessionLocal
from app.services.ai_provider import get_provider
from app.services.conductor import conductor
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        try:
            prompt = await conductor._build_prompt(
                db,
                trigger_id="TASK-AGENT-003",
                trigger_detail="epic_run_scheduler:ready->in_progress",
                trigger_type="task_state",
                agent_role="worker",
                prompt_type="worker_implement",
                thread_context=None,
            )
            print(f"Prompt length: {len(prompt)} chars / ~{len(prompt)//4} tokens")

            provider = await get_provider("worker", db)
            from app.services.agentic_dispatch import _get_mcp_tools_as_dicts, _filter_tools_for_agent, _build_system_prompt
            all_tools = _get_mcp_tools_as_dicts()
            tools = _filter_tools_for_agent(all_tools, "worker")
            print(f"Tools: {len(tools)}")
            for t in tools:
                oai_name = t["name"].replace("/", "__").replace("-", "_")
                if len(oai_name) > 64:
                    print(f"  LONG NAME ({len(oai_name)}): {oai_name}")

            response = await provider.send_messages(
                messages=[{"role": "user", "content": prompt}],
                tools=tools if tools else None,
                system=_build_system_prompt("worker", "TASK-AGENT-003"),
            )
            print(f"SUCCESS! Model: {response.model}, content[:100]: {str(response.content)[:100]}")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

asyncio.run(main())
