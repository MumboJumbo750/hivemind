"""Prompt-Generator Service — TASK-3-005 + TASK-8-016.

Generates context-specific prompts for all agents:
  bibliothekar, worker, review, gaertner, architekt, stratege, kartograph, triage.

Each invocation writes a prompt_history entry with token count.
Retention: max 500 entries per task (FIFO).

Phase 8 (TASK-8-016): Provider-specific token budget from ai_provider_configs.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.context_boundary import ContextBoundary, TaskSkill
from app.models.doc import Doc


def _epic_prefix_from_key(epic_key: str) -> str:
    """Derive the task-key prefix from an epic_key.

    EPIC-PHASE-5 → '5', EPIC-PHASE-1A → '1A', EPIC-42 → '42'.
    """
    m = re.match(r"EPIC-PHASE-(.+)", epic_key, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.match(r"EPIC-(\S+)", epic_key, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return epic_key
from app.models.epic import Epic
from app.models.epic_proposal import EpicProposal
from app.models.guard import Guard, TaskGuard
from app.models.prompt_history import PromptHistory
from app.models.project import Project
from app.models.skill import Skill
from app.models.sync import SyncOutbox
from app.models.task import Task
from app.models.wiki import WikiArticle

logger = logging.getLogger(__name__)



def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")


def _parse_health_report_summary(content: str) -> str:
    """Extract a brief summary from a diagnostics wiki article (TASK-HEALTH-008).

    Tries to parse error/warning counts and top categories from the markdown content.
    Falls back to the first 400 characters when patterns are not found.
    """
    lines = content.splitlines()
    errors = warnings = 0
    categories: list[tuple[str, int]] = []

    error_pat = re.compile(r"(\d+)\s+error", re.IGNORECASE)
    warn_pat = re.compile(r"(\d+)\s+warning", re.IGNORECASE)
    # Matches lines like: "- hardcoded-css: 42 findings" or "| hardcoded-css | 42 |"
    cat_pat = re.compile(r"[|\-\s]+([\w-]+)\s*[|:]\s*(\d+)", re.IGNORECASE)

    for line in lines[:80]:
        m = error_pat.search(line)
        if m:
            errors = max(errors, int(m.group(1)))
        m = warn_pat.search(line)
        if m:
            warnings = max(warnings, int(m.group(1)))
        m = cat_pat.search(line)
        if m:
            cat_name = m.group(1).lower()
            known = {"hardcoded-css", "layer-violations", "file-size", "magic-values",
                     "duplicate-detection", "import-cycles", "naming-conventions"}
            if cat_name in known:
                categories.append((cat_name, int(m.group(2))))

    # Deduplicate categories, keep top 3 by count
    seen: set[str] = set()
    unique_cats: list[tuple[str, int]] = []
    for name, count in sorted(categories, key=lambda x: -x[1]):
        if name not in seen:
            seen.add(name)
            unique_cats.append((name, count))
            if len(unique_cats) >= 3:
                break

    if errors or warnings or unique_cats:
        cat_names = ", ".join(c[0] for c in unique_cats)
        cat_str = "\n".join(f"  - {n}: {c} Findings" for n, c in unique_cats) or "  _keine Kategorien erkannt_"
        return (
            f"- **{errors}** Errors, **{warnings}** Warnings\n"
            f"- Top-Kategorien:\n{cat_str}\n"
            + (f"- Empfehlung: Cleanup-Epics für {cat_names} ableiten" if cat_names else "")
        )

    # Fallback: first 400 chars of content
    excerpt = content.strip()[:400].replace("\n", " ")
    return f"_{excerpt}..._"

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

# Default token budget when no DB config is available (fallback to settings)
_DEFAULT_TOKEN_BUDGET = 8000

# ── Health-Findings → Guard-Mapping (TASK-HEALTH-008) ─────────────────────────
HEALTH_FINDINGS_TO_GUARD_MAPPING: dict[str, list[str]] = {
    "hardcoded-css": ["no-hardcoded-colors", "no-hardcoded-spacing"],
    "layer-violations": ["layer-boundaries"],
    "file-size": ["max-file-size"],
    "magic-values": ["no-magic-numbers"],
    "duplicate-detection": ["no-duplicate-components"],
}

# ── Cleanup-Epic-Templates pro Analyzer-Kategorie (TASK-HEALTH-008) ───────────
CLEANUP_EPIC_TEMPLATES: dict[str, dict] = {
    "hardcoded-css": {
        "title": "Design-Token-Migration: Hardcoded CSS-Werte ersetzen",
        "description": (
            "Alle hardcodierten Farb- und Spacing-Werte durch Design-Tokens ersetzen.\n\n"
            "**Scope:** Alle Komponenten mit hardcoded CSS-Werten laut Health Report.\n\n"
            "**Vorgehen:**\n"
            "1. Design-Token-Katalog erstellen (colors, spacing, typography)\n"
            "2. Hardcoded Werte komponentenweise ersetzen\n"
            "3. Visuelle Regression-Tests sicherstellen"
        ),
        "definition_of_done": [
            "Alle hardcodierten Farbwerte durch CSS-Variablen/Tokens ersetzt",
            "Alle hardcodierten Spacing-Werte durch Tokens ersetzt",
            "Health-Report zeigt 0 hardcoded-css Findings",
            "Visuelle Regressions-Tests grün",
        ],
        "tags": ["cleanup", "design-tokens", "css", "health-report"],
    },
    "duplicate-detection": {
        "title": "Komponenten-Deduplizierung: Doppelte Implementierungen zusammenführen",
        "description": (
            "Identifizierte doppelte Komponenten zusammenführen und eine "
            "Single-Source-of-Truth etablieren.\n\n"
            "**Scope:** Alle Duplikat-Paare laut Health Report.\n\n"
            "**Vorgehen:**\n"
            "1. Duplikat-Paare analysieren (Unterschiede dokumentieren)\n"
            "2. Gemeinsame Basiskomponente extrahieren\n"
            "3. Alle Verweise auf Duplikate migrieren\n"
            "4. Duplikate entfernen"
        ),
        "definition_of_done": [
            "Alle identifizierten Duplikat-Paare aufgelöst",
            "Keine redundanten Komponenten-Implementierungen",
            "Health-Report zeigt 0 duplicate-detection Findings",
            "Alle bestehenden Tests grün",
        ],
        "tags": ["cleanup", "refactoring", "deduplication", "health-report"],
    },
    "layer-violations": {
        "title": "Layer-Refactoring: Architektur-Schichten bereinigen",
        "description": (
            "Layer-Violations gemäß Health Report beheben und saubere "
            "Architektur-Schichten herstellen.\n\n"
            "**Scope:** Alle Layer-Verletzungen laut Health Report.\n\n"
            "**Vorgehen:**\n"
            "1. Bestehende Layer-Definitionen dokumentieren\n"
            "2. Verletzungen analysieren und Refactoring-Plan erstellen\n"
            "3. Schrittweise Refactoring unter Beibehaltung der Funktionalität"
        ),
        "definition_of_done": [
            "Alle Layer-Violations aus Health Report behoben",
            "Layer-Boundaries als Guards konfiguriert",
            "Health-Report zeigt 0 layer-violations Findings",
            "Architektur-Dokumentation aktualisiert",
        ],
        "tags": ["cleanup", "architecture", "layers", "health-report"],
    },
    "magic-values": {
        "title": "Konstanten-Extraktion: Magic Values ersetzen",
        "description": (
            "Alle Magic Numbers und Magic Strings durch benannte Konstanten ersetzen.\n\n"
            "**Scope:** Alle Magic-Value-Findings laut Health Report.\n\n"
            "**Vorgehen:**\n"
            "1. Magic Values katalogisieren und gruppieren\n"
            "2. Konstanten-Datei(en) erstellen\n"
            "3. Magic Values ersetzen"
        ),
        "definition_of_done": [
            "Alle Magic Numbers durch benannte Konstanten ersetzt",
            "Alle Magic Strings durch Konstanten/Enums ersetzt",
            "Health-Report zeigt 0 magic-values Findings",
            "Code-Review bestätigt Lesbarkeitsverbesserung",
        ],
        "tags": ["cleanup", "constants", "code-quality", "health-report"],
    },
}


async def _get_provider_token_budget(db: AsyncSession, agent_role: str, settings: Settings) -> int:
    """Return the effective token budget for an agent role.

    Lookup chain:
    1. ai_provider_configs.token_budget_daily for the role
    2. settings.hivemind_token_budget (global default)

    Applies HIVEMIND_TOKEN_COUNT_CALIBRATION factor if set.
    """
    budget = settings.hivemind_token_budget
    provider_name: str | None = None
    try:
        from app.models.ai_provider import AIProviderConfig
        result = await db.execute(
            select(AIProviderConfig).where(
                AIProviderConfig.agent_role == agent_role,
                AIProviderConfig.enabled.is_(True),
            )
        )
        config = result.scalar_one_or_none()
        if config and config.token_budget_daily:
            budget = config.token_budget_daily
        if config:
            provider_name = config.provider
    except Exception:
        pass  # graceful fallback if table doesn't exist yet

    # Apply calibration factor per provider
    if provider_name and settings.hivemind_token_count_calibration:
        try:
            calibration: dict = json.loads(settings.hivemind_token_count_calibration)
            factor = float(calibration.get(provider_name, 1.0))
            budget = int(budget * factor)
        except Exception:
            pass

    return budget


class PromptGenerator:
    """Generates agent prompts and records them in prompt_history."""

    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self._settings = settings

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
            "stratege_requirement": self._stratege_requirement,
            "kartograph": self._kartograph,
            "triage": self._triage,
        }
        handler = generators.get(prompt_type)
        if not handler:
            raise ValueError(f"Unbekannter Prompt-Typ: {prompt_type}")

        # Phase 8: resolve effective token budget for this agent role
        effective_budget: int | None = None
        if self._settings and prompt_type in (
            "bibliothekar", "worker", "review", "gaertner",
            "architekt", "stratege", "kartograph", "triage",
        ):
            effective_budget = await _get_provider_token_budget(
                self.db, prompt_type, self._settings
            )

        prompt = await handler(
            task_id=task_id,
            epic_id=epic_id,
            project_id=project_id,
            token_budget=effective_budget,
        )

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

    async def _bibliothekar(self, *, task_id: str | None, token_budget: int | None = None, **_) -> str:
        if not task_id:
            raise ValueError("bibliothekar benötigt task_id")
        task = await self._load_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' nicht gefunden")

        skills = await self._get_active_skills()
        docs = await self._get_epic_docs(task.epic_id)

        skills_text = self._format_skills(skills)
        docs_text = self._format_docs(docs)

        budget = token_budget or _DEFAULT_TOKEN_BUDGET
        budget_hint = f"\n> **Token-Budget:** ~{budget} Tokens verfügbar (Provider-konfiguriert).\n" if token_budget else ""

        return f"""## Rolle: Bibliothekar — Context Assembly

