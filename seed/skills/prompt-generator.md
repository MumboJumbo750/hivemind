---
title: "Prompt-Generator & Templates"
service_scope: ["backend"]
stack: ["python", "fastapi", "jinja2"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.5
source_epics: ["EPIC-PHASE-3"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Prompt-Generator & Templates

### Rolle
Du implementierst den Prompt-Generator-Service — das Herzstück der Agent-Prompt-Erzeugung. Der Service generiert kontextspezifische Prompts für alle Agenten (Bibliothekar, Worker, Kartograph, Architekt, Stratege, Gärtner, Triage, Review) und schreibt jeden generierten Prompt in die `prompt_history`.

### Konventionen
- Service in `app/services/prompt_generator.py`
- MCP-Tool: `hivemind/get_prompt { "type": "<agent>", "task_id": "TASK-88" }`
- Prompt-Templates sind Skills mit `lifecycle='active'` — versioniert und austauschbar
- Jeder `get_prompt`-Aufruf schreibt einen `prompt_history`-Eintrag:
  - `agent_type`, `prompt_type`, `prompt_text`, `token_count`, `generated_by`
- Token-Counting mit `tiktoken` (cl100k_base Encoding) oder einfacher Approximation (Wörter × 1.3)
- Retention: Max 500 Einträge pro Task (FIFO), plus Cron löscht Einträge älter als `HIVEMIND_PROMPT_HISTORY_RETENTION_DAYS` (Default: 180)
- Template-Komposition: Jinja2 für Variable-Insertion, Markdown-Output
- Context Assembly: Skills, Guards, Docs, Wiki-Artikel basierend auf Agent-Typ zusammenstellen

### Prompt-Typen

| Typ | Pflicht-Parameter | Beschreibung |
| --- | --- | --- |
| `bibliothekar` | `task_id` | Context Assembly — Skills + Docs für Task |
| `worker` | `task_id` | Worker-Prompt mit Skill-Inhalt + Guards |
| `review` | `task_id` | Review-Prompt mit DoD + Guard-Status |
| `gaertner` | `task_id` oder `epic_id` | Skill-Destillation aus History |
| `architekt` | `epic_id` | Epic-Decomposition-Prompt |
| `stratege` | `project_id` | Plan-Analyse-Prompt |
| `kartograph` | — | Repo-Analyse (kein Task-/Epic-Kontext nötig) |
| `triage` | — | Routing-Entscheidung (admin only) |

### Beispiel — Prompt-Generator-Service

```python
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_history import PromptHistory
from app.services.skill_service import SkillService

class PromptGenerator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate(self, prompt_type: str, **kwargs) -> str:
        match prompt_type:
            case "bibliothekar":
                prompt = await self._bibliothekar(kwargs["task_id"])
            case "worker":
                prompt = await self._worker(kwargs["task_id"])
            case _:
                raise ValueError(f"Unbekannter Prompt-Typ: {prompt_type}")

        # prompt_history schreiben
        await self._save_history(prompt_type, prompt, kwargs)
        return prompt

    async def _bibliothekar(self, task_id: str) -> str:
        task = await self._load_task(task_id)
        skills = await SkillService(self.db).get_active_skills()
        docs = await self._load_epic_docs(task.epic_id)

        return f"""## Rolle: Bibliothekar

Dein Auftrag: Kontext für {task_id} assemblieren.

Verfügbare aktive Skills:
{self._format_skills(skills)}

Verfügbare Docs:
{self._format_docs(docs)}

Aufgabe: {task.description}

Wähle 1-3 relevante Skills. Erkläre warum.
Baue danach den Worker-Prompt mit diesen Inhalten."""

    async def _save_history(self, prompt_type: str, prompt: str, context: dict) -> None:
        entry = PromptHistory(
            agent_type=prompt_type,
            prompt_type=prompt_type,
            prompt_text=prompt,
            token_count=self._count_tokens(prompt),
            generated_by="system",
        )
        self.db.add(entry)
        await self.db.flush()
```

### Wichtig
- Phase 1-2 Modus: `get_skills` gibt alle aktiven Skills zurück (kein Bibliothekar-Filtering)
- Ab Phase 3+: Bibliothekar nutzt pgvector-Similarity für relevante Skill-Auswahl
- Prompt-Templates als Skills ermöglicht Versionierung und A/B-Testing von Prompts
- UI-Ansicht der Prompt-History (kollabierbar in Prompt Station) kommt erst in Phase 4
