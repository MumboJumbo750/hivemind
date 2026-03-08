import asyncio, sys
sys.path.insert(0, '/app')
from app.db import AsyncSessionLocal
from app.models.ai_credential import AICredential
from app.services.ai_provider import decrypt_api_key
from app.config import settings
from sqlalchemy import select
import httpx, json

SIMPLE_TOOL = {
    "type": "function",
    "function": {
        "name": "test_tool",
        "description": "A test tool",
        "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
    },
}

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AICredential))
        cred = result.scalar_one_or_none()
        token = decrypt_api_key(cred.api_key_encrypted, cred.api_key_nonce, settings.hivemind_key_passphrase)

        async with httpx.AsyncClient() as client:
            # Test WITH tools
            resp = await client.post(
                "https://api.githubcopilot.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Copilot-Integration-Id": "hivemind",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4.6",
                    "messages": [{"role": "user", "content": "Say hello, use the test_tool with x='hi'"}],
                    "tools": [SIMPLE_TOOL],
                    "max_tokens": 50,
                },
                timeout=15.0,
            )
            print(f"WITH tools: {resp.status_code}")
            print(resp.text[:400])

asyncio.run(main())