**Task:** {task.task_key} — {task.title}
**Status:** {task.state}
**Beschreibung:** {task.description or 'Keine Beschreibung'}
{budget_hint}
### Verfügbare aktive Skills ({len(skills)})
{skills_text}

### Epic-Docs ({len(docs)})
{docs_text}

### Auftrag
1. Analysiere die Task-Beschreibung und Definition-of-Done.
2. Wähle 1-3 relevante Skills aus der Liste.
3. Erkläre kurz, warum diese Skills relevant sind.
4. Baue daraus den Worker-Prompt zusammen.
5. Halte den Prompt innerhalb des Token-Budgets (~{budget} Tokens)."""

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
        linked_skills = await self._get_task_linked_skills(task)
        pinned_slugs = list(task.pinned_skills or [])
        pinned_skills = await self._resolve_pinned_skills(pinned_slugs)
        skills_overview_text = self._format_task_skill_overview(
            linked_skills=linked_skills,
            pinned_slugs=pinned_slugs,
            pinned_skills=pinned_skills,
        )
        pinned_skills_text = self._format_pinned_skills(pinned_skills, pinned_slugs)
        context_boundary = await self._get_task_context_boundary(task)
        allowed_boundary_skills = await self._resolve_skills_by_ids(
            list(context_boundary.allowed_skills or []) if context_boundary else []
        )
        context_boundary_text = self._format_task_context_boundary(
            task=task,
            boundary=context_boundary,
            allowed_skills=allowed_boundary_skills,
        )

        # Phase 5 enhancements: review comment on re-entry, write tools list
        review_hint = ""
        if task.qa_failed_count and task.qa_failed_count > 0 and task.review_comment:
            review_hint = f"""
### ⚠ Vorheriger Review-Kommentar (QA #{task.qa_failed_count})
{task.review_comment}
"""

        mcp_base = "http://localhost:8000"
        mcp_sse_url = f"{mcp_base}/api/mcp/sse"
        task_resource_uri = f"hivemind://task/{task.task_key}"

        return f"""## Rolle: Worker — Task-Ausführung

**Task:** {task.task_key} — {task.title}
**Status:** {task.state} (QA-Failed: {task.qa_failed_count or 0})
**Beschreibung:** {task.description or 'Keine Beschreibung'}
{review_hint}
### MCP-Verbindung

MCP-Server: `{mcp_sse_url}`
Task-Resource: `{task_resource_uri}`

> VS Code/Copilot: `.vscode/mcp.json` ist bereits im Repo — Hivemind-Tools sind automatisch verfügbar.
> Andere Clients: `GET {mcp_base}/api/mcp/discovery`

