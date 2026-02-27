# Gamification — EXP, Badges & Levels

← [Index](../../masterplan.md)

**Skeleton aktiv ab:** Phase 1 (Seed-Daten anlegen)
**EXP-Logik aktiv ab:** Phase 5 (Worker & Gaertner Writes)
**Leaderboard & Badges sichtbar ab:** Phase 5

---

## Philosophie

Gamification in Hivemind ist **nicht aufgesetzt** — es ist eine Übersetzung echter Entwicklerarbeit in Spielmechaniken. Jede EXP-Vergabe entspricht einer messbaren Leistung. Keine Dark Patterns, keine erzwungene Interaktion. Wer lieber ohne Punkte arbeitet, ignoriert die Anzeige einfach.

```text
Real Work → Gamification Frame
─────────────────────────────────────────────
Task abschließen       → Quest erfüllt, Loot (Artifacts)
Skill publishen        → Gildenwissen erweitern
Review bestehen        → Bewährungsprüfung
Peer helfen (Delegation) → Mercenary-Mission
Code explorieren       → Fog of War lichten, neue Gebiete
```

---

## EXP-Vergabe — Vollständige Tabelle

EXP wird bei erfolgreichen Events vergeben. Kein EXP bei Fehlern, Abbrüchen oder durch Spam.

| Event | EXP | Trigger | Anti-Spam |
| --- | --- | --- | --- |
| **Task `done`** | 50 | `approve_review` → Task-State `done` | 1x pro Task |
| **Task `done` ohne `qa_failed`** (Clean Run) | +20 Bonus | Kein `qa_failed`-Event in Task-History | 1x pro Task |
| **Task `done` mit SLA eingehalten** | +10 Bonus | `task.done_at <= task.sla_due_at` (wenn SLA gesetzt) | 1x pro Task |
| **Review als Owner durchgeführt** | 15 | `approve_review` oder `reject_review` (beide) | 1x pro Review-Aktion |
| **Skill als Draft eingereicht** | 10 | `submit_skill_proposal` | 1x pro Skill-Proposal |
| **Skill gemergt (Active)** | 30 | `merge_skill` → Skill `active` | 1x pro Skill |
| **Guard gemergt (Active)** | 30 | `merge_guard` → Guard `active` | 1x pro Guard |
| **Skill-Change-Proposal akzeptiert** | 20 | `accept_skill_change` | 1x pro Change |
| **Wiki-Artikel erstellt** | 15 | `create_wiki_article` (Gaertner/Kartograph) | 1x pro Artikel |
| **Wiki-Artikel aktualisiert** | 5 | `update_wiki_article` | max 1x/Tag pro Artikel |
| **Code-Node exploriert** | 2 | Kartograph erstellt neuen `code_node` | 1x pro Node |
| **Discovery Session gestartet + abgeschlossen** | 10 | `end_discovery_session` (nur wenn mind. 5 Nodes entdeckt) | 1x pro Session |
| **Epic Proposal akzeptiert** | 25 | `accept_epic_proposal` | 1x pro Proposal |
| **Delegierten Task als Peer erfüllt** | 60 | Task `done` auf Peer-Node (Mercenary-Bonus) | 1x pro delegiertem Task |
| **Decision Record erstellt** | 10 | `create_decision_record` (Gaertner) | max 3x/Tag |

### Multiplier (Stack additiv, nicht multiplikativ)

| Bedingung | Multiplier |
| --- | --- |
| Node ist Gilde-Mitglied (Federation aktiv) | +10% EXP auf alles |
| Peer-assisted Task (Shared Epic) | +5% EXP auf Task-Done-Events |

> **Hinweis Multiplier:** Werden erst ab Phase F aktiv. In Solo-Betrieb und ohne Federation: Basis-EXP ohne Multiplier.

---

## Level-System

Level steigen linear mit einem festen Schwellwert pro Level. Keine exponentielle Kurve — EXP soll sich immer bedeutsam anfühlen, auch in höheren Levels.

| Level | EXP-Schwelle (kumulativ) | Titel |
| --- | --- | --- |
| 1 | 0 | Rookie Kommandant |
| 2 | 100 | Einsatz-Kommandant |
| 3 | 250 | Veteran |
| 4 | 500 | Elite-Kommandant |
| 5 | 1000 | Meister-Kommandant |
| 6 | 2000 | Gilden-Ältester |
| 7 | 4000 | Legenden-Kommandant |
| 8 | 8000 | Hivemind-Architekt |
| 9 | 15000 | Sovereign |
| 10 | 30000 | Grand Sovereign |

