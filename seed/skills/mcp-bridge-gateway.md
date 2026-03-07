---
title: "MCP Bridge / Gateway: MCP-zu-MCP Kommunikation"
service_scope: ["backend"]
stack: ["python", "fastapi", "mcp"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100", "mcp": ">=1.0" }
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

## Skill: MCP Bridge / Gateway

### Rolle
Du implementierst den MCP Bridge / Gateway — das zentrale Konzept, das Hivemind zum **Meta-MCP** macht. Hivemind ist gleichzeitig MCP-Server (für AI-Agents) UND MCP-Client (zu externen MCP-Servern). Agents erhalten damit Tools aus mehreren MCP-Welten über eine einzige Schnittstelle.

### Kontext

**Problem:** Hivemind hat eigene MCP-Tools (`hivemind-*`). GitHub hat einen MCP-Server (`@modelcontextprotocol/server-github`), GitLab ebenso. Ein AI-Agent soll Tools aus allen Quellen nutzen können — ohne separate Konfiguration pro MCP-Server.

**Lösung: MCP Gateway Pattern**

```
AI Agent  (Claude, GPT-4o, Llama, etc.)
    │
    │ MCP Protocol (tools/call)
    ▼
┌─────────────────────────────────────────┐
│  Hivemind MCP Server (Gateway)          │
│                                         │
│  hivemind-* tools  → lokaler Handler    │
│  github/* tools    → Proxy → GitHub MCP │
│  gitlab/* tools    → Proxy → GitLab MCP │
│  slack/* tools     → Proxy → Slack MCP  │
│                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │ RBAC    │  │ Audit   │  │ Rate    │ │
│  │ Check   │  │ Log     │  │ Limit   │ │
│  └─────────┘  └─────────┘  └─────────┘ │
└─────────┬───────────┬───────────┬───────┘
          │           │           │
     stdio/SSE   stdio/SSE   stdio/SSE
          │           │           │
    ┌─────┴─────┐ ┌───┴───┐ ┌────┴────┐
    │GitHub MCP │ │GitLab │ │Slack MCP│
    │Server     │ │MCP    │ │Server   │
    └───────────┘ └───────┘ └─────────┘
```

Hivemind agiert als **Proxy mit Layer** — jeder Tool-Call durchläuft RBAC, Audit und Rate-Limiting, bevor er an den externen MCP-Server weitergeleitet wird.

### Konventionen
- Service: `app/services/mcp_bridge.py`
- Model: `app/models/mcp_bridge.py`
- Schema: `app/schemas/mcp_bridge.py`
- Namespace-Prefix: externe Tools werden unter ihrem Bridge-Namespace registriert (`github/create_issue`, `gitlab/get_pipeline`)
- Hivemind-eigene Tools bleiben unter `hivemind-*`
- Kein Tool-Name-Kollision möglich durch Namespace-Trennung

### Datenmodell

```python
from sqlalchemy import String, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from uuid import UUID, uuid4
from app.db.base import Base

class MCPBridgeConfig(Base):
    """Konfiguration für eine Verbindung zu einem externen MCP-Server."""
    __tablename__ = "mcp_bridge_configs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)  # "github", "gitlab", "slack"
    namespace: Mapped[str] = mapped_column(String(50), unique=True)  # Tool-Prefix: "github", "gitlab"
    transport: Mapped[str] = mapped_column(String(20))  # "stdio" | "sse" | "http"

    # stdio transport
    command: Mapped[str | None] = mapped_column(String(500))
    # Beispiel: "npx @modelcontextprotocol/server-github"
    args: Mapped[list | None] = mapped_column(JSON)
    # Beispiel: ["--token", "***"]

    # sse/http transport
    url: Mapped[str | None] = mapped_column(String(500))
    # Beispiel: "http://localhost:3100/sse"

    # Environment-Variablen für den externen MCP-Server (AES-256-GCM encrypted)
    env_vars_encrypted: Mapped[bytes | None] = mapped_column()
    # Beispiel: {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_***"}

    enabled: Mapped[bool] = mapped_column(default=True)
    tool_allowlist: Mapped[list | None] = mapped_column(JSON)
    # null = alle Tools proxyen, Liste = nur diese Tools
    tool_blocklist: Mapped[list | None] = mapped_column(JSON)
    # Liste von Tool-Namen die NICHT proxied werden (z.B. dangerous_delete_*)

    # Cached tool catalog (wird beim Connect aktualisiert)
    discovered_tools: Mapped[dict | None] = mapped_column(JSON)
    # {"create_issue": {"description": "...", "inputSchema": {...}}, ...}

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

### MCP-Client (Bridge Connection)

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

class MCPBridge:
    """Verbindung zu einem externen MCP-Server (als Client)."""

    def __init__(self, config: MCPBridgeConfig):
        self.config = config
        self.session: ClientSession | None = None
        self._tools: dict[str, dict] = {}

    async def connect(self):
        """Verbindung herstellen und Tool-Katalog laden."""
        match self.config.transport:
            case "stdio":
                params = StdioServerParameters(
                    command=self.config.command,
                    args=self.config.args or [],
                    env=self._decrypt_env_vars(),
                )
                self._transport = await stdio_client(params).__aenter__()
            case "sse":
                self._transport = await sse_client(
                    url=self.config.url,
                    headers=self._auth_headers(),
                ).__aenter__()
            case _:
                raise ValueError(f"Unsupported transport: {self.config.transport}")

        read, write = self._transport
        self.session = ClientSession(read, write)
        await self.session.initialize()

        # Tool-Katalog laden
        tools_result = await self.session.list_tools()
        for tool in tools_result.tools:
            if self._is_tool_allowed(tool.name):
                self._tools[tool.name] = {
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
        logger.info(f"MCP Bridge '{self.config.name}': {len(self._tools)} tools discovered")

    def _is_tool_allowed(self, tool_name: str) -> bool:
        """Prüft ob Tool gemäß Allow-/Blocklist proxied werden darf."""
        if self.config.tool_blocklist and tool_name in self.config.tool_blocklist:
            return False
        if self.config.tool_allowlist and tool_name not in self.config.tool_allowlist:
            return False
        return True

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Ruft ein Tool auf dem externen MCP-Server auf."""
        if not self.session:
            raise MCPBridgeError(f"Bridge '{self.config.name}' not connected")
        if tool_name not in self._tools:
            raise MCPBridgeError(f"Tool '{tool_name}' not available on '{self.config.name}'")

        result = await self.session.call_tool(tool_name, arguments)
        return result

    @property
    def namespaced_tools(self) -> dict[str, dict]:
        """Gibt Tools mit Namespace-Prefix zurück."""
        return {
            f"{self.config.namespace}/{name}": schema
            for name, schema in self._tools.items()
        }
```

### Gateway (Tool-Registry + Proxy-Dispatcher)

```python
class MCPGateway:
    """Zentrale Registry: verwaltet lokale + proxied Tools."""

    def __init__(self):
        self._bridges: dict[str, MCPBridge] = {}  # namespace → bridge
        self._local_tools: dict[str, Callable] = {}  # hivemind-* tools

    async def startup(self, db: AsyncSession):
        """Alle konfigurierten Bridges starten."""
        configs = await db.execute(
            select(MCPBridgeConfig).where(MCPBridgeConfig.enabled == True)
        )
        for config in configs.scalars():
            bridge = MCPBridge(config)
            try:
                await bridge.connect()
                self._bridges[config.namespace] = bridge
                logger.info(f"Bridge '{config.name}' connected: {len(bridge.namespaced_tools)} tools")
            except Exception as e:
                logger.error(f"Bridge '{config.name}' failed to connect: {e}")

    def register_local_tool(self, name: str, handler: Callable):
        """Lokales Hivemind-Tool registrieren."""
        self._local_tools[name] = handler

    @property
    def all_tools(self) -> dict[str, dict]:
        """Alle verfügbaren Tools (lokal + proxied)."""
        tools = {}
        # Lokale Tools
        for name, handler in self._local_tools.items():
            tools[f"hivemind-{name}"] = {
                "description": handler.__doc__,
                "inputSchema": handler.input_schema,
            }
        # Proxied Tools
        for bridge in self._bridges.values():
            tools.update(bridge.namespaced_tools)
        return tools

    async def dispatch(self, full_tool_name: str, arguments: dict, context: ToolContext) -> Any:
        """Tool-Call dispatchen — lokal oder via Bridge."""
        namespace, _, tool_name = full_tool_name.partition("/")

        # 1. RBAC prüfen
        if not await self._check_rbac(context.agent_role, full_tool_name):
            raise PermissionError(f"Agent role '{context.agent_role}' cannot use '{full_tool_name}'")

        # 2. Audit-Log schreiben (IMMER — auch für proxied Calls)
        audit_entry = await self._create_audit_entry(full_tool_name, arguments, context)

        # 3. Dispatchen
        try:
            if namespace == "hivemind":
                result = await self._local_tools[tool_name](arguments, context)
            elif namespace in self._bridges:
                result = await self._bridges[namespace].call_tool(tool_name, arguments)
            else:
                raise MCPBridgeError(f"Unknown namespace: '{namespace}'")

            audit_entry.success = True
            return result
        except Exception as e:
            audit_entry.success = False
            audit_entry.error = str(e)
            raise
        finally:
            await self._save_audit_entry(audit_entry)
```

### Tool-Auflösung für Agents

Wenn der Conductor einen Agent dispatcht, erhält dieser eine Tool-Liste basierend auf:
1. Agent-Rolle (Worker, Tester, Reviewer, etc.)
2. Governance-Level (manuelle Einschränkung möglich)
3. Bridge-Konfiguration (welche Bridges sind aktiv)

```python
class ConductorToolResolver:
    """Bestimmt welche Tools ein Agent haben darf."""

    ROLE_TOOLS = {
        "worker": [
            "hivemind-get_task",
            "hivemind-submit_result",
            "hivemind-update_task_state",
            "github/get_file_contents",    # ← Proxied!
            "github/create_branch",         # ← Proxied!
            "github/push_files",            # ← Proxied!
            "github/create_pull_request",   # ← Proxied!
        ],
        "reviewer": [
            "hivemind-get_task",
            "hivemind-submit_review_recommendation",
            "github/get_file_contents",
            "github/list_commits",
            "github/get_pull_request",
        ],
        "tester": [
            "hivemind-get_task",
            "hivemind-report_guard_result",
            "github/get_file_contents",
            "github/search_code",
        ],
    }
```

### Agent-Workflow Beispiel (Worker mit GitHub Tools)

```
Worker Agent erhält Prompt:
  "Implementiere Feature X. Nutze Branch feature/TASK-42."

1. hivemind-get_task {"task_key": "TASK-42"}
   → {title, description, acceptance_criteria, ...}

2. github/get_file_contents {"owner": "acme", "repo": "app", "path": "src/feature.py"}
   → Bestehender Code

3. (AI generiert Änderungen)

4. github/create_branch {"owner": "acme", "repo": "app", "branch": "feature/TASK-42"}
   → Branch erstellt

5. github/push_files {"owner": "acme", "repo": "app", "branch": "feature/TASK-42", "files": [...]}
   → Code gepusht

6. github/create_pull_request {
     "owner": "acme", "repo": "app",
     "title": "[TASK-42] Feature X",
     "body": "Implements Feature X\n\nHivemind Task: TASK-42",
     "head": "feature/TASK-42",
     "base": "main"
   }
   → PR #123 erstellt

7. hivemind-submit_result {
     "task_key": "TASK-42",
     "result": "Feature X implemented. PR #123 created.",
     "artifacts": [{"type": "github_pr", "url": "https://github.com/acme/app/pull/123"}]
   }

8. hivemind-update_task_state {"task_key": "TASK-42", "target_state": "in_review"}
```

### Beispiel-Konfigurationen

```python
# GitHub MCP Server (stdio)
MCPBridgeConfig(
    name="github",
    namespace="github",
    transport="stdio",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"],
    env_vars_encrypted=encrypt({"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_***"}),
    enabled=True,
    tool_allowlist=None,  # Alle GitHub-Tools verfügbar
    tool_blocklist=["delete_repository"],  # Aber kein Repo-Delete!
)

# GitLab MCP Server (stdio)
MCPBridgeConfig(
    name="gitlab",
    namespace="gitlab",
    transport="stdio",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-gitlab"],
    env_vars_encrypted=encrypt({"GITLAB_ACCESS_TOKEN": "glpat-***"}),
    enabled=True,
    tool_allowlist=["get_project", "get_merge_request", "list_pipelines"],
    tool_blocklist=None,
)

# Eigener MCP Server (SSE)
MCPBridgeConfig(
    name="internal-tools",
    namespace="internal",
    transport="sse",
    url="http://internal-mcp:3100/sse",
    enabled=True,
)
```

### Tool-Name-Konversion

MCP-Protokoll erlaubt keine `/` in Tool-Namen. Konversion:

```python
def to_mcp_tool_name(namespaced: str) -> str:
    """'github/create_issue' → 'github__create_issue'"""
    return namespaced.replace("/", "__")

def from_mcp_tool_name(mcp_name: str) -> str:
    """'github__create_issue' → 'github/create_issue'"""
    return mcp_name.replace("__", "/", 1)
```

### API-Endpoints

```python
@router.get("/api/admin/mcp-bridges")
async def list_bridges(db: AsyncSession = Depends(get_db)):
    """Alle konfigurierten MCP-Bridges auflisten."""
    ...

@router.post("/api/admin/mcp-bridges")
async def create_bridge(config: MCPBridgeCreate, db: AsyncSession = Depends(get_db)):
    """Neue MCP-Bridge konfigurieren."""
    ...

@router.post("/api/admin/mcp-bridges/{bridge_id}/test")
async def test_bridge(bridge_id: UUID, db: AsyncSession = Depends(get_db)):
    """Bridge-Verbindung testen und Tool-Katalog aktualisieren."""
    ...

@router.get("/api/admin/mcp-bridges/{bridge_id}/tools")
async def list_bridge_tools(bridge_id: UUID, db: AsyncSession = Depends(get_db)):
    """Verfügbare Tools einer Bridge auflisten."""
    ...
```

### Sicherheits-Architektur

| Layer | Schutzmaßnahme |
| --- | --- |
| **Namespace-Isolation** | Namespaces sind unique — keine Tool-Kollision möglich |
| **Tool Allow/Blocklist** | Admin kontrolliert welche externen Tools verfügbar sind |
| **RBAC per Tool** | Nur Rollen mit Berechtigung dürfen bestimmte Tools nutzen |
| **Audit Trail** | JEDER proxied Call wird geloggt (Tool, Arguments, Result, Agent, Timestamp) |
| **Rate Limiting** | Per Bridge + per Agent-Rolle konfigurierbar |
| **Credential Isolation** | Env-Vars AES-256-GCM encrypted — Agent sieht nie den Token |
| **No Credential Forwarding** | Agent-Prompt enthält NIE Credentials — nur via Backend-Proxy |

### Health-Check

```python
async def check_bridges_health() -> dict:
    """Regelmäßig Bridge-Verbindungen prüfen."""
    return {
        namespace: {
            "connected": bridge.session is not None,
            "tools_count": len(bridge._tools),
            "last_call": bridge.last_call_at,
            "error_rate": bridge.error_rate_1h,
        }
        for namespace, bridge in gateway._bridges.items()
    }
```

### Wichtige Regeln
- **Agents sehen NIE Credentials** — alle externen API-Calls laufen durch den Backend-Proxy
- **Audit Trail ist Pflicht** — jeder proxied Tool-Call wird geloggt, auch erfolgreiche
- **Tool-Blocklist für gefährliche Operationen** — z.B. `delete_repository` IMMER blocken
- **Namespace `hivemind` ist reserviert** — kann nicht als Bridge-Namespace verwendet werden
- **Graceful Degradation** — wenn eine Bridge ausfällt, funktionieren lokale Tools weiterhin
- **Tool-Katalog cachen** — nicht bei jedem Tool-Call neu laden, nur bei Connect + manuell
- **Env-Vars verschlüsseln** — selbes Pattern wie `ai_provider_configs` (AES-256-GCM, `HIVEMIND_KEY_PASSPHRASE`)