### Definition of Done
{chr(10).join(f'- [ ] {c}' for c in criteria) if criteria else '- Keine DoD definiert'}

### Guards (Phase 5 Enforcement aktiv)
{guards_text}
> **Hinweis:** Alle Guards müssen `passed` oder `skipped` sein, bevor der Task
> nach `in_review` wechseln kann. Nutze `hivemind/report_guard_result` zum
> Melden der Guard-Ergebnisse.

### Context Boundary
{context_boundary_text}

### Skills
{skills_overview_text}

### Skills — Volltext (Pinned)
{pinned_skills_text}

### Verfügbare Write-Tools

> ⚠️ **Zwei-Schritt-Abschluss — häufiger Fehler:**
> `submit_result` speichert nur Ergebnis/Artifacts — der Task bleibt in `in_progress`!
> Danach **muss** `update_task_state` aufgerufen werden.

**Schritt 1 — Ergebnis speichern:**
- `hivemind/submit_result` — Ergebnis + Artifacts speichern (State bleibt `in_progress`!)
  ```json
  {{"tool": "hivemind/submit_result", "arguments": {{"task_key": "{task.task_key}", "result": "...", "artifacts": []}}}}
  ```

**Schritt 2 — State wechseln:**
- `hivemind/update_task_state` — Task nach `in_review` schieben (erst nach Schritt 1!)
  ```json
  {{"tool": "hivemind/update_task_state", "arguments": {{"task_key": "{task.task_key}", "target_state": "in_review"}}}}
  ```

**Weitere Tools:**
- `hivemind/report_guard_result` — Guard-Status melden (passed/failed/skipped)
- `hivemind/create_decision_request` — Entscheidung anfordern (Task → blocked)

### ⚠️ Operative Hinweise (häufige Fehler!)

**MCP-Aufrufe:** Alle Tools laufen über **einen** Endpoint — `POST {mcp_base}/api/mcp/call` mit Body:
```json
{{"tool": "hivemind/TOOLNAME", "arguments": {{...}}}}
```
Es gibt **keine** individuellen REST-Endpoints wie `/api/mcp/submit_result` — das wären 404er!

**Host-Einschränkungen:** `python` ist auf dem Windows-Host NICHT verfügbar (nur Microsoft Store Stub).
Scripts via Container: `podman compose exec backend /app/.venv/bin/python /workspace/scripts/mcp_call.py "hivemind/get_task" '{{"task_key": "{task.task_key}"}}'`
Alternativ: `curl` oder PowerShell `Invoke-WebRequest` direkt vom Host.

**PowerShell:** Backticks in Here-Strings werden als Escape-Sequenzen interpretiert → Parse-Error.
JSON in Datei auslagern (`Get-Content payload.json -Raw`) oder einfache Anführungszeichen nutzen. Keine Markdown-Backticks in JSON-Bodys.

### Auftrag
Führe die Aufgabe gemäß der Beschreibung und DoD aus.
Beachte alle Guards — sie müssen vor Abschluss bestanden werden.
Schreibe das Ergebnis als Markdown und nutze `hivemind/submit_result`."""

    async def _review(self, *, task_id: str | None, **_) -> str:
        if not task_id:
            raise ValueError("review benötigt task_id")
        task = await self._load_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' nicht gefunden")

        guards = await self._get_task_guards(task)
        guards_text = self._format_guards_with_provenance(guards)
        dod = task.definition_of_done or {}
        criteria = dod.get("criteria", [])
        linked_skills = await self._get_task_linked_skills(task)
        pinned_slugs = list(task.pinned_skills or [])
        pinned_skills = await self._resolve_pinned_skills(pinned_slugs)
        skills_overview_text = self._format_task_skill_overview(
            linked_skills=linked_skills,
            pinned_slugs=pinned_slugs,
            pinned_skills=pinned_skills,
        )
        context_boundary = await self._get_task_context_boundary(task)
        allowed_boundary_skills = await self._resolve_skills_by_ids(
            list(context_boundary.allowed_skills or []) if context_boundary else []
        )
        context_boundary_text = self._format_task_context_boundary(
            task=task,
            boundary=context_boundary,
            allowed_skills=allowed_boundary_skills,
        )

        mcp_base = "http://localhost:8000"
        mcp_sse_url = f"{mcp_base}/api/mcp/sse"
        task_resource_uri = f"hivemind://task/{task.task_key}"

        return f"""## Rolle: Reviewer — Quality Gate

**Task:** {task.task_key} — {task.title}
**Status:** {task.state} (QA-Failed Count: {task.qa_failed_count})
**Ergebnis:** {task.result or 'Noch kein Ergebnis eingereicht'}

---

### MCP-Verbindung (Pflicht vor Beginn)

Verbinde dich mit dem Hivemind MCP-Server um die Review-Tools nutzen zu können:

| Client | Konfiguration |
|--------|---------------|
| VS Code / Copilot | `.vscode/mcp.json` bereits im Repo — kein Setup nötig |
| Claude Desktop | SSE-URL: `{mcp_sse_url}` (via `mcp-remote`) |
| Cursor | SSE-URL: `{mcp_sse_url}` |
| Copilot CLI | `gh copilot mcp add hivemind --type sse --url {mcp_sse_url}` |

**Discovery:** `GET {mcp_base}/api/mcp/discovery` — Config-Snippets für alle Clients.

**Task-Kontext als MCP-Resource laden:**
```
Resource URI: {task_resource_uri}
```
In VS Code: *Add Context → MCP Resources → {task_resource_uri}*

---

### Skills
{skills_overview_text}

### Definition of Done — Checkliste
{chr(10).join(f'- [ ] {c}' for c in criteria) if criteria else '- Keine DoD definiert'}

### Guards — Status mit Provenance
{guards_text}

### Context Boundary
{context_boundary_text}

---

### Auftrag
1. Lade Task-Kontext via MCP-Resource `{task_resource_uri}`.
2. Prüfe ob jedes DoD-Kriterium erfüllt ist.
3. Prüfe alle Guards — beachte die **Quelle** (self-reported vs. system-executed).
4. ⚠ **Warnung**: Bei `self-reported` Guards ohne Output besonders kritisch prüfen!
5. Entscheide und führe einen der folgenden MCP-Calls aus:

**Approve:**
```json
{{"tool": "hivemind/approve_review", "arguments": {{"task_key": "{task.task_key}", "comment": "Alle DoD-Kriterien erfüllt. Guards bestanden."}}}}
```

**Reject (QA Failed):**
```json
{{"tool": "hivemind/reject_review", "arguments": {{"task_key": "{task.task_key}", "comment": "Begründung: <was fehlt oder fehlerhaft ist>"}}}}
```

