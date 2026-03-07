---
title: "Review-Recommendation: AI-Reviewer MCP-Write-Tool"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy", "pydantic"]
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

## Skill: Review-Recommendation (Reviewer-Agent Write-Tool)

### Rolle
Du implementierst das MCP-Write-Tool `hivemind-submit_review_recommendation` und den zugehörigen Governance-Flow. Der Reviewer ist der 7. AI-Agent — er prüft Task-Ergebnisse gegen DoD, Guards und Skills und gibt eine Confidence-basierte Empfehlung ab. Das Tool ändert **nie** direkt den Task-State.

### Kontext
Der Reviewer-Agent wird vom Conductor dispatcht wenn `governance.review ≠ 'manual'`. Seine Empfehlung wird in `review_recommendations` gespeichert. Je nach Governance-Level:
- `assisted`: Owner sieht AI-Empfehlung + 1-Click Approve/Reject
- `auto`: Bei Confidence ≥ Threshold → Auto-Approve mit Grace Period
- Vor Worker-/Review-Prompts und spaetestens am `in_review`-Gate materialisiert das Backend alle passenden aktiven Guards in `task_guards`, damit der Reviewer denselben Guard-Stand sieht, den auch das State-Gate enforced.
- Der Auto-Approve-Pfad darf den Task-State nie direkt setzen. Er muss denselben kanonischen Abschluss-Service wie `approve_review` nutzen, damit EXP, `task_done`, Epic-Abschlusspruefung und der nachgelagerte Gaertner-Dispatch erhalten bleiben.
- `reject`-Empfehlungen fuehren nie zu Auto-Reject. Reale Rejects laufen weiterhin ueber den kanonischen `reject_review`-Pfad und erzeugen `task_qa_failed`, damit der Gaertner gezielt Review-Feedback destillieren kann.

Ist-Stand-Hinweis:
- Der Review-Flow ist derzeit der Governance-Typ mit dem saubersten Unterschied zwischen `assisted` und `auto`.
- Andere Governance-Typen koennen ebenfalls AI-Dispatch aktivieren, besitzen aber aktuell noch keinen gleichwertig ausmodellierten Auto-Abschluss.

### Konventionen
- MCP-Tool in `app/mcp/tools/reviewer_write_tools.py`
- Model in `app/models/review_recommendation.py`
- Reviewer-spezifische Ablage/Abfragen in `app/services/review_service.py`
- Kanonischer State-Abschluss in `app/services/review_workflow.py`
- Das Tool erfordert die `reviewer`-Permission (system-intern, nicht user-aufrufbar)
- `submit_review_recommendation` speichert nur — es ruft **nie** `approve_review` oder `reject_review` auf
- Die Governance-Logik entscheidet nach dem Speichern über den nächsten Schritt

### Datenmodell

