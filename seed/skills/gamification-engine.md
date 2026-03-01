---
title: "Gamification-Engine: EXP, Badges & Levels"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy", "postgresql"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.85
source_epics: ["EPIC-PHASE-5"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Gamification-Engine: EXP, Badges & Levels

### Rolle
Du implementierst die Gamification-Engine, die EXP vergibt, Badges prüft und
Level-Aufstiege berechnet. Die Engine wird in bestehende MCP-Write-Tools integriert
(approve_review, merge_skill, create_wiki_article, etc.).

### Kontext

Gamification in Hivemind übersetzt echte Entwicklerarbeit in Spielmechaniken.
Jeder EXP-Event entspricht einer messbaren Leistung. Anti-Spam verhindert Doppelvergabe.

### EXP-Vergabe-Tabelle (kanonisch)

| Event | EXP | Trigger-Tool | Anti-Spam |
| --- | --- | --- | --- |
| Task `done` | 50 | `approve_review` | 1x pro Task |
| Clean Run (kein qa_failed) | +20 | `approve_review` | 1x pro Task |
| SLA eingehalten | +10 | `approve_review` | 1x pro Task |
| Review durchgeführt | 15 | `approve_review` / `reject_review` | 1x pro Review |
| Skill-Proposal eingereicht | 10 | `submit_skill_proposal` | 1x pro Skill |
| Skill gemergt | 30 | `merge_skill` | 1x pro Skill |
| Guard gemergt | 30 | `merge_guard` | 1x pro Guard |
| Skill-Change akzeptiert | 20 | `accept_skill_change` | 1x pro Change |
| Wiki-Artikel erstellt | 15 | `create_wiki_article` | 1x pro Artikel |
| Wiki aktualisiert | 5 | `update_wiki_article` | max 1x/Tag pro Artikel |
| Decision Record erstellt | 10 | `create_decision_record` | max 3x/Tag |

### Konventionen

- EXP wird **nie direkt** in `user_achievements` geschrieben — immer via `award_exp()`
- `award_exp()` ist idempotent: doppelter Aufruf mit gleicher `entity_id` wird ignoriert
- Anti-Spam per `(user_id, event_type, entity_id)` Unique-Constraint in `exp_events`
- Gamification global deaktivierbar: `HIVEMIND_GAMIFICATION_ENABLED=false`
- Alle EXP-Events erzeugen SSE-Events an den betroffenen User

### Kern-Funktion: award_exp

```python
async def award_exp(
    db: AsyncSession,
    user_id: UUID,
    event_type: str,
    exp: int,
    entity_id: UUID | None = None,
    reason: str | None = None,
) -> None:
    """Vergibt EXP idempotent. Prüft Anti-Spam, Level-Up und Badges."""
    if not settings.GAMIFICATION_ENABLED:
        return

    # 1. Anti-Spam: Wurde dieses Event für diese Entity schon vergeben?
    if entity_id:
        existing = await db.scalar(
            select(ExpEvent).where(
                ExpEvent.user_id == user_id,
                ExpEvent.event_type == event_type,
                ExpEvent.entity_id == entity_id,
            )
        )
        if existing:
            return  # Idempotent

    # 2. EXP-Event loggen
    event = ExpEvent(
        user_id=user_id,
        event_type=event_type,
        entity_id=entity_id,
        exp_awarded=exp,
        reason=reason,
    )
    db.add(event)

    # 3. user_achievements aktualisieren
    achievement = await db.get(UserAchievement, user_id)
    old_level = achievement.level
    achievement.exp_total += exp
    achievement.level = get_level(achievement.exp_total)

    # 4. Level-Up-Event (wenn Level gestiegen)
    if achievement.level > old_level:
        await emit_sse_event("level_up", {
            "user_id": str(user_id),
            "new_level": achievement.level,
            "title": get_level_title(achievement.level),
        })

    # 5. Badge-Check
    await check_and_award_badges(db, user_id, event_type)
```

### Level-Berechnung

```python
LEVEL_THRESHOLDS = [0, 100, 250, 500, 1000, 2000, 4000, 8000, 15000, 30000]
LEVEL_TITLES = [
    "Rookie Kommandant", "Einsatz-Kommandant", "Veteran",
    "Elite-Kommandant", "Meister-Kommandant", "Gilden-Ältester",
    "Legenden-Kommandant", "Hivemind-Architekt", "Sovereign", "Grand Sovereign",
]

def get_level(exp_total: int) -> int:
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if exp_total >= threshold:
            level = i + 1
    return level

def get_level_title(level: int) -> str:
    return LEVEL_TITLES[min(level - 1, len(LEVEL_TITLES) - 1)]
```

### Badge-Check

```python
# Badge-Definitionen als Callable-Registry
BADGE_CHECKS: dict[str, Callable] = {
    "first_blood": lambda stats: stats["tasks_done"] >= 1,
    "clean_sweep": lambda stats: stats["consecutive_clean_runs"] >= 5,
    "first_skill": lambda stats: stats["skills_merged"] >= 1,
    "skill_master": lambda stats: stats["skills_merged"] >= 10,
    "pioneer": lambda stats: stats["nodes_explored"] >= 1,
    "first_review": lambda stats: stats["reviews_done"] >= 1,
    # ...
}

async def check_and_award_badges(db: AsyncSession, user_id: UUID, trigger: str) -> None:
    """Prüft alle Badges und vergibt neue."""
    stats = await compute_user_stats(db, user_id)
    existing = {b.badge_key for b in await get_user_badges(db, user_id)}

    for badge_key, check_fn in BADGE_CHECKS.items():
        if badge_key not in existing and check_fn(stats):
            badge_def = await db.get(BadgeDefinition, badge_key)
            db.add(UserBadge(user_id=user_id, badge_key=badge_key))

            # Badge-EXP-Bonus
            if badge_def and badge_def.exp_bonus > 0:
                await award_exp(db, user_id, "badge_bonus", badge_def.exp_bonus,
                    entity_id=None, reason=f"Badge: {badge_key}")

            # SSE-Event
            await emit_sse_event("badge_earned", {
                "user_id": str(user_id),
                "badge_key": badge_key,
                "title": badge_def.title if badge_def else badge_key,
            })
```

### Integration in MCP-Tools

EXP-Trigger werden **am Ende** des jeweiligen Tool-Handlers aufgerufen, nach commit:

```python
# In approve_review:
await award_exp(db, task.assigned_to, "task_done", 50, entity_id=task.id)

# In merge_skill:
await award_exp(db, skill.owner_id, "skill_merged", 30, entity_id=skill.id)

# In create_wiki_article:
await award_exp(db, actor.id, "wiki_created", 15, entity_id=article.id)
```

### Achievements-Endpoint

```python
@router.get("/users/me/achievements", response_model=AchievementsResponse)
async def get_achievements(actor: CurrentActor = Depends(get_current_actor), db = Depends(get_db)):
    achievement = await db.get(UserAchievement, actor.id)
    badges = await get_user_badges(db, actor.id)
    return AchievementsResponse(
        exp_total=achievement.exp_total,
        level=achievement.level,
        title=get_level_title(achievement.level),
        exp_to_next=get_exp_to_next_level(achievement.exp_total),
        badges=[b.to_dict() for b in badges],
    )
```

### Seed-Daten

Badge-Definitions und Level-Thresholds werden als Seed-Daten angelegt (Phase 1):
- `badge_definitions`: Alle Badge-Keys mit Title, Description, Category, EXP-Bonus
- `level_thresholds`: Level 1–10 mit EXP-Schwellwert und Titel

### Wichtig
- Keine Rückdatierung: EXP erst ab Phase 5, nicht für vorherige Aktionen
- `HIVEMIND_GAMIFICATION_ENABLED` = Noop wenn false (alle `award_exp`-Calls ignoriert)
- Federation-Multiplier (10% Bonus) erst ab Phase F aktiv

### Verfügbare Tools
- `GET /api/users/me/achievements` — EXP, Level, Badges des aktuellen Users