**Alle verfügbaren Tools:** `GET {mcp_base}/api/mcp/tools`"""

    async def _gaertner(self, *, task_id: str | None, epic_id: str | None, **_) -> str:
        if not task_id and not epic_id:
            raise ValueError("gaertner benötigt task_id oder epic_id")

        context_parts = []
        task_result = ""
        if task_id:
            task = await self._load_task(task_id)
            if task:
                context_parts.append(f"**Task:** {task.task_key} — {task.title}\n{task.description or ''}")
                if task.result:
                    task_result = f"\n**Task-Ergebnis:**\n{task.result[:2000]}"
        if epic_id:
            epic = await self._load_epic_by_key(epic_id)
            if epic:
                context_parts.append(f"**Epic:** {epic.epic_key} — {epic.title}\n{epic.description or ''}")

        skills = await self._get_active_skills()
        skills_text = self._format_skills(skills)

        return f"""## Rolle: Gärtner — Skill-Destillation & Wissenskonsolidierung

### Kontext
{chr(10).join(context_parts) or 'Kein Kontext verfügbar'}
{task_result}

### Existierende Skills ({len(skills)})
{skills_text}

### Verfügbare Write-Tools
- `hivemind/propose_skill` — Neuen Skill vorschlagen (lifecycle=draft)
- `hivemind/propose_skill_change` — Änderung an bestehendem Skill
- `hivemind/create_decision_record` — Entscheidungs-Dokumentation
- `hivemind/update_doc` — Epic-Doc aktualisieren (Optimistic Locking)

### Auftrag
1. Analysiere den Kontext und das Ergebnis der Aufgabe.
2. Vergleiche mit existierenden Skills — verhindere Duplikate.
3. Identifiziere wiederverwendbare Muster oder Wissen.
4. Nutze `hivemind/propose_skill` für neue Skills (max. Tiefe 3).
5. Formatiere jeden Skill als Markdown mit Frontmatter (title, service_scope, stack).
6. Dokumentiere wichtige Entscheidungen mit `hivemind/create_decision_record`."""

    async def _architekt(self, *, epic_id: str | None, **_) -> str:
        if not epic_id:
            raise ValueError("architekt benötigt epic_id")
        epic = await self._load_epic_by_key(epic_id)
        if not epic:
            raise ValueError(f"Epic '{epic_id}' nicht gefunden")

        tasks = await self._get_epic_tasks(epic.id)
        tasks_text = "\n".join(
            f"- [{t.state}] {t.task_key}: {t.title}"
            + (f" (assigned: {t.assigned_to})" if t.assigned_to else "")
            for t in tasks
        ) or "Keine Tasks vorhanden"

        # Active skills with relevance info
        skills = await self._get_active_skills()
        skills_text = self._format_skills(skills)

        # Epic docs
        docs = await self._get_epic_docs(epic.id)
        docs_text = self._format_docs(docs)

        # Wiki articles linked to this epic or matching epic tags
        wiki_articles = await self._get_epic_wiki_articles(epic)
        wiki_text = ""
        if wiki_articles:
            wiki_text = "\n### Wiki-Artikel ({count})\n{items}".format(
                count=len(wiki_articles),
                items="\n".join(
                    f"- **{a.title}** (tags: {', '.join(a.tags or [])}) — {a.content[:150]}..."
                    for a in wiki_articles
                ),
            )

        # DoD framework from epic scoping
        dod_text = ""
        if epic.dod_framework:
            dod = epic.dod_framework
            if isinstance(dod, dict) and "text" in dod:
                dod_text = f"\n### Definition of Done (Epic-Rahmen)\n{dod['text']}"
            elif isinstance(dod, dict) and "criteria" in dod:
                dod_text = "\n### Definition of Done (Epic-Rahmen)\n" + "\n".join(
                    f"- {c}" for c in dod["criteria"]
                )
            elif isinstance(dod, str):
                dod_text = f"\n### Definition of Done (Epic-Rahmen)\n{dod}"

        # Epic dependency chain
        dep_text = ""
        if epic.external_id:
            deps = await self._get_epic_dependencies(epic.external_id)
            if deps:
                dep_text = "\n### Abhängigkeiten\n" + "\n".join(
                    f"- {d.epic_key}: {d.title} [{d.state}]" for d in deps
                )

        # Context boundary (if set for any task in epic)
        token_budget = Settings().hivemind_token_budget  # default
        boundaries = await self._get_epic_context_boundaries(epic.id)
        boundary_text = ""
        if boundaries:
            boundary_text = "\n### Context Boundaries\n" + "\n".join(
                f"- Task {b['task_key']}: max_tokens={b['max_token_budget']}, "
                f"allowed_skills={len(b['allowed_skills'] or [])}"
                for b in boundaries
            )
            # Use first boundary's budget if set
            first_budget = boundaries[0].get("max_token_budget")
            if first_budget:
                token_budget = first_budget

        return f"""## Rolle: Architekt — Epic-Dekomposition

**Epic:** {epic.epic_key} — {epic.title}
**Epic-UUID:** {epic.id} (für `list_tasks` epic_id Filter)
**Status:** {epic.state} | **Priorität:** {epic.priority}
**Token-Budget:** {token_budget}
**Beschreibung:** {epic.description or 'Keine Beschreibung'}
{dod_text}
{dep_text}

### Bestehende Tasks ({len(tasks)})
{tasks_text}

### Aktive Skills ({len(skills)})
{skills_text}

### Docs
{docs_text}
{wiki_text}
{boundary_text}

### Auftrag
1. Analysiere die Epic-Beschreibung, DoD-Rahmen und bestehende Tasks.
2. Identifiziere fehlende Tasks oder Lücken.
3. Schlage eine optimale Task-Reihenfolge vor (Dependency-Graph).
4. Definiere DoD-Kriterien pro Task.
5. Verknüpfe passende Skills mit Tasks via `link_skill`.
6. Setze Context Boundaries für Tasks mit speziellen Anforderungen.
7. Berücksichtige Abhängigkeiten zu anderen Epics.

### Wichtig: Task-Benennung & Lifecycle
`decompose_epic` generiert automatisch **phasen-spezifische Task-Keys** nach dem Muster `TASK-{{phasen-prefix}}-NNN`.
Beispiel: Epic `{epic.epic_key}` → Tasks `TASK-{_epic_prefix_from_key(epic.epic_key)}-001`, `TASK-{_epic_prefix_from_key(epic.epic_key)}-002`, …
Jeder Task bekommt automatisch eine `external_id` identisch zum `task_key`.

Tasks starten mit state=**incoming**. Du musst sie manuell transitionieren:
1. `incoming → scoped` (via `update_task_state`)
2. `scoped → ready` (via `update_task_state`, Voraussetzung: `assigned_to` gesetzt, sonst 422)

Empfohlene Reihenfolge pro Task: decompose → set_context_boundary → link_skill → assign_task → update_task_state(scoped) → update_task_state(ready)

### MCP-Tools
Nutze folgende Tools für die Umsetzung:

