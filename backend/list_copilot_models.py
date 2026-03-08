import asyncio, sys
sys.path.insert(0, '/app')
from app.db import AsyncSessionLocal
from app.models.ai_credential import AICredential
from app.services.ai_provider import decrypt_api_key
from app.config import settings
from sqlalchemy import select
import httpx

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AICredential))
        cred = result.scalar_one_or_none()
        if not cred or not cred.api_key_encrypted:
            print("No credential found")
            return
        token = decrypt_api_key(cred.api_key_encrypted, cred.api_key_nonce, settings.hivemind_key_passphrase)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.githubcopilot.com/models",
                headers={"Authorization": f"Bearer {token}", "Copilot-Integration-Id": "hivemind"},
                timeout=10.0
            )
            data = resp.json()
            models = data.get("data") or data
            for m in models:
                if isinstance(m, dict):
                    print(m.get("id", "?"))

asyncio.run(main())
