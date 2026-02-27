# Kartograph — Fog-of-War Explorer

← [Agenten-Übersicht](./overview.md) | [Index](../../masterplan.md)

Der Kartograph arbeitet nach dem **Fog-of-War-Prinzip**: maximale Zugangsberechtigung, aber nicht allwissend. Er entdeckt aktiv — was er noch nicht abgefragt hat, sieht er nicht.

> Analogie: Ein Soldat mit Geländezugang ohne Sperrzonen — aber er muss trotzdem jeden Hügel selbst besteigen.

---

## Kernaufgaben

1. **Repo-Analyse (Bootstrap)** — Initial auf ein Code-Repository losgelassen; kartiert die Systemlandschaft von Grund auf
2. **Systemkartierung** — Erstellt und pflegt das Wiki als lebendige, wachsende Karte des Gesamtsystems
3. **Cross-Epic-Analyse** — Erkennt Muster, Redundanzen und Abhängigkeiten durch aktives Erkunden mehrerer Epics
4. **Epic-Dokumentation** — Schreibt initiale Epic-Docs bevor der Architekt zerlegt
5. **Skill-Gap-Analyse** — Identifiziert fehlende Skills durch Vergleich abgeschlossener Epics
6. **Epic-Restructuring-Proposals** — Schlägt vor wenn Epics falsch geschnitten sind

---

## RBAC

```json
{
  "role": "kartograph",
  "permissions": {
    "read_any_epic": true,
    "read_any_wiki": true,
    "read_any_skill": true,
    "read_any_doc": true,
    "context_boundary_filter": false,
    "write_wiki": true,
    "write_epic_docs": true,
    "propose_epic_restructure": true,
    "propose_skill": true,
    "propose_skill_change": true,
    "write_tasks": false,
    "execute_tasks": false,
    "merge_skills": false
  }
}
```

> **`propose_skill` für den Kartographen:** Der Kartograph ist der einzige Agent neben dem Gaertner mit direktem Skill-Proposal-Recht. Begründung: Er sieht als einziger das gesamte Repository und entdeckt Codebase-weite Coding-Patterns (z.B. "dieses Repo nutzt überall Repository-Pattern + Service-Layer") — das sind perfekte Skill-Kandidaten die ohne Umweg über den Gaertner formalisierbar sind. Analog zu `propose_guard` (das der Kartograph bereits hat): Guards beschreiben *was geprüft wird*, Skills beschreiben *wie gearbeitet wird* — beides entsteht durch Code-Analyse.

---

## Bootstrap — Repo-Analyse

Wenn ein neues Projekt gestartet wird, generiert Hivemind einen **Initial-Kartograph-Prompt**. Der User führt ihn im AI-Client aus. Der AI-Client hat dabei Zugriff auf das lokale Repository (Dateisystem, Git-History).

```
Eingabe:  Repo-Pfad + optionale Starthinweise
Ablauf:   Hivemind generiert Prompt → User führt in AI-Client aus
          AI erkundet Repo + Hivemind-Daten → schreibt Wiki-Artikel, Epic-Docs
Ausgabe:  Wachsende Systemkarte in Hivemind (Wiki + Nexus Grid Nodes)
```

---

## Typischer Workflow (Fog of War)

```
1. Hivemind generiert Initial-Kartograph-Prompt für Repo X
   User fügt Prompt in AI-Client ein

2. AI-Client fragt aktiv nach was es braucht:
   hivemind/search_wiki { "query": "authentication" }
   → findet nichts → weiß: das muss noch kartiert werden

3. AI liest Repo-Dateien (eigene Filesystem-Zugriffe)
   → erkennt Auth-Muster in /src/auth/

4. AI schreibt Erkenntnis in Hivemind:
   hivemind/create_wiki_article { "title": "Auth-Architektur", "slug": "auth-architektur", "content": "...", "tags": ["backend", "auth"] }
   hivemind/create_epic_doc { "epic_id": "550e8400-e29b-41d4-a716-446655440000", "title": "Auth Setup", "content": "..." }

5. Hivemind generiert Follow-up-Prompt: "Was noch nicht kartiert wurde: ..."
   User führt nächste Session durch

6. Über Zeit: vollständige Systemkarte entsteht iterativ
```

---

## Nexus Grid Integration

Jedes Mal wenn der Kartograph einen Code-Bereich analysiert und einen Wiki-Artikel oder Epic-Doc schreibt, wird der entsprechende `code_node.explored_at` gesetzt:

```
Kartograph analysiert src/auth/jwt.py
  → schreibt Wiki-Artikel "JWT-Implementierung"
  → Hivemind setzt code_nodes WHERE path = 'src/auth/jwt.py': explored_at = now()
  → Nexus Grid zeigt diesen Knoten als kartiert (● statt ░)
```