- **`hivemind/decompose_epic`**: Epic in Tasks zerlegen (erstellt Tasks als `incoming`)
  ```json
  {{"tool": "hivemind/decompose_epic", "arguments": {{"epic_key": "{epic.epic_key}", "tasks": [{{"title": "...", "description": "...", "definition_of_done": {{"criteria": ["..."]}}, "subtasks": []}}]}}}}
  ```

- **`hivemind/set_context_boundary`**: Token-Budget und erlaubte Skills pro Task
  ```json
  {{"tool": "hivemind/set_context_boundary", "arguments": {{"task_key": "TASK-xxx", "max_token_budget": 8000, "allowed_skills": ["skill-uuid"]}}}}
  ```

- **`hivemind/link_skill`**: Skill an Task pinnen
  ```json
  {{"tool": "hivemind/link_skill", "arguments": {{"task_key": "TASK-xxx", "skill_id": "skill-uuid"}}}}
  ```

- **`hivemind/assign_task`**: Task einem User zuweisen
  ```json
  {{"tool": "hivemind/assign_task", "arguments": {{"task_key": "TASK-xxx", "user_id": "user-uuid"}}}}
  ```

- **`hivemind/update_task_state`**: Task-State transitionieren (incoming→scoped→ready)
  ```json
  {{"tool": "hivemind/update_task_state", "arguments": {{"task_key": "TASK-xxx", "target_state": "scoped"}}}}
  ```
  Danach:
  ```json
  {{"tool": "hivemind/update_task_state", "arguments": {{"task_key": "TASK-xxx", "target_state": "ready"}}}}
  ```

### Parameter-Referenz (exakte Feldnamen!)
| Tool | Required Params | Hinweis |
|------|----------------|---------|
| `decompose_epic` | `epic_key` (str), `tasks` (array) | NICHT `epic_id`! |
| `set_context_boundary` | `task_key` (str) | optional: `allowed_skills`, `allowed_docs`, `max_token_budget` |
| `link_skill` | `task_key` (str), `skill_id` (uuid-str) | |
| `assign_task` | `task_key` (str), `user_id` (uuid-str) | NICHT `assigned_to`! |
| `update_task_state` | `task_key` (str), `target_state` (str) | NICHT `state`! 2 Schritte: incoming→scoped→ready |
| `list_tasks` | — | Filter: `epic_id` (UUID!), `state`, `assigned_to`. epic_id ist die UUID, NICHT der epic_key |"""

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

        # All epics with task progress stats
        epics_result = await self.db.execute(
            select(Epic).where(Epic.project_id == pid).order_by(Epic.created_at.asc())
        )
        epics = list(epics_result.scalars().all())
        epics_lines = []
        for e in epics:
            task_count = await self.db.execute(
                select(func.count()).select_from(Task).where(Task.epic_id == e.id)
            )
            done_count = await self.db.execute(
                select(func.count()).select_from(Task).where(
                    Task.epic_id == e.id, Task.state == "done"
                )
            )
            total = task_count.scalar_one()
            done = done_count.scalar_one()
            progress = f"{done}/{total}" if total else "0/0"
            epics_lines.append(
                f"- [{e.state}] {e.epic_key}: {e.title} (Prio: {e.priority}, Tasks: {progress})"
            )
        epics_text = "\n".join(epics_lines) or "Keine Epics vorhanden"

        # Open epic proposals
        proposals_result = await self.db.execute(
            select(EpicProposal).where(
                EpicProposal.project_id == pid,
                EpicProposal.state == "proposed",
            ).order_by(EpicProposal.created_at.desc())
        )
        proposals = list(proposals_result.scalars().all())
        proposals_text = "\n".join(
            f"- **{p.title}**: {(p.description or '')[:200]} (von: {p.proposed_by})"
            for p in proposals
        ) if proposals else "_Keine offenen Proposals_"

        # Wiki overview
        wiki_result = await self.db.execute(
            select(WikiArticle).order_by(WikiArticle.created_at.desc()).limit(20)
        )
        wiki_articles = list(wiki_result.scalars().all())
        wiki_text = "\n".join(
            f"- [{a.slug}] {a.title}"
            for a in wiki_articles
        ) if wiki_articles else "_Kein Wiki vorhanden_"

        # ── Health-Report-Enrichment (TASK-HEALTH-008) ──────────────────────
        health_section = await self._build_health_report_section()

        token_budget = Settings().hivemind_token_budget

        return f"""## Rolle: Stratege — Plan-Analyse

**Projekt:** {project.name}
**Beschreibung:** {project.description or 'Keine Beschreibung'}
**Token-Budget:** {token_budget}

### Epics ({len(epics)})
{epics_text}

### Offene Proposals ({len(proposals)})
{proposals_text}

### Wiki-Überblick ({len(wiki_articles)} Artikel)
{wiki_text}
{health_section}
### Analyse-Framework
- **Fortschritt**: % der Tasks in done-State pro Epic
- **Risiken**: Epics mit vielen blockierten Tasks
- **Engpässe**: Tasks ohne assigned_to oder mit hohem qa_failed_count
- **Prioritäten**: Mismatches zwischen Epic-Priorität und Task-Fortschritt

### Auftrag
1. Analysiere den Gesamt-Fortschritt aller Epics.
2. Identifiziere Risiken, Engpässe und Prioritäts-Konflikte.
3. Schlage Reihenfolge-Optimierungen vor.
4. Prüfe offene Proposals auf strategische Relevanz.
5. Erstelle eine Zusammenfassung des Projektstands.
6. Bei Bedarf: Erstelle neue Epic-Proposals für identifizierte Lücken.
7. Bei vorhandenem Health-Report: Leite Cleanup-Epics aus den Top-Findings ab.

### MCP-Tools
Nutze folgendes Tool für neue Epic-Vorschläge:

