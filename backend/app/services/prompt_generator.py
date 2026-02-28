"""Prompt-Generator Service — TASK-3-005.

Generates context-specific prompts for all agents:
  bibliothekar, worker, review, gaertner, architekt, stratege, kartograph, triage.

Each invocation writes a prompt_history entry with token count.
Retention: max 500 entries per task (FIFO).
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doc import Doc
from app.models.epic import Epic
from app.models.guard import Guard, TaskGuard
from app.models.prompt_history import PromptHistory
from app.models.project import Project
from app.models.skill import Skill
from app.models.sync import SyncOutbox
from app.models.task import Task

logger = logging.getLogger(__name__)

# Token counting — use tiktoken when available, fallback to word approximation
_encoding = None
try:
    import tiktoken
    _encoding = tiktoken.get_encoding("cl100k_base")
except Exception:
    pass


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base) or word approximation."""
    if _encoding:
        return len(_encoding.encode(text))
    return int(len(text.split()) * 1.3)


MAX_HISTORY_PER_TASK = 500


class PromptGenerator:
    """Generates agent prompts and records them in prompt_history."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate(
        self,
        prompt_type: str,
        *,
        task_id: Optional[str] = None,
        epic_id: Optional[str] = None,
        project_id: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> str:
        """Generate a prompt for the given agent type."""
        generators = {
            "bibliothekar": self._bibliothekar,
            "worker": self._worker,
            "review": self._review,
            "gaertner": self._gaertner,
            "architekt": self._architekt,
            "stratege": self._stratege,
            "kartograph": self._kartograph,
            "triage": self._triage,
        }
        handler = generators.get(prompt_type)
        if not handler:
            raise ValueError(f"Unbekannter Prompt-Typ: {prompt_type}")

        prompt = await handler(task_id=task_id, epic_id=epic_id, project_id=project_id)

        # Save to prompt_history
        task_uuid = None
        epic_uuid = None
        project_uuid = None
        if task_id:
            task = await self._load_task(task_id)
            if task:
                task_uuid = task.id
                epic_uuid = task.epic_id
        if epic_id and not epic_uuid:
            epic = await self._load_epic_by_key(epic_id)
            if epic:
                epic_uuid = epic.id
                project_uuid = epic.project_id
        if project_id and not project_uuid:
            try:
                project_uuid = uuid.UUID(project_id)
            except ValueError:
                pass

        entry = PromptHistory(
            task_id=task_uuid,
            epic_id=epic_uuid,
            project_id=project_uuid,
            agent_type=prompt_type,
            prompt_type=prompt_type,
            prompt_text=prompt,
            token_count=count_tokens(prompt),
            generated_by=actor_id,
        )
        self.db.add(entry)
        await self.db.flush()

        # FIFO retention per task
        if task_uuid:
            await self._enforce_fifo(task_uuid)

        return prompt

    # ── Agent Prompt Generators ────────────────────────────────────────────

    async def _bibliothekar(self, *, task_id: str | None, **_) -> str:
        if not task_id:
            raise ValueError("bibliothekar benötigt task_id")
        task = await self._load_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' nicht gefunden")

        skills = await self._get_active_skills()
        docs = await self._get_epic_docs(task.epic_id)

        skills_text = self._format_skills(skills)
        docs_text = self._format_docs(docs)

        return f"""## Rolle: Bibliothekar — Context Assembly

**Task:** {task.task_key} — {task.title}
**Status:** {task.state}
**Beschreibung:** {task.description or 'Keine Beschreibung'}

### Verfügbare aktive Skills ({len(skills)})
{skills_text}

### Epic-Docs ({len(docs)})
{docs_text}

### Auftrag
1. Analysiere die Task-Beschreibung und Definition-of-Done.
2. Wähle 1-3 relevante Skills aus der Liste.
3. Erkläre kurz, warum diese Skills relevant sind.
4. Baue daraus den Worker-Prompt zusammen."""

    async def _worker(self, *, task_id: str | None, **_) -> str:
        if not task_id:
            raise ValueError("worker benötigt task_id")
        task = await self._load_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' nicht gefunden")

        guards = await self._get_task_guards(task)
        guards_text = self._format_guards(guards)
        dod = task.definition_of_done or {}
        criteria = dod.get("criteria", [])

        return f"""## Rolle: Worker — Task-Ausführung

**Task:** {task.task_key} — {task.title}
**Status:** {task.state}
**Beschreibung:** {task.description or 'Keine Beschreibung'}

### Definition of Done
{chr(10).join(f'- [ ] {c}' for c in criteria) if criteria else '- Keine DoD definiert'}

### Guards
{guards_text}

### Pinned Skills
{', '.join(str(s) for s in (task.pinned_skills or [])) or 'Keine'}