---

## Infinite Context via Memory Ledger

Der Kartograph ist der Hauptnutzer des Memory Ledgers (→ [Memory Ledger](../features/memory-ledger.md)). Da Codebase-Exploration typischerweise viele Sessions umfasst, persistiert der Kartograph sein Arbeitsgedächtnis strukturiert:

```text
Session 1:  Top-Level erkunden → 15 Beobachtungen → 40 Fakten → 3 Summaries
Session 2:  Resume (Summaries + Fakten laden) → Weiß was kartiert ist → vertieft /workers/
Session 5:  Auth-Summary graduiert zu Wiki → Memory-Footprint sinkt
Session 10: Nur noch 2 aktive Summaries + 80 Fakten ≈ 1000 Tokens für 10 Sessions Wissen
```

**Kompaktierungspflicht:** Am Ende jeder Kartograph-Session **muss** der Agent seine Beobachtungen zu einer L2-Summary verdichten und offene Fragen explizit notieren. Das Follow-up-Prompt enthält automatisch den Memory-Kontext.

→ Vollständiger Memory-Skill: [Agent Skills — Memory Skill](../features/agent-skills.md#memory-skill)

---

## Solo-Modus

Im Solo-Modus ist der Entwickler selbst der Kartograph. Fog-of-War-Mechanik bleibt erhalten — nicht als Zugangskontrolle, sondern als **Arbeitsdisziplin**:

```
Erst kartieren → dann zerlegen → dann ausführen
```

Die Prompt Pipeline (→ [Prompt Pipeline](./prompt-pipeline.md)) unterstützt das strukturiert.

---

## Kartograph-Outputs

| Output-Typ | Beschreibung | MCP-Tool |
| --- | --- | --- |
| Wiki-Artikel | Systemwissen dokumentieren | `create_wiki_article`, `update_wiki_article` |
| Epic-Docs | Epic-spezifische Dokumentation | `create_epic_doc` |
| Code-Nodes | Nexus Grid befüllen (Fog of War lichten) | Automatisch via Backend bei Wiki/Doc-Write |
| Skill-Proposals | Codebase-weite Coding-Patterns als Skills formalisieren | `propose_skill`, `submit_skill_proposal` |
| Skill-Change-Proposals | Bestehende Skills erweitern basierend auf Code-Entdeckungen | `propose_skill_change` |
| Guard-Proposals | Guards aus Repo-Dateien entdecken (`.eslintrc`, `pytest.ini`, `pyproject.toml`, CI-Configs) | `propose_guard`, `submit_guard_proposal` |
| Guard-Change-Proposals | Bestehende Guards aktualisieren (z.B. Coverage-Schwelle ändern) | `propose_guard_change` |
| Epic-Restructure-Proposals | Falsch geschnittene Epics vorschlagen umzustrukturieren | `propose_epic_restructure` |
| Discovery Sessions | Codebase-Bereiche aktiv erkunden und an Peers broadcasten | `hivemind/start_discovery_session`, `hivemind/end_discovery_session` |

> **Guard-Discovery:** Der Kartograph analysiert Repo-Dateien (`.github/workflows/ci.yml`, `Makefile`, `package.json`, `pyproject.toml`, `.pre-commit-config.yaml`) und erstellt daraus Guard-Proposals. Vollständige Quellen-Tabelle: [→ guards.md — Kartograph-Discovery](../features/guards.md#kartograph-discovery)

---

## Abgrenzung

| | Kartograph | Stratege | Architekt | Worker |
| --- | --- | --- | --- | --- |
| Sichtweite | Fog of War, max. Berechtigung | Breit (Hivemind-Daten, kein Code) | Ein Epic (gesetzt) | Context Boundary (fix) |
| Kontextfilter | Deaktiviert | Deaktiviert | Setzt ihn | Strikt begrenzt |
| Output | Wiki, Docs, Skill-Proposals, Restructure-Proposals | Epic-Proposals, Roadmap, Dependencies | Tasks, Subtasks, Boundaries | Task-Ergebnisse |
| Timing | Initial + nach Epic-Abschluss | Vor Architekt; nach Kartograph/Plan | Nach Stratege/Scoping | Während Sprint |

> **Abgrenzung Kartograph vs. Stratege:** Der Kartograph entdeckt *was da ist* (bottom-up: Code → Verständnis). Der Stratege entscheidet *was wir daraus machen* (top-down: Plan → Epics). Der Kartograph schlägt `propose_epic_restructure` vor wenn er beim Erkunden Fehlschnitte entdeckt. Der Stratege schlägt `propose_epic` vor wenn er aus einem Plan neue Arbeitspakete ableitet. Beide Proposals landen in der Triage Station.