- **`hivemind/propose_epic`**: Neuen Epic-Vorschlag erstellen
  ```json
  {{"tool": "hivemind/propose_epic", "arguments": {{"project_id": "{project_id}", "title": "...", "description": "...", "rationale": "..."}}}}
  ```"""

    async def _stratege_requirement(
        self,
        *,
        project_id: str | None,
        requirement_text: str | None = None,
        priority_hint: str | None = None,
        **_,
    ) -> str:
        """Generate enriched Stratege prompt for a new free-text requirement."""
        if not project_id:
            raise ValueError("stratege_requirement benötigt project_id")
        if not requirement_text:
            raise ValueError("stratege_requirement benötigt requirement_text")
        try:
            pid = uuid.UUID(project_id)
        except ValueError:
            raise ValueError(f"Ungültige project_id: {project_id}")

        result = await self.db.execute(select(Project).where(Project.id == pid))
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Projekt '{project_id}' nicht gefunden")

        # All epics (summary for duplicate check)
        epics_result = await self.db.execute(
            select(Epic).where(Epic.project_id == pid).order_by(Epic.created_at.asc())
        )
        epics = list(epics_result.scalars().all())
        epics_lines = []
        for e in epics:
            task_count_r = await self.db.execute(
                select(func.count()).select_from(Task).where(Task.epic_id == e.id)
            )
            done_count_r = await self.db.execute(
                select(func.count()).select_from(Task).where(
                    Task.epic_id == e.id, Task.state == "done"
                )
            )
            total = task_count_r.scalar_one()
            done = done_count_r.scalar_one()
            epics_lines.append(
                f"- [{e.state}] {e.epic_key}: {e.title} (Prio: {e.priority}, Tasks: {done}/{total})"
            )
        epics_text = "\n".join(epics_lines) or "_Keine Epics vorhanden_"

        # Capacity: in_progress + blocked task counts
        in_progress_r = await self.db.execute(
            select(func.count()).select_from(Task).join(Epic).where(
                Epic.project_id == pid, Task.state == "in_progress"
            )
        )
        blocked_r = await self.db.execute(
            select(func.count()).select_from(Task).join(Epic).where(
                Epic.project_id == pid, Task.state == "blocked"
            )
        )
        in_progress_count = in_progress_r.scalar_one()
        blocked_count = blocked_r.scalar_one()

        # Tech stack from project description (or generic)
        tech_stack = project.description[:200] if project.description else "Siehe AGENTS.md"

        priority_hint_text = f"\n**Prioritäts-Hint vom User:** {priority_hint}" if priority_hint else ""

        capacity_warning = ""
        if in_progress_count > 5:
            capacity_warning = (
                "\n> ⚠ Kapazität: Viele Tasks in-progress. "
                "Empfehle `suggested_priority: medium` oder spätere Phase, "
                "außer die Anforderung ist kritisch für laufende Arbeit."
            )

        return f"""## Rolle: Stratege — Neue Anforderung erfassen

**Projekt:** {project.name}
**Aktuelle Phase:** Siehe Epics-Liste
**Tech-Stack:** {tech_stack}

### Bestehende Epics ({len(epics)}) — Duplikat-Check

{epics_text}

### Kapazität

**Tasks in-progress:** {in_progress_count}
**Blockierte Tasks:** {blocked_count}
{capacity_warning}

### Neue Anforderung (User-Input)
{priority_hint_text}

> {requirement_text}

### Auftrag

**Schritt 1 — Duplikat-Check:**
Prüfe ob die Anforderung bereits durch ein bestehendes Epic abgedeckt ist.

- Falls ja: Empfehle das betroffene Epic zu erweitern, nicht neu anlegen. Begründe warum.
- Falls nein: Weiter mit Schritt 2.

**Schritt 2 — Epic-Proposal formulieren:**

```
Titel:              [kurz, präzise, max 60 Zeichen]
Beschreibung:       [Was genau gebaut wird + warum]
Rationale:          [Ableitung aus der Anforderung + strategischer Nutzen]
suggested_priority: critical | high | medium | low
suggested_phase:    [nächste sinnvolle Phase-Nummer]
depends_on:         [Epic-Keys die vorher abgeschlossen sein müssen, oder leer]
```

**Schritt 3 — Risiken & offene Fragen:**

Identifiziere technische oder fachliche Risiken und nenne offene Fragen die vor der Umsetzung geklärt sein müssen.

**Schritt 4 — MCP-Call (wenn verfügbar):**

```
hivemind/propose_epic {{
  "project_id": "{project_id}",
  "title": "...",
  "description": "...",
  "rationale": "..."
}}
```

Falls nicht verfügbar: Gib den Proposal als Markdown-Block aus."""

    async def _kartograph(self, **_) -> str:
        # Load unexplored code nodes count
        from app.models.code_node import CodeNode
        try:
            unexplored_result = await self.db.execute(
                select(func.count()).select_from(CodeNode).where(
                    CodeNode.explored_at.is_(None)
                )
            )
            unexplored_count = unexplored_result.scalar_one()
        except Exception:
            unexplored_count = "?"

        return f"""## Rolle: Kartograph — Repo-Analyse & Wissensgraph

### Status
- Unexplorierte Code-Nodes: {unexplored_count}

### Verfügbare Write-Tools
- `hivemind/create_wiki_article` — Wiki-Artikel erstellen + explored_at setzen
- `hivemind/update_wiki_article` — Wiki-Artikel aktualisieren (versioniert)
- `hivemind/create_epic_doc` — Epic-Doc erstellen
- `hivemind/link_wiki_to_epic` — Wiki ↔ Epic verknüpfen
- `hivemind/propose_guard` — Guard vorschlagen (lifecycle=draft)
- `hivemind/propose_guard_change` — Guard-Änderung vorschlagen
- `hivemind/submit_guard_proposal` — Guard-Vorschlag einreichen (draft → pending_merge)

### Auftrag
1. Analysiere die Projektstruktur (Dateien, Module, Abhängigkeiten).
2. Identifiziere zentrale Komponenten und deren Beziehungen.
3. Erstelle Code-Nodes und Code-Edges für den Dependency-Graph.
4. **Erstelle Wiki-Artikel** für wichtige Komponenten.
5. Markiere Legacy-Code, Dead-Code und Hot-Paths.
6. Schlage Guards vor für kritische Code-Pfade.

### Konventionen
- Code-Nodes haben Typen: module, class, function, file, package
- Code-Edges beschreiben: imports, calls, inherits, implements
- Nutze `create_wiki_article` mit `code_node_paths` um explored_at zu setzen"""

    async def _triage(self, **_) -> str:
        """Enhanced triage prompt with unrouted items and epic context (TASK-6-008)."""
        # Load unrouted items
        unrouted_result = await self.db.execute(
            select(SyncOutbox).where(
                SyncOutbox.direction == "inbound",
                SyncOutbox.routing_state == "unrouted",
            ).order_by(SyncOutbox.created_at.desc()).limit(20)
        )
        unrouted_items = list(unrouted_result.scalars().all())
        unrouted_count = len(unrouted_items)

        # Load active epics for routing context
        epic_result = await self.db.execute(
            select(Epic).where(
                Epic.state.notin_(["done", "cancelled"])
            ).order_by(Epic.priority.desc(), Epic.created_at.asc())
        )
        active_epics = list(epic_result.scalars().all())

        # Load escalated tasks
        escalated_result = await self.db.execute(
            select(Task).where(Task.state == "escalated").order_by(Task.updated_at.asc())
        )
        escalated_tasks = list(escalated_result.scalars().all())

        # Build unrouted items section
        items_section = ""
        if unrouted_items:
            items_lines = []
            for item in unrouted_items:
                payload_summary = ""
                if item.payload:
                    payload_summary = str(item.payload)[:200]
                items_lines.append(
                    f"  - ID: {item.id} | Typ: {item.event_type or 'unknown'} | "
                    f"Erstellt: {item.created_at} | Payload: {payload_summary}"
                )
            items_section = "\n".join(items_lines)
        else:
            items_section = "  (keine ungerouteten Events)"

        # Build epic context section
        epic_lines = []
        for epic in active_epics[:15]:
            sla_info = f" | SLA: {epic.sla_due_at}" if epic.sla_due_at else ""
            epic_lines.append(
                f"  - {epic.epic_key}: {epic.title} [{epic.state}] "
                f"(Prio: {epic.priority}{sla_info})"
            )
        epics_section = "\n".join(epic_lines) if epic_lines else "  (keine aktiven Epics)"

        # Build escalated section
        escalated_lines = []
        for task in escalated_tasks[:10]:
            escalated_lines.append(
                f"  - {task.task_key}: {task.title} (qa_failed: {task.qa_failed_count}x)"
            )
        escalated_section = "\n".join(escalated_lines) if escalated_lines else "  (keine eskalierten Tasks)"

        return f"""## Rolle: Triage — Routing-Entscheidung