**Level-Up-Trigger:** `user_achievements.exp_total` überschreitet nächsten Schwellwert → `user_achievements.level` wird erhöht → SSE-Event `level_up` an Client → UI zeigt Level-Up-Animation.

**Formel für aktuelles Level:**
```python
def get_level(exp_total: int) -> int:
    thresholds = [0, 100, 250, 500, 1000, 2000, 4000, 8000, 15000, 30000]
    level = 1
    for i, threshold in enumerate(thresholds):
        if exp_total >= threshold:
            level = i + 1
    return level

def get_exp_to_next_level(exp_total: int) -> int | None:
    thresholds = [0, 100, 250, 500, 1000, 2000, 4000, 8000, 15000, 30000]
    level = get_level(exp_total)
    if level >= len(thresholds):
        return None  # Max Level
    return thresholds[level] - exp_total
```

---

## Badges

Badges sind einmalige Errungenschaften. Sie werden **nicht rückwirkend** vergeben — nur wenn die Bedingung nach Phase-5-Aktivierung erfüllt wird.

### Kategorie: Quests

| Badge | Titel | Bedingung | EXP-Bonus |
| --- | --- | --- | --- |
| `first_blood` | Erster Strike | Ersten Task abschließen | +25 |
| `clean_sweep` | Makellose Serie | 5 Tasks hintereinander ohne `qa_failed` (Clean Run) | +50 |
| `speed_demon` | Blitzkrieger | Task in < 1h nach `in_progress` auf `done` (SLA eingehalten) | +30 |
| `marathon` | Marathonläufer | Task mit > 7 Tagen `in_progress` abschließen | +20 |
| `century` | Centurion | 100 Tasks abgeschlossen | +100 |

### Kategorie: Wissen

| Badge | Titel | Bedingung | EXP-Bonus |
| --- | --- | --- | --- |
| `first_skill` | Erster Schmied | Ersten Skill publishen (gemergt) | +30 |
| `skill_master` | Skill-Meister | 10 Skills gemergt | +100 |
| `wiki_scribe` | Gilden-Schreiber | 20 Wiki-Artikel erstellt | +75 |
| `knowledge_base` | Wissenshüter | 50 Wiki-Artikel erstellt | +200 |

### Kategorie: Exploration

| Badge | Titel | Bedingung | EXP-Bonus |
| --- | --- | --- | --- |
| `pioneer` | Pionier | Ersten Code-Node exploriert | +20 |
| `cartographer` | Kartograph der Gilde | 50 Code-Nodes exploriert | +50 |
| `fog_lifter` | Nebellichter | 200 Code-Nodes exploriert | +150 |
| `mapmaker` | Weltenkartograf | 500 Code-Nodes exploriert | +300 |

### Kategorie: Federation

| Badge | Titel | Bedingung | EXP-Bonus |
| --- | --- | --- | --- |
| `first_contact` | Erster Kontakt | Ersten Peer-Node verbunden | +40 |
| `guild_founder` | Gilden-Gründer | 3+ Nodes in der Gilde verbunden | +75 |
| `mercenary` | Söldner | Ersten delegierten Task als Peer erfüllt | +50 |
| `elite_mercenary` | Elite-Söldner | 10 delegierte Tasks als Peer erfüllt | +100 |
| `skill_sharer` | Wissens-Händler | Ersten Skill in Federation geteilt | +30 |

### Kategorie: Governance

| Badge | Titel | Bedingung | EXP-Bonus |
| --- | --- | --- | --- |
| `first_review` | Erster Richter | Ersten Task reviewed | +20 |
| `judge` | Richter | 50 Reviews durchgeführt | +100 |
| `no_escalation_30` | Friedensstifter | 30 Tage ohne Eskalation | +80 |

---

## Datenmodell