### Auftrag
Führe die Aufgabe gemäß der Beschreibung und DoD aus.
Beachte alle Guards — sie müssen vor Abschluss bestanden werden.
Schreibe das Ergebnis als Markdown."""

    async def _review(self, *, task_id: str | None, **_) -> str:
        if not task_id:
            raise ValueError("review benötigt task_id")
        task = await self._load_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' nicht gefunden")

        guards = await self._get_task_guards(task)
        guards_text = self._format_guards(guards)
        dod = task.definition_of_done or {}
        criteria = dod.get("criteria", [])

        return f"""## Rolle: Reviewer — Quality Gate

**Task:** {task.task_key} — {task.title}
**Status:** {task.state} (QA-Failed Count: {task.qa_failed_count})
**Ergebnis:** {task.result or 'Noch kein Ergebnis eingereicht'}

### Definition of Done
{chr(10).join(f'- [ ] {c}' for c in criteria) if criteria else '- Keine DoD definiert'}

### Guards
{guards_text}

### Auftrag
1. Prüfe ob jedes DoD-Kriterium erfüllt ist.
2. Prüfe ob alle Guards bestanden haben.
3. Entscheide: `approve` oder `reject` (mit Begründung)."""

    async def _gaertner(self, *, task_id: str | None, epic_id: str | None, **_) -> str:
        if not task_id and not epic_id:
            raise ValueError("gaertner benötigt task_id oder epic_id")

        context_parts = []
        if task_id:
            task = await self._load_task(task_id)
            if task:
                context_parts.append(f"**Task:** {task.task_key} — {task.title}\n{task.description or ''}")
        if epic_id:
            epic = await self._load_epic_by_key(epic_id)
            if epic:
                context_parts.append(f"**Epic:** {epic.epic_key} — {epic.title}\n{epic.description or ''}")

        skills = await self._get_active_skills()
        skills_text = self._format_skills(skills)

        return f"""## Rolle: Gärtner — Skill-Destillation

### Kontext
{chr(10).join(context_parts) or 'Kein Kontext verfügbar'}

### Existierende Skills ({len(skills)})
{skills_text}

### Auftrag
1. Analysiere den Kontext und das Ergebnis der Aufgabe.
2. Identifiziere wiederverwendbare Muster oder Wissen.
3. Extrahiere neue Skills oder schlage Updates bestehender Skills vor.
4. Formatiere jeden Skill als Markdown mit Frontmatter (title, service_scope, stack)."""

    async def _architekt(self, *, epic_id: str | None, **_) -> str:
        if not epic_id:
            raise ValueError("architekt benötigt epic_id")
        epic = await self._load_epic_by_key(epic_id)
        if not epic:
            raise ValueError(f"Epic '{epic_id}' nicht gefunden")

        tasks = await self._get_epic_tasks(epic.id)
        tasks_text = "\n".join(
            f"- [{t.state}] {t.task_key}: {t.title}"
            for t in tasks
        ) or "Keine Tasks vorhanden"

        return f"""## Rolle: Architekt — Epic-Dekomposition

**Epic:** {epic.epic_key} — {epic.title}
**Status:** {epic.state} | **Priorität:** {epic.priority}
**Beschreibung:** {epic.description or 'Keine Beschreibung'}

### Bestehende Tasks ({len(tasks)})
{tasks_text}

### Auftrag
1. Analysiere die Epic-Beschreibung und bestehende Tasks.
2. Identifiziere fehlende Tasks oder Lücken.
3. Schlage eine optimale Task-Reihenfolge vor (Dependency-Graph).
4. Definiere DoD-Kriterien pro Task."""

    async def _stratege(self, *, project_id: str | None, **_) -> str:
        if not project_id:
            raise ValueError("stratege benötigt project_id")
        try:
            pid = uuid.UUID(project_id)
        except ValueError:
            raise ValueError(f"Ungültige project_id: {project_id}")

        result = await self.db.execute(select(Project).where(Project.id == pid))
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Projekt '{project_id}' nicht gefunden")

        epics_result = await self.db.execute(
            select(Epic).where(Epic.project_id == pid).order_by(Epic.created_at.asc())
        )
        epics = list(epics_result.scalars().all())
        epics_text = "\n".join(
            f"- [{e.state}] {e.epic_key}: {e.title} (Prio: {e.priority})"
            for e in epics
        ) or "Keine Epics vorhanden"

        return f"""## Rolle: Stratege — Plan-Analyse

**Projekt:** {project.name}
**Beschreibung:** {project.description or 'Keine Beschreibung'}

### Epics ({len(epics)})
{epics_text}

### Auftrag
1. Analysiere den Gesamt-Fortschritt aller Epics.
2. Identifiziere Risiken, Engpässe und Prioritäts-Konflikte.
3. Schlage Reihenfolge-Optimierungen vor.
4. Erstelle eine Zusammenfassung des Projektstands."""

    async def _kartograph(self, **_) -> str:
        return """## Rolle: Kartograph — Repo-Analyse

### Auftrag
1. Analysiere die Projektstruktur (Dateien, Module, Abhängigkeiten).
2. Identifiziere zentrale Komponenten und deren Beziehungen.
3. Erstelle Code-Nodes und Code-Edges für den Dependency-Graph.
4. Markiere Legacy-Code, Dead-Code und Hot-Paths.
5. Aktualisiere den Code-Graph in der Datenbank.