### Status
- Unrouted Events: {unrouted_count}
- Aktive Epics: {len(active_epics)}
- Eskalierte Tasks: {len(escalated_tasks)}

### Ungeroutete Events
{items_section}

### Verfügbare Epics (Routing-Ziele)
{epics_section}

### Eskalierte Tasks (priorisiert)
{escalated_section}

### Auftrag
1. Analysiere jeden ungerouteten Event: Was ist passiert? Welches Epic/Task betrifft es?
2. Für jeden Event: Bewerte die Confidence (0.0-1.0) der Zuordnung.
3. Route Events mit Confidence >= 0.85 direkt via `hivemind/route_event`.
4. Events mit Confidence < 0.85 → zur manuellen Prüfung markieren.
5. Events ohne Match → `hivemind/ignore_event` mit Begründung oder Eskalation.
6. Eskalierte Tasks prüfen: Können sie de-eskaliert werden?

### Routing-Empfehlung (pro Event)
Gib für jeden Event zurück:
```json
{{
  "event_id": "<id>",
  "recommended_epic": "<epic_key>",
  "confidence": 0.0-1.0,
  "reasoning": "<kurze Begründung>",
  "action": "route|ignore|escalate"
}}
```

### Entscheidungspfad
- Sentry-Error → Bug-Task anlegen oder existierenden Tasks zuordnen
- YouTrack-Update → State-Sync mit Hivemind-Task
- Federation-Event → Peer-Epic zuordnen oder DLQ prüfen
- Unbekannt → Eskalation an Admin"""

    # ── Data Loaders ───────────────────────────────────────────────────────

    async def _build_health_report_section(self) -> str:
        """Build Repo-Health-Report section for Stratege prompt (TASK-HEALTH-008).

        - If a wiki article with tag 'diagnostics' exists: render summary.
        - If no diagnostics article but code_nodes > 0: render warning hint.
        - Otherwise: return empty string.
        """
        from app.models.code_node import CodeNode

        # Check for diagnostics wiki article
        try:
            diag_result = await self.db.execute(
                select(WikiArticle)
                .where(WikiArticle.tags.any("diagnostics"))
                .order_by(WikiArticle.updated_at.desc())
                .limit(1)
            )
            diag_article = diag_result.scalar_one_or_none()
        except Exception:
            diag_article = None

        # Count code nodes
        try:
            node_count_result = await self.db.execute(
                select(func.count()).select_from(CodeNode)
            )
            code_node_count = node_count_result.scalar_one()
        except Exception:
            code_node_count = 0

        if diag_article:
            summary = _parse_health_report_summary(diag_article.content)
            date_str = diag_article.updated_at.strftime("%Y-%m-%d") if diag_article.updated_at else "unbekannt"
            return f"""
### 📊 Repo Health Report (vom {date_str})
{summary}

> Cleanup-Epic-Templates verfügbar für: hardcoded-css, duplicate-detection, layer-violations, magic-values.
> Health-Findings → Guard-Mapping: hardcoded-css → [no-hardcoded-colors, no-hardcoded-spacing] | layer-violations → [layer-boundaries] | file-size → [max-file-size]
"""

        if code_node_count > 0:
            return f"""
### ⚠ Kein Repo Health Report vorhanden
Das Repo ist kartiert ({code_node_count} Code-Nodes), aber es existiert noch kein Diagnostics-Wiki-Artikel.

**Empfehlung:** Kartograph mit Diagnostics-Phase ausführen bevor Epics geplant werden.
Dann stehen Cleanup-Epic-Templates und Health→Guard-Mappings automatisch zur Verfügung.

