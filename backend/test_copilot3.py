import asyncio, sys, traceback
sys.path.insert(0, '/app')
from app.db import AsyncSessionLocal
from app.models.ai_credential import AICredential
from app.services.ai_provider import decrypt_api_key, get_provider
from app.config import settings
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        try:
            provider = await get_provider("worker", db)
            print(f"Provider: {type(provider).__name__}")
            print(f"Default model: {provider.default_model()}")

            # Minimal test like agentic_dispatch
            response = await provider.send_messages(
                messages=[{"role": "user", "content": "Say hello in one word."}],
                tools=None,
                system="You are a helpful assistant.",
            )
            print(f"SUCCESS! Content: {response.content}")
            print(f"Model: {response.model}")
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()

asyncio.run(main())