### Konventionen
- Code-Nodes haben Typen: module, class, function, file, package
- Code-Edges beschreiben: imports, calls, inherits, implements
- Nutze `POST /api/code-nodes` für neue Nodes
- Nutze `POST /api/code-nodes/{id}/edges` für neue Edges"""

    async def _triage(self, **_) -> str:
        # Load unrouted items count
        count_result = await self.db.execute(
            select(func.count()).select_from(SyncOutbox).where(
                SyncOutbox.direction == "inbound",
                SyncOutbox.routing_state == "unrouted",
            )
        )
        unrouted_count = count_result.scalar_one()

        return f"""## Rolle: Triage — Routing-Entscheidung

### Status
- Unrouted Events: {unrouted_count}

### Auftrag
1. Lade die ungerouteten Events via `hivemind/get_triage`.
2. Analysiere jeden Event: Was ist passiert? Welches Epic/Task betrifft es?
3. Route jeden Event zu einem Epic oder eskaliere ihn.
4. Events die keinem Epic zugeordnet werden können → `escalated` markieren.
5. Dead-Letter Events prüfen: Können sie erneut verarbeitet werden?

### Entscheidungspfad
- Sentry-Error → Bug-Task anlegen oder existierenden Tasks zuordnen
- YouTrack-Update → State-Sync mit Hivemind-Task
- Unbekannt → Eskalation an Admin"""

    # ── Data Loaders ───────────────────────────────────────────────────────

    async def _load_task(self, task_key: str) -> Task | None:
        result = await self.db.execute(select(Task).where(Task.task_key == task_key))
        return result.scalar_one_or_none()

    async def _load_epic_by_key(self, epic_key: str) -> Epic | None:
        result = await self.db.execute(select(Epic).where(Epic.epic_key == epic_key))
        return result.scalar_one_or_none()

    async def _get_active_skills(self) -> list[Skill]:
        result = await self.db.execute(
            select(Skill).where(
                Skill.lifecycle == "active",
                Skill.deleted_at.is_(None),
            ).order_by(Skill.title)
        )
        return list(result.scalars().all())

    async def _get_epic_docs(self, epic_id: uuid.UUID) -> list[Doc]:
        result = await self.db.execute(
            select(Doc).where(Doc.epic_id == epic_id)
        )
        return list(result.scalars().all())

    async def _get_epic_tasks(self, epic_id: uuid.UUID) -> list[Task]:
        result = await self.db.execute(
            select(Task).where(Task.epic_id == epic_id).order_by(Task.created_at.asc())
        )
        return list(result.scalars().all())

    async def _get_task_guards(self, task: Task) -> list[dict]:
        tg_result = await self.db.execute(
            select(TaskGuard, Guard)
            .join(Guard, TaskGuard.guard_id == Guard.id)
            .where(TaskGuard.task_id == task.id)
        )
        return [
            {"title": g.title, "type": g.type, "command": g.command, "status": tg.status, "skippable": g.skippable}
            for tg, g in tg_result.all()
        ]

    # ── Formatters ─────────────────────────────────────────────────────────

    def _format_skills(self, skills: list[Skill]) -> str:
        if not skills:
            return "_Keine aktiven Skills verfügbar_"
        return "\n".join(
            f"- **{s.title}** (scope: {','.join(s.service_scope)}, stack: {','.join(s.stack)}, conf: {s.confidence})"
            for s in skills
        )

    def _format_docs(self, docs: list[Doc]) -> str:
        if not docs:
            return "_Keine Docs verfügbar_"
        return "\n".join(f"- **{d.title}**: {d.content[:200]}..." for d in docs)

    def _format_guards(self, guards: list[dict]) -> str:
        if not guards:
            return "_Keine Guards konfiguriert_"
        return "\n".join(
            f"- [{g['status']}] {g['title']} ({g['type']}){' [skippable]' if g.get('skippable') else ''}"
            for g in guards
        )

    # ── Retention ──────────────────────────────────────────────────────────

    async def _enforce_fifo(self, task_id: uuid.UUID) -> None:
        """Remove oldest prompt_history entries exceeding MAX_HISTORY_PER_TASK."""
        count_result = await self.db.execute(
            select(func.count()).select_from(PromptHistory).where(
                PromptHistory.task_id == task_id
            )
        )
        count = count_result.scalar_one()
        if count <= MAX_HISTORY_PER_TASK:
            return

        excess = count - MAX_HISTORY_PER_TASK
        # Get IDs of oldest entries to delete
        oldest = await self.db.execute(
            select(PromptHistory.id)
            .where(PromptHistory.task_id == task_id)
            .order_by(PromptHistory.created_at.asc())
            .limit(excess)
        )
        ids_to_delete = [row[0] for row in oldest.all()]
        if ids_to_delete:
            await self.db.execute(
                delete(PromptHistory).where(PromptHistory.id.in_(ids_to_delete))
            )
            await self.db.flush()
