# Hivemind

> A hybrid developer hivemind with Progressive Disclosure.  
> Starts as a manual BYOAI system ("Wizard of Oz") and scales to autonomous MCP agents — without breaking the architecture.  
> Hivemind is itself an MCP server: the AI chat reads and writes context directly.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

---

## What is Hivemind?

Hivemind is a self-hosted project and task management system designed for developers who work with AI assistants. It acts as the **command deck** for a fleet of specialized AI agents, each with a clearly defined role — from planning and architecture down to code execution, documentation and federation across peers.

The system is built around a single core principle: **you are always in control**. AI agents propose, humans review and approve. Even in fully autonomous mode (Phase 8), every action passes a review gate.

---

## Core Principles

| # | Principle | Description |
|---|-----------|-------------|
| 1 | **Progressive Disclosure** | Load only the context needed for the current task — no context bloat |
| 2 | **BYOAI → Autonomy** | Today manual, tomorrow autonomous. Same endpoints, same data contract |
| 3 | **Prompt Station** | The system tells you which agent is needed and delivers the prompt |
| 4 | **No autonomous AI execution in Phases 1–7** | AI is used manually (copy/paste prompts in your AI client). From Phase 3 onwards, the Bibliothekar automates context assembly — only the AI execution stays manual |
| 5 | **Review gate always active** | No direct `done` transition even in solo mode |
| 6 | **Sci-Fi Game HUD** | Modern, dark, game-like UI — you are the commander of an agent swarm |
| 7 | **Sovereign Nodes** | Every developer hosts their own full instance; Federation connects peers over VPN |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vue 3 + Vite + TypeScript + Reka UI + Design Tokens |
| Backend | FastAPI (Bibliothekar + Router + MCP Server in one service) |
| Database | PostgreSQL 16 + pgvector |
| Embeddings | Ollama `nomic-embed-text` (from Phase 3) — no API key required |
| Runtime | Docker Compose |
| Integrations | YouTrack, Sentry, GitLab (MCP Consumer) |

---

## Agents

| Agent | Role |
|-------|------|
| **Kartograph** | Fog-of-War Explorer, repo analysis, wiki author |
| **Stratege** | Plan → Epics, dependency mapping, roadmap planning |
| **Architekt** | Epic decomposition, tasks, context boundaries |
| **Worker** | Task execution, guard checks, result delivery |
| **Gärtner** | Skill distillation, decision records, doc updates |
| **Triage** | Event routing, proposals, dead letters, escalations |
| **Bibliothekar** | Context assembly — Phase 1–2: prompt, Phase 3+: service |

---

## Phases

| Phase | Focus |
|-------|-------|
| **1a** | Data foundation, state machine, Docker Compose |
| **1b** | Design system, Prompt Station + inline review |
| **2** | Identity & RBAC, Command Deck, login, notifications |
| **F** | Federation protocol, peer discovery, epic sharing |
| **3** | MCP read tools + Bibliothekar prompt, Ollama embeddings |
| **4** | Planner writes (Stratege & Architekt), Skill Lab |
| **5** | Worker & Gärtner writes, Wiki, Nexus Grid 2D |
| **6** | Triage & escalation, SLA UI |
| **7** | External integration hardening, Dead Letter, Bug Heatmap |
| **8** | Full autonomy, 3D Nexus Grid, Auto Mode |

---

## Quick Start

### Prerequisites

- [Podman](https://podman.io/docs/installation) + [podman-compose](https://github.com/containers/podman-compose) (or Docker + Docker Compose)
- Git
- `make`

### Run

```bash
git clone https://github.com/MumboJumbo750/hivemind.git
cd hivemind
cp .env.example .env   # adjust values as needed
make up
```

The backend will be available at `http://localhost:8000` and the frontend at `http://localhost:5173`.

### Common Dev Commands

```bash
make help              # show all available commands

make up                # start stack
make up-ai             # start stack + Ollama (Phase 3+, for embeddings)
make down              # stop stack
make logs              # stream backend logs

make migrate           # run alembic upgrade head
make test              # run all backend tests
make test-integration  # run integration tests only
make shell-be          # open bash in backend container
make db                # open psql in postgres container

make rebuild-be        # rebuild backend image (only needed after Dockerfile changes)
make rebuild-fe        # rebuild frontend image (only needed after Dockerfile changes)
```

> **Note:** Code changes take effect immediately via hot-reload — no restart needed.
> `requirements.txt` changes only need `make restart-be`, not a full rebuild.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `hivemind` | Database user |
| `POSTGRES_PASSWORD` | `hivemind` | Database password |
| `POSTGRES_DB` | `hivemind` | Database name |
| `HIVEMIND_MODE` | `solo` | `solo` or `team` |
| `HIVEMIND_TOKEN_BUDGET` | `8000` | Max tokens per context assembly |
| `HIVEMIND_ROUTING_THRESHOLD` | `0.85` | pgvector similarity threshold |
| `HIVEMIND_DLQ_MAX_ATTEMPTS` | `5` | Dead letter queue retry limit |
| `AUDIT_RETENTION_DAYS` | `90` | Audit log retention in days |

---

## Documentation

| Document | Description |
|----------|-------------|
| [masterplan.md](masterplan.md) | Full project index |
| [Architecture Overview](docs/architecture/overview.md) | Principles, stack, trust boundary |
| [REST API](docs/architecture/rest-api.md) | Frontend-backend contract, auth flow, SSE |
| [Data Model](docs/architecture/data-model.md) | Full SQL schema |
| [State Machine](docs/architecture/state-machine.md) | Task states, skill lifecycle, escalation |
| [MCP Toolset](docs/architecture/mcp-toolset.md) | All MCP tools, transports, security rules |
| [RBAC](docs/architecture/rbac.md) | Roles, permissions matrix |
| [Phase Overview](docs/phases/overview.md) | All phases with sequencing guide |
| [Agents Overview](docs/agents/overview.md) | All agents compared |
| [Glossary](docs/glossary.md) | Domain term definitions |

---

## License

This project is licensed under the **GNU Affero General Public License v3.0** — see [LICENSE](LICENSE) for details.

In short: if you run a modified version of Hivemind as a network service, you must make the modified source code available to the users of that service.