```python
class ReviewRecommendation(Base):
    __tablename__ = "review_recommendations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"))
    recommendation: Mapped[str] = mapped_column(String(30))  # approve, reject, needs_human_review
    confidence: Mapped[float] = mapped_column()  # 0.0–1.0
    summary: Mapped[str] = mapped_column(Text)
    checklist: Mapped[dict | None] = mapped_column(JSONB)  # [{criterion, status, detail}]
    concerns: Mapped[list | None] = mapped_column(JSONB)  # Strings bei reject/needs_human_review
    governance_level: Mapped[str] = mapped_column(String(20))  # assisted, auto
    auto_approved: Mapped[bool] = mapped_column(default=False)
    auto_approve_at: Mapped[datetime | None] = mapped_column()  # Grace Period Ende
    vetoed: Mapped[bool] = mapped_column(default=False)
    vetoed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    conductor_dispatch_id: Mapped[UUID | None] = mapped_column(ForeignKey("conductor_dispatches.id"))
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### MCP-Tool-Implementierung

```python
async def handle_submit_review_recommendation(args: dict) -> list[TextContent]:
    body = ReviewRecommendationInput(**args)

    async with get_db() as db:
        actor = await resolve_actor(db, args.get("_actor_id"))
        require_permission(actor, "reviewer")

        # 1. Task laden + validieren
        task = await TaskService(db).get_by_key(body.task_key)
        if task.state != "in_review":
            raise ToolError(f"Task {body.task_key} is not in_review (current: {task.state})")

        # 2. Empfehlung speichern
        governance = await GovernanceService(db).get_governance_config()
        recommendation = ReviewRecommendation(
            task_id=task.id,
            recommendation=body.recommendation,
            confidence=body.confidence,
            summary=body.summary,
            checklist=body.checklist,
            concerns=body.concerns,
            governance_level=governance.review,
        )

        # 3. Auto-Approve-Logik (nur bei governance.review = 'auto')
        if governance.review == "auto":
            if await GovernanceService(db).check_auto_allowed("review", {
                "recommendation": body.recommendation,
                "confidence": body.confidence,
            }):
                grace_minutes = governance.auto_review_grace_minutes
                recommendation.auto_approve_at = datetime.utcnow() + timedelta(minutes=grace_minutes)
                # APScheduler-Job für Grace-Period-Ablauf registrieren
                # → Nach Ablauf: approve_review automatisch ausführen

        db.add(recommendation)

        # 4. Audit-Log
        await AuditService(db).log(
            actor_id=actor.id,
            action="submit_review_recommendation",
            entity_type="task",
            entity_id=str(task.id),
            input_snapshot=args,
            output_snapshot={
                "recommendation_id": str(recommendation.id),
                "recommendation": body.recommendation,
                "confidence": body.confidence,
            },
        )

        # 5. Notification an Owner
        await event_bus.publish(ReviewRecommendationEvent(
            task_id=task.id,
            recommendation=body.recommendation,
            confidence=body.confidence,
        ))

        await db.commit()

        return [TextContent(type="text", text=json.dumps({
            "data": {
                "recommendation_id": str(recommendation.id),
                "recommendation": body.recommendation,
                "confidence": body.confidence,
                "governance_action": _describe_action(governance.review, recommendation),
            },
            "meta": {},
        }))]

def _describe_action(level: str, rec: ReviewRecommendation) -> str:
    if level == "auto" and rec.auto_approve_at:
        return f"Auto-approve scheduled at {rec.auto_approve_at.isoformat()}"
    if level == "assisted":
        return "Recommendation stored. Owner will see 1-click confirmation."
    return "Manual review required."
```

### Grace-Period-Flow (Auto-Modus)

```python
# In scheduler.py registriert:
async def check_auto_review_grace_periods():
    """Cron-Job: prüft abgelaufene Grace Periods und führt auto-approve aus."""
    async with get_db() as db:
        expired = await db.scalars(
            select(ReviewRecommendation).where(
                ReviewRecommendation.auto_approve_at <= datetime.utcnow(),
                ReviewRecommendation.auto_approved == False,
                ReviewRecommendation.vetoed == False,
                ReviewRecommendation.recommendation == "approve",
            )
        )
        for rec in expired:
            task = await db.get(Task, rec.task_id)
            if task.state == "in_review":  # Noch nicht manuell entschieden
                await approve_task_review(
                    db,
                    task,
                    comment="Auto-approved after grace period",
                )
                rec.auto_approved = True
                await db.commit()
```

Dabei gilt zwingend:
- kein direktes `task.state = "done"` im Cron-Job
- derselbe Abschluss-Service fuer manuellen und automatischen Review-Approve
- der komplette Folgepfad (`task_done` → Gaertner) muss identisch bleiben

### Veto-Endpoint (Owner unterbricht Grace Period)

```python
@router.post("/api/tasks/{task_key}/review/veto")
async def veto_auto_review(
    task_key: str,
    db: AsyncSession = Depends(get_db),
    actor = Depends(get_current_user),
):
    """Owner unterbricht Auto-Review Grace Period."""
    recommendation = await ReviewService(db).get_active_recommendation(task_key)
    if not recommendation or not recommendation.auto_approve_at:
        raise HTTPException(404, "No active auto-review for this task")
    recommendation.vetoed = True
    recommendation.vetoed_by = actor.id
    await db.commit()
    return {"status": "vetoed", "task_key": task_key}
```

### Sicherheitsprinzipien
- **Auto-Reject gibt es NICHT** — `reject`-Empfehlung erfordert immer menschliche Bestätigung
- **Grace Period** — Owner kann innerhalb des Zeitfensters widersprechen (Veto)
- `submit_review_recommendation` ändert **nie** direkt den Task-State
- Auto-Approve nutzt den kanonischen Review-Workflow-Service statt Sonderlogik im Cron-Job
- Jede Empfehlung wird vollständig im Audit-Trail geloggt
- Confidence < Threshold → immer Fallback auf `assisted` (nie blockieren)