```sql
-- Seed-Daten Phase 1: Tabellen anlegen, EXP-Logik NICHT aktiv (Werte bleiben 0)
CREATE TABLE user_achievements (
    user_id         UUID PRIMARY KEY REFERENCES users(id),
    exp_total       INTEGER NOT NULL DEFAULT 0,
    level           INTEGER NOT NULL DEFAULT 1,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_badges (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id),
    badge_key   TEXT NOT NULL,          -- 'first_blood', 'pioneer', etc.
    awarded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, badge_key)         -- Ein Badge kann nur einmal vergeben werden
);

-- Referenztabelle für Badge-Definitionen (Seed-Daten)
CREATE TABLE badge_definitions (
    badge_key   TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    category    TEXT NOT NULL,          -- 'quest', 'knowledge', 'exploration', 'federation', 'governance'
    exp_bonus   INTEGER NOT NULL DEFAULT 0,
    icon        TEXT                    -- Icon-Name aus Design-System
);

-- Level-Schwellwerte (Seed-Daten)
CREATE TABLE level_thresholds (
    level       INTEGER PRIMARY KEY,
    exp_required INTEGER NOT NULL,
    title       TEXT NOT NULL
);

-- EXP-Event-Log (Audit-Trail)
CREATE TABLE exp_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id),
    event_type  TEXT NOT NULL,          -- 'task_done', 'skill_merged', etc.
    entity_id   UUID,                   -- Task-ID, Skill-ID etc.
    exp_awarded INTEGER NOT NULL,
    reason      TEXT,                   -- Freitext für Sonderfälle
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON exp_events (user_id, created_at DESC);
```

---

## EXP-Vergabe-Mechanismus

EXP wird **nie direkt** in `user_achievements` geschrieben — immer via `award_exp(user_id, event_type, entity_id, exp)`:

```python
async def award_exp(
    db: AsyncSession,
    user_id: UUID,
    event_type: str,
    exp: int,
    entity_id: UUID | None = None,
    reason: str | None = None,
) -> None:
    # 1. Anti-Spam-Check: Wurde dieses Event für diese Entity schon vergeben?
    if entity_id:
        existing = await db.scalar(
            select(ExpEvent).where(
                ExpEvent.user_id == user_id,
                ExpEvent.event_type == event_type,
                ExpEvent.entity_id == entity_id,
            )
        )
        if existing:
            return  # Idempotent — kein doppelter EXP

    # 2. EXP-Event loggen
    event = ExpEvent(user_id=user_id, event_type=event_type, entity_id=entity_id,
                     exp_awarded=exp, reason=reason)
    db.add(event)

    # 3. user_achievements aktualisieren
    achievement = await db.get(UserAchievement, user_id)
    old_level = achievement.level
    achievement.exp_total += exp
    achievement.level = get_level(achievement.exp_total)

    # 4. Level-Up-Event auslösen (wenn Level gestiegen)
    if achievement.level > old_level:
        await emit_sse_event("level_up", {
            "user_id": str(user_id),
            "new_level": achievement.level,
            "title": get_level_title(achievement.level),
        })

    # 5. Badge-Check (asynchron, non-blocking)
    await check_and_award_badges(db, user_id, event_type)
```

---

## UI-Integration

### EXP-Anzeige in der Prompt Station

```text
┌─ PROMPT STATION ─────────────────────────────────────┐
│  [TASK-88 ✓ DONE]                                    │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  +50 EXP  (Clean Run: +20)  (SLA: +10)               │
│  ████████████████░░░░░░░░  640 / 1000  LVL 4 → LVL 5 │
└──────────────────────────────────────────────────────┘
```

### Leaderboard (Gilde-View, ab Phase F)

```text
┌─ GILDE — RANGLISTE ──────────────────────────────────┐
│  #1  ◈ alex-hivemind    LVL 6  ████  2340 EXP  [≡]  │
│  #2  ◈ ben-hivemind     LVL 5  ███░  1180 EXP  [≡]  │
│  #3  ◈ clara-hivemind   LVL 4  ██░░   720 EXP  [≡]  │
│                         [BADGES ANZEIGEN ▾]          │
└──────────────────────────────────────────────────────┘
```

Das Leaderboard zeigt nur Peers in der Gilde (Federation). Im Solo-Modus ist es nicht sichtbar.

### Phase 1–4: Stille Akkumulation

In Phase 1–4 ist die EXP-Logik nicht aktiv — `user_achievements.exp_total` bleibt 0. Die Tabellen existieren (Seed-Daten), aber keine Events werden gefeuert. Ab Phase 5 startet die Vergabe für zukünftige Events (keine Rückdatierung).

---

## Konfiguration

| Env-Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_GAMIFICATION_ENABLED` | `true` | Gamification komplett deaktivieren (alle EXP-Calls = Noop) |
| `HIVEMIND_EXP_MULTIPLIER_FEDERATION` | `1.1` | Globaler EXP-Multiplier wenn Federation aktiv (10% Bonus) |
| `HIVEMIND_EXP_MULTIPLIER_PEER_ASSIST` | `1.05` | Zusätzlicher Multiplier für Peer-assisted Tasks |
