---
title: "AI-Provider-Service: Multi-Provider-Abstraktion & Per-Role-Routing"
service_scope: ["backend"]
stack: ["python", "fastapi", "httpx", "cryptography", "sqlalchemy"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100", "cryptography": ">=41.0" }
confidence: 0.5
source_epics: ["EPIC-PHASE-8"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: AI-Provider-Service

### Rolle
Du implementierst den AI-Provider-Service — die zentrale Abstraktion für AI-API-Calls im Auto-Modus (Phase 8). Der Service sendet generierte Prompts direkt an konfigurierte AI-Provider und empfängt MCP-Tool-Calls als Antwort. Jede Agent-Rolle kann einen eigenen Provider nutzen.

### Konventionen
- Service in `app/services/ai_provider_service.py`
- Provider-Interface: `AIProvider` ABC mit `send_prompt(prompt, tools) -> AIResponse`
- Konkrete Provider: `AnthropicProvider`, `OpenAIProvider`, `GoogleProvider`, `OllamaProvider`, `CustomProvider`
- Per-Role-Konfiguration via `ai_provider_configs`-Tabelle (→ data-model.md)
- Fallback-Kaskade: `ai_provider_configs[rolle]` → `app_settings.ai_provider` (Global) → BYOAI-Modus (kein API-Call)
- CustomProvider: beliebiger OpenAI-kompatibler Endpoint (z.B. vLLM, LiteLLM)

### Provider-Konfiguration (Datenmodell)

```python
# ai_provider_configs Tabelle
class AIProviderConfig(Base):
    __tablename__ = "ai_provider_configs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_role: Mapped[str] = mapped_column(String(50), unique=True)  # kartograph, stratege, architekt, worker, gaertner, triage, reviewer
    provider: Mapped[str] = mapped_column(String(50))  # anthropic, openai, google, ollama, custom
    model: Mapped[str] = mapped_column(String(100))  # claude-sonnet-4-20250514, gpt-4o, gemini-2.0-flash, etc.
    endpoint: Mapped[str | None] = mapped_column(String(500))  # Custom/Ollama endpoint URL
    enabled: Mapped[bool] = mapped_column(default=True)
    rpm_limit: Mapped[int | None] = mapped_column()  # Requests per Minute
    tpm_limit: Mapped[int | None] = mapped_column()  # Tokens per Minute
    token_budget: Mapped[int | None] = mapped_column()  # Max tokens per prompt
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    api_key_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    endpoints: Mapped[dict | None] = mapped_column(JSONB)  # Worker-Endpoint-Pool (Phase 8 optional)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

### Provider-Abstraktion

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class AIResponse:
    content: str
    tool_calls: list[dict]  # MCP-Tool-Calls die die AI ausführen will
    tokens_used: int
    model: str

class AIProvider(ABC):
    @abstractmethod
    async def send_prompt(self, prompt: str, tools: list[dict]) -> AIResponse:
        """Sendet Prompt an AI-API und gibt strukturierte Antwort zurück."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Prüft ob der Provider erreichbar ist."""
        ...

class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = httpx.AsyncClient(
            base_url="https://api.anthropic.com/v1",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=120.0,
        )
        self.model = model

    async def send_prompt(self, prompt: str, tools: list[dict]) -> AIResponse:
        response = await self.client.post("/messages", json={
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
            "tools": tools,
        })
        response.raise_for_status()
        data = response.json()
        return self._parse_response(data)

class OllamaProvider(AIProvider):
    def __init__(self, base_url: str = "http://ollama:11434", model: str = "llama3"):
        self.client = httpx.AsyncClient(base_url=base_url, timeout=300.0)
        self.model = model

    async def send_prompt(self, prompt: str, tools: list[dict]) -> AIResponse:
        response = await self.client.post("/api/chat", json={
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "tools": tools,
            "stream": False,
        })
        response.raise_for_status()
        data = response.json()
        return self._parse_response(data)
```

### API-Key-Verschlüsselung (AES-256-GCM)

```python
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

def derive_api_key_encryption_key(passphrase: str) -> bytes:
    """Leitet AES-256-Schlüssel aus HIVEMIND_KEY_PASSPHRASE ab (HKDF-SHA256)."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"hivemind-api-key-encryption",  # Fester Salt für diesen Kontext
        info=b"api-key-aes-256-gcm",
    ).derive(passphrase.encode())

def encrypt_api_key(plaintext: str, passphrase: str) -> tuple[bytes, bytes]:
    """Verschlüsselt API-Key. Gibt (ciphertext, nonce) zurück."""
    key = derive_api_key_encryption_key(passphrase)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit Nonce für GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return ciphertext, nonce

def decrypt_api_key(ciphertext: bytes, nonce: bytes, passphrase: str) -> str:
    """Entschlüsselt API-Key. Nur im Speicher beim aktiven API-Call."""
    key = derive_api_key_encryption_key(passphrase)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()
```

### Rate-Limiting & Retry

- Retry: Exponential Backoff (1s → 2s → 4s → max 60s), max 3 Versuche bei HTTP 429 / 503
- RPM/TPM pro Agent-Rolle konfigurierbar: `rpm_limit`, `tpm_limit` in `ai_provider_configs`
- Token Bucket pro Agent-Rolle (nicht pro Dispatch)
- Bei Überschreitung: `await asyncio.sleep(backoff)` — kein Fehler, keine externe Queue
- Backoff: `60s / rpm_limit` (z.B. bei 10 RPM: 6s zwischen Requests)

```python
import asyncio
import time
from collections import defaultdict

class RateLimiter:
    def __init__(self):
        self._buckets: dict[str, float] = defaultdict(float)  # role → last_request_time
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, role: str, rpm_limit: int | None):
        if not rpm_limit:
            return
        async with self._locks[role]:
            min_interval = 60.0 / rpm_limit
            now = time.monotonic()
            wait = self._buckets[role] + min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._buckets[role] = time.monotonic()

async def send_with_retry(provider: AIProvider, prompt: str, tools: list[dict], max_retries: int = 3) -> AIResponse:
    for attempt in range(max_retries + 1):
        try:
            return await provider.send_prompt(prompt, tools)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 503) and attempt < max_retries:
                backoff = min(2 ** attempt, 60)
                await asyncio.sleep(backoff)
                continue
            raise
```

### Routing-Logik (Kern-Service)

```python
class AIProviderService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.rate_limiter = RateLimiter()

    async def send(self, agent_role: str, prompt: str, tools: list[dict]) -> AIResponse | None:
        """Sendet Prompt an den konfigurierten Provider für die Agent-Rolle."""
        # 1. Per-Role-Config lookup
        config = await self._get_config(agent_role)

        if not config or not config.enabled:
            # 2. Global-Fallback
            config = await self._get_global_config()

        if not config:
            return None  # BYOAI-Fallback — kein API-Call

        # 3. Rate-Limiting
        await self.rate_limiter.acquire(agent_role, config.rpm_limit)

        # 4. Provider instanziieren + API-Key entschlüsseln
        provider = self._create_provider(config)

        # 5. Send mit Retry
        return await send_with_retry(provider, prompt, tools)
```

### Token-Counting-Kalibrierung

```python
import tiktoken

# Default: cl100k_base für alle Provider (ausreichend genau)
_encoding = tiktoken.get_encoding("cl100k_base")

# Kalibrierungsfaktoren pro Provider (via HIVEMIND_TOKEN_COUNT_CALIBRATION)
DEFAULT_CALIBRATION = {"anthropic": 1.05, "openai": 1.0, "google": 1.1, "ollama": 1.0}

def count_tokens(text: str, provider: str = "openai") -> int:
    base_count = len(_encoding.encode(text))
    calibration = settings.token_count_calibration.get(provider, 1.0)
    return int(base_count * calibration)
```

### Env-Variablen

| Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_AI_API_KEY` | — | Global-Fallback API-Key (Env-Var statt DB) |
| `HIVEMIND_AI_RPM_LIMIT` | `10` | Default RPM-Limit (global) |
| `HIVEMIND_AI_TPM_LIMIT` | `100000` | Default TPM-Limit (global) |
| `HIVEMIND_KEY_PASSPHRASE` | — | Passphrase für AES-256-GCM Key-Derivation |
| `HIVEMIND_TOKEN_COUNT_CALIBRATION` | `{}` | JSON: Provider-spezifische Token-Count-Faktoren |
| `HIVEMIND_ENFORCE_TLS` | `false` | Warnung wenn API-Keys ohne TLS übertragen werden |

### Wichtige Regeln
- API-Keys **nie** im Plaintext in der DB speichern — immer AES-256-GCM
- Entschlüsselter Key sofort nach API-Call aus dem Speicher löschen (del)
- Gleicher Prompt wie bisher — kein Unterschied für MCP-Tools
- Provider-spezifische Fehler sauber auf `AIProviderError` mappen
- Jeder API-Call wird in `conductor_dispatches` geloggt (Audit-Trail)
