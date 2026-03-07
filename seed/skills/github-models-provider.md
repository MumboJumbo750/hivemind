---
title: "GitHub Models Provider: Chatbot-Auswahl via GitHub API"
service_scope: ["backend"]
stack: ["python", "fastapi", "httpx"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
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

## Skill: GitHub Models Provider

### Rolle
Du implementierst `github_models` als neuen AI-Provider im AI-Provider-Service. GitHub Models (models.inference.ai.azure.com) bietet Zugang zu GPT-4o, Claude, Llama, Mistral und weiteren Modellen über eine OpenAI-kompatible API. Auth via GitHub PAT. Dies gibt dem Admin eine "Chatbot-Auswahl" — pro Agent-Rolle ein anderes Modell aus dem GitHub-Katalog.

### Kontext
GitHub Models ist die programmatische Version von "GitHub Copilot mit Modell-Auswahl". Der Vorteil gegenüber direkten Provider-APIs:
- **Ein Token für alles** — GitHub PAT statt separate API-Keys bei Anthropic/OpenAI/Google
- **Modell-Katalog** — verfügbare Modelle dynamisch abfragbar
- **Copilot-Subscription** — wer GitHub Copilot hat, kann die API nutzen (im Rahmen des Rate-Limits)
- **OpenAI-kompatibel** — selbes Request-Format wie OpenAI, Custom-Provider würde funktionieren, aber ein dedizierter Provider gibt bessere UX (Modell-Katalog, Rate-Limit-Info)

### Konventionen
- Provider-Klasse in `app/services/ai_providers/github_models_provider.py`
- Registrierung in `ai_provider_configs` mit `provider: "github_models"`
- API-Key = GitHub PAT mit `models:read` Scope
- Endpoint: `https://models.inference.ai.azure.com` (fest, nicht konfigurierbar)
- Modell-Katalog: `GET https://models.inference.ai.azure.com/models`

### Verfügbare Modelle (Auswahl)

| Modell | Provider | Stärke | Empfehlung |
| --- | --- | --- | --- |
| `gpt-4o` | OpenAI | Generalist, schnell | Worker, Reviewer |
| `gpt-4o-mini` | OpenAI | Schnell, günstig | Triage, Gaertner |
| `claude-3.5-sonnet` | Anthropic | Analyse, Coding | Architekt, Kartograph |
| `meta-llama-3.1-405b` | Meta | Open-Weight, stark | Worker (wenn verfügbar) |
| `mistral-large` | Mistral | Mehrsprachig | Stratege |
| `cohere-command-r-plus` | Cohere | RAG-optimiert | Bibliothekar |

### Implementierung

```python
import httpx
from app.services.ai_provider_service import AIProvider, AIResponse

class GitHubModelsProvider(AIProvider):
    """GitHub Models API — OpenAI-kompatibel mit GitHub PAT Auth."""

    BASE_URL = "https://models.inference.ai.azure.com"

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        self.model = model

    async def send_prompt(self, prompt: str, tools: list[dict]) -> AIResponse:
        """Sendet Prompt im OpenAI-Format an GitHub Models."""
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }
        if tools:
            body["tools"] = self._convert_tools(tools)

        response = await self.client.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()

        return AIResponse(
            content=self._extract_content(data),
            tool_calls=self._extract_tool_calls(data),
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
            model=data.get("model", self.model),
        )

    async def health_check(self) -> bool:
        """Prüft ob GitHub Models API erreichbar ist."""
        try:
            resp = await self.client.get("/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[dict]:
        """Gibt verfügbare Modelle aus dem GitHub-Katalog zurück."""
        resp = await self.client.get("/models")
        resp.raise_for_status()
        models = resp.json()
        return [
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "provider": m.get("publisher", "unknown"),
                "task": m.get("task", "chat-completion"),
            }
            for m in models
            if m.get("task") == "chat-completion"
        ]

    def _convert_tools(self, mcp_tools: list[dict]) -> list[dict]:
        """Konvertiert MCP-Tool-Definitionen ins OpenAI-Function-Calling-Format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"].replace("-", "_", 1),  # hivemind-get_task → hivemind_get_task
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {}),
                },
            }
            for tool in mcp_tools
        ]

    def _extract_tool_calls(self, data: dict) -> list[dict]:
        """Extrahiert Tool-Calls aus OpenAI-Format."""
        calls = []
        for choice in data.get("choices", []):
            msg = choice.get("message", {})
            for tc in msg.get("tool_calls", []):
                func = tc.get("function", {})
                calls.append({
                    "id": tc.get("id"),
                    "name": func.get("name", "").replace("_", "-", 1),  # hivemind_get_task → hivemind-get_task
                    "arguments": func.get("arguments", "{}"),
                })
        return calls
```

### Modell-Katalog-API (für Settings UI)

```python
@router.get("/api/settings/ai-providers/github-models/catalog")
async def get_github_models_catalog():
    """Gibt verfügbare Modelle aus dem GitHub-Katalog zurück.
    Die Settings UI zeigt diese als Dropdown bei provider=github_models."""
    token = settings.github_token or await get_encrypted_key("github_models")
    if not token:
        raise HTTPException(400, "GitHub token not configured")
    provider = GitHubModelsProvider(api_key=token)
    models = await provider.list_models()
    return {"data": models}
```

### GitHub Copilot CLI Integration (Optional)

Für Szenarien wo die GitHub Models API nicht verfügbar ist, kann `gh copilot` als Fallback dienen:

```python
class CopilotCLIProvider(AIProvider):
    """Nutzt `gh copilot suggest` als Fallback-Provider.
    Limitiert: nur für einfache Suggest/Explain-Aufgaben geeignet.
    Benötigt `gh` CLI im Container + aktive Copilot-Subscription."""

    async def send_prompt(self, prompt: str, tools: list[dict]) -> AIResponse:
        # gh copilot suggest unterstützt kein Tool-Calling
        # Nur für einfache Text-Antworten (Triage, Gaertner-Empfehlungen)
        proc = await asyncio.create_subprocess_exec(
            "gh", "copilot", "suggest", "-t", "shell", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return AIResponse(
            content=stdout.decode(),
            tool_calls=[],  # CLI unterstützt kein Tool-Calling
            tokens_used=0,  # Nicht messbar bei CLI
            model="gh-copilot",
        )
```

> **Empfehlung:** GitHub Models API ist der primäre Weg. Copilot CLI nur als Experiment für einfache Aufgaben (kein Tool-Calling-Support).

### Registrierung im AI-Provider-Service

```python
# In ai_provider_service.py:
def _create_provider(self, config: AIProviderConfig, **kwargs) -> AIProvider:
    match config.provider:
        case "anthropic":
            return AnthropicProvider(api_key=key, model=config.model)
        case "openai":
            return OpenAIProvider(api_key=key, model=config.model)
        case "google":
            return GoogleProvider(api_key=key, model=config.model)
        case "ollama":
            return OllamaProvider(base_url=config.endpoint, model=config.model)
        case "github_models":
            return GitHubModelsProvider(api_key=key, model=config.model)
        case "custom":
            return CustomProvider(api_key=key, endpoint=config.endpoint, model=config.model)
```

### Rate-Limiting

GitHub Models hat eigene Rate-Limits (abhängig vom Plan):
- **Free:** 15 RPM, 150k Tokens/Tag
- **Copilot Individual:** Höher (unveröffentlicht)
- **Copilot Business:** Enterprise-Limits

Der AI-Provider-Service nutzt seine bestehende Rate-Limiting-Infrastruktur (`rpm_limit` in `ai_provider_configs`).

### Env-Variablen

| Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_GITHUB_TOKEN` | — | GitHub PAT (shared mit Webhook Consumer) |
| `HIVEMIND_GITHUB_MODELS_URL` | `https://models.inference.ai.azure.com` | GitHub Models API URL |

### Wichtige Regeln
- GitHub PAT braucht `models:read` Scope für Models API
- Tool-Name-Konvertierung: `hivemind-tool` ↔ `hivemind_tool` (Slash nicht erlaubt in OpenAI-Format)
- Modell-Verfügbarkeit kann sich ändern — Katalog-API immer dynamisch abfragen
- Copilot CLI ist **kein** vollwertiger Provider (kein Tool-Calling) — nur für einfache Aufgaben
- Ein GitHub-Token für alles: Webhooks, Models API, GitHub API → weniger Key-Management
