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
- MCP-Tool: `hivemind-get_prompt { "type": "<agent>", "task_key": "TASK-88" }`
- Legacy-Alias: `task_id` bleibt fuer `hivemind-get_prompt` kompatibel, aber neue Aufrufe verwenden `task_key`
- Prompt-Templates sind Skills mit `lifecycle='active'` — versioniert und austauschbar
- Jeder `get_prompt`-Aufruf schreibt einen `prompt_history`-Eintrag:
  - `agent_type`, `prompt_type`, `prompt_text`, `token_count`, `generated_by`
- Token-Counting mit `tiktoken` (cl100k_base Encoding) oder einfacher Approximation (Wörter × 1.3)
- Retention: Max 500 Einträge pro Task (FIFO), plus Cron löscht Einträge älter als `HIVEMIND_PROMPT_HISTORY_RETENTION_DAYS` (Default: 180)
- Template-Komposition: Jinja2 für Variable-Insertion, Markdown-Output
- Context Assembly: Skills, Guards, Docs, Wiki-Artikel basierend auf Agent-Typ zusammenstellen
- Die Prompt Station darf beim manuellen `Ausführen` nie nur `task.description` senden. Sie muss erst den agent-spezifischen Prompt generieren und genau diesen Prompt an den konfigurierten Provider dispatchen.
- `generate()` darf neben `task_key` / `epic_id` / `project_id` auch proposal-spezifischen Kontext annehmen (`skill_id`, `guard_id`, `proposal_id`, `decision_id`), damit Triage keine generischen Fallback-Prompts bekommt.

### Prompt-Typen

| Typ | Pflicht-Parameter | Beschreibung |
| --- | --- | --- |
| `bibliothekar` | `task_key` | Context Assembly — Skills + Docs für Task |
| `worker` | `task_key` | Worker-Prompt mit Skill-Inhalt + Guards |
| `review` | `task_key` | Review-Prompt mit DoD + Guard-Status |
| `gaertner` | `task_key` oder `epic_id` | Skill-Destillation aus History |
| `architekt` | `epic_id` | Epic-Decomposition-Prompt |
| `stratege` | `project_id` | Plan-Analyse-Prompt |
| `kartograph` | — | Repo-Analyse (kein Task-/Epic-Kontext nötig) |
| `triage` | optional `skill_id` / `guard_id` / `proposal_id` / `decision_id` | Routing- oder Proposal-Entscheidung (admin only) |

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
                prompt = await self._bibliothekar(kwargs["task_key"])
            case "worker":
                prompt = await self._worker(kwargs["task_key"])
            case "triage":
                prompt = await self._triage(
                    skill_id=kwargs.get("skill_id"),
                    guard_id=kwargs.get("guard_id"),
                    proposal_id=kwargs.get("proposal_id"),
                    decision_id=kwargs.get("decision_id"),
                )
            case _:
                raise ValueError(f"Unbekannter Prompt-Typ: {prompt_type}")

        # prompt_history schreiben
        await self._save_history(prompt_type, prompt, kwargs)
        return prompt

    async def _bibliothekar(self, task_key: str) -> str:
        task = await self._load_task(task_key)
        boundary = await self._load_context_boundary(task.id)
        query_text = self._build_task_query_text(task)
        skills = await self._select_relevant_skills(task, boundary=boundary, query_text=query_text)
        docs = await self._select_relevant_docs(task, boundary=boundary, query_text=query_text)

        return f"""## Rolle: Bibliothekar

Dein Auftrag: Kontext für {task_key} assemblieren.

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
- Ab Phase 3+: Bibliothekar nutzt pgvector-Similarity fuer relevante Skill-/Doc-Auswahl, respektiert `allowed_skills` / `allowed_docs` und faellt bei fehlenden Embeddings deterministisch auf eine schlanke Kandidatenliste zurueck
- Worker-/Review-Prompts sollen nicht blind alle gepinnten Skills inline expandieren, sondern nur die relevantesten Skill-Bloecke innerhalb eines Teilbudgets
- Gaertner-Prompts muessen bei `qa_failed` den letzten `review_comment` und den QA-Failure-Kontext einblenden, damit aus Review-Feedback lernbare Skill-/Doc-Aenderungen entstehen.
- Triage-Prompts muessen je nach Kontext zwischen allgemeinem Routing, Skill-Review, Guard-Review, Epic-Proposal-Review, Decision-Request-Review und Epic-Restructure-Review unterscheiden.
- Prompt-Templates als Skills ermöglicht Versionierung und A/B-Testing von Prompts
- UI-Ansicht der Prompt-History (kollabierbar in Prompt Station) kommt erst in Phase 4
- Manuelle Dispatches über `/api/admin/conductor/dispatch` lösen den Prompt serverseitig aus `task_key` / `epic_id` / `project_id` auf; nur wenn kein Kontext übergeben wurde, darf ein expliziter Roh-Prompt verwendet werden.
