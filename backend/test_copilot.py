import asyncio, sys
sys.path.insert(0, '/app')
from app.db import AsyncSessionLocal
from app.models.ai_credential import AICredential
from app.services.ai_provider import decrypt_api_key
from app.config import settings
from sqlalchemy import select
import httpx, json

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AICredential))
        cred = result.scalar_one_or_none()
        token = decrypt_api_key(cred.api_key_encrypted, cred.api_key_nonce, settings.hivemind_key_passphrase)
        print(f"Token prefix: {token[:10]}...")

        # Simple test WITHOUT tools
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.githubcopilot.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Copilot-Integration-Id": "hivemind",
                    "Content-Type": "application/json",
                },
                json={"model": "claude-sonnet-4.6", "messages": [{"role": "user", "content": "Say hello"}], "max_tokens": 20},
                timeout=15.0,
            )
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text[:300]}")

asyncio.run(main())