> Nächster Schritt: Repo Health Scan durchführen (`make health`)
"""
        return ""

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

    async def _resolve_pinned_skills(self, slugs: list[str]) -> list[Skill]:
        """Resolve pinned_skills slug list to Skill objects via source_slug."""
        if not slugs:
            self._unresolved_slugs = []
            return []
        result = await self.db.execute(
            select(Skill).where(
                Skill.source_slug.in_(slugs),
                Skill.lifecycle == "active",
                Skill.deleted_at.is_(None),
            ).order_by(Skill.title)
        )
        found = list(result.scalars().all())
        # Warn in prompt for slugs that could not be resolved
        found_slugs = {s.source_slug for s in found}
        self._unresolved_slugs = [s for s in slugs if s not in found_slugs]
        return found

    async def _resolve_skills_by_ids(self, skill_ids: list[uuid.UUID]) -> list[Skill]:
        if not skill_ids:
            return []
        result = await self.db.execute(
            select(Skill)
            .where(Skill.id.in_(skill_ids), Skill.deleted_at.is_(None))
            .order_by(Skill.title.asc())
        )
        return list(result.scalars().all())

    async def _get_task_linked_skills(self, task: Task) -> list[Skill]:
        result = await self.db.execute(
            select(Skill)
            .join(TaskSkill, TaskSkill.skill_id == Skill.id)
            .where(TaskSkill.task_id == task.id, Skill.deleted_at.is_(None))
            .order_by(Skill.title.asc())
        )
        return list(result.scalars().all())

    async def _get_task_context_boundary(self, task: Task) -> ContextBoundary | None:
        result = await self.db.execute(
            select(ContextBoundary).where(ContextBoundary.task_id == task.id).limit(1)
        )
        return result.scalar_one_or_none()

    def _format_pinned_skills(self, skills: list[Skill], raw_slugs: list[str]) -> str:
        """Render pinned skills as full content blocks for agent consumption."""
        if not raw_slugs:
            return "_Keine gepinnten Skills_"
        if not skills:
            return (
                f"_Slug-Liste: {', '.join(raw_slugs)} — Skills konnten nicht aufgelöst werden._\n"
                "_Führe `make migrate` und `seed_import` aus, um Skills zu indexieren._"
            )
        lines = []
        unresolved = getattr(self, "_unresolved_slugs", [])
        for skill in skills:
            lines.append(f"#### {skill.title} (`{skill.source_slug}`)")
            lines.append(skill.content.strip())
            lines.append("")
        if unresolved:
            lines.append(f"_Nicht aufgelöste Slugs: {', '.join(unresolved)}_")
        return "\n".join(lines)

    def _format_task_skill_overview(
        self,
        *,
        linked_skills: list[Skill],
        pinned_slugs: list[str],
        pinned_skills: list[Skill],
    ) -> str:
        lines: list[str] = []
        if linked_skills:
            lines.append("**Linked Skills (task_skills):**")
            for skill in linked_skills:
                lines.append(f"- {skill.title} (`{skill.source_slug or _slugify(skill.title)}`)")
        else:
            lines.append("_Keine linked Skills über `task_skills`._")

        if pinned_slugs:
            lines.append("")
            lines.append(f"**Pinned Skill Refs:** {', '.join(pinned_slugs)}")
            if pinned_skills:
                lines.append("**Aufgelöste Pinned Skills:**")
                for skill in pinned_skills:
                    lines.append(f"- {skill.title}")
            unresolved = getattr(self, "_unresolved_slugs", [])
            if unresolved:
                lines.append(f"_Nicht aufgelöste Pinned Refs: {', '.join(unresolved)}_")
        else:
            lines.append("")
            lines.append("_Keine Pinned Skills gesetzt._")

        return "\n".join(lines)

    def _format_task_context_boundary(
        self,
        *,
        task: Task,
        boundary: ContextBoundary | None,
        allowed_skills: list[Skill],
    ) -> str:
        if not boundary:
            return (
                "_Keine Context Boundary gesetzt._\n"
                "- Resource URI: "
                f"`hivemind://context-boundary/{task.task_key}`\n"
                "- Hinweis: Mit `hivemind/set_context_boundary` kann ein Scope gesetzt werden."
            )

        allowed_skill_titles = ", ".join(skill.title for skill in allowed_skills) or "_keine_"
        allowed_docs = ", ".join(str(doc_id) for doc_id in (boundary.allowed_docs or [])) or "_keine_"
        external_access = ", ".join(boundary.external_access or []) or "_kein externer Zugriff_"
        max_budget = boundary.max_token_budget or _DEFAULT_TOKEN_BUDGET

        return (
            f"- Resource URI: `hivemind://context-boundary/{task.task_key}`\n"
            f"- Max Token Budget: {max_budget}\n"
            f"- Allowed Skills: {allowed_skill_titles}\n"
            f"- Allowed Docs: {allowed_docs}\n"
            f"- External Access: {external_access}\n"
            f"- Version: {boundary.version}"
        )

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

    async def _get_epic_context_boundaries(self, epic_id: uuid.UUID) -> list[dict]:
        """Load context boundaries for all tasks of an epic."""
        result = await self.db.execute(
            select(ContextBoundary, Task.task_key)
            .join(Task, ContextBoundary.task_id == Task.id)
            .where(Task.epic_id == epic_id)
        )
        return [
            {
                "task_key": task_key,
                "max_token_budget": cb.max_token_budget,
                "allowed_skills": cb.allowed_skills,
            }
            for cb, task_key in result.all()
        ]

    async def _get_epic_wiki_articles(self, epic: Epic) -> list[WikiArticle]:
        """Load wiki articles linked to this epic or matching its tags."""
        from sqlalchemy import or_, cast
        from sqlalchemy.dialects.postgresql import ARRAY, TEXT as PG_TEXT

        conditions = []
        # Articles explicitly linked to this epic
        conditions.append(WikiArticle.linked_epics.any(str(epic.id)))
        # Articles whose tags overlap with epic tags (if epic has tags)
        # Use ILIKE on slug for phase-based matching (e.g. epic_key "EPIC-PHASE-5" → slug containing "phase-5")
        epic_phase = epic.epic_key.lower().replace("epic-", "") if epic.epic_key else ""
        if epic_phase:
            conditions.append(WikiArticle.slug.ilike(f"%{epic_phase}%"))
            conditions.append(WikiArticle.title.ilike(f"%{epic_phase}%"))

        result = await self.db.execute(
            select(WikiArticle).where(or_(*conditions)).limit(10)
        )
        return list(result.scalars().all())

    async def _get_epic_dependencies(self, external_id: str) -> list[Epic]:
        """Load epics that this epic depends on (via seed depends_on in external_id)."""
        # Look for epics that might be dependencies — check all epics and find
        # ones whose external_id appears in common dependency naming patterns
        # e.g. EPIC-PHASE-5 depends on EPIC-PHASE-4
        phase_num = None
        for part in external_id.split("-"):
            try:
                phase_num = int(part)
                break
            except ValueError:
                continue

        if phase_num is None or phase_num <= 1:
            return []

        # Load the predecessor epic
        predecessor_key = external_id.rsplit("-", 1)[0] + f"-{phase_num - 1}"
        result = await self.db.execute(
            select(Epic).where(Epic.epic_key == predecessor_key)
        )
        predecessor = result.scalar_one_or_none()
        return [predecessor] if predecessor else []

    async def _get_task_guards(self, task: Task) -> list[dict]:
        tg_result = await self.db.execute(
            select(TaskGuard, Guard)
            .join(Guard, TaskGuard.guard_id == Guard.id)
            .where(TaskGuard.task_id == task.id)
        )
        results = []
        for tg, g in tg_result.all():
            # Derive source: if guard has command and checked_by is set = system, else self-reported
            source = "self-reported" if tg.checked_by else "pending"
            if g.command and tg.checked_by:
                source = "system-executed"
            results.append({
                "title": g.title, "type": g.type, "command": g.command,
                "status": tg.status, "skippable": g.skippable,
                "source": source,
                "checked_at": str(tg.checked_at) if tg.checked_at else None,
                "output": tg.result,
            })
        return results

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

    def _format_guards_with_provenance(self, guards: list[dict]) -> str:
        """Format guards with provenance info for review prompt."""
        if not guards:
            return "_Keine Guards konfiguriert_"
        lines = []
        for g in guards:
            source = g.get("source", "unknown")
            checked_at = g.get("checked_at", "")
            output = g.get("output", "")
            status = g["status"]
            badge = f"[{source}]" if source else ""
            warning = ""
            if source == "self-reported" and not output:
                warning = " ⚠ KEIN OUTPUT"
            time_str = f" @ {checked_at}" if checked_at else ""
            lines.append(
                f"- [{status}] {g['title']} ({g['type']}) {badge}{time_str}"
                f"{' [skippable]' if g.get('skippable') else ''}{warning}"
            )
        return "\n".join(lines)

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
