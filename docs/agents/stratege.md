# Stratege — Strategische Planung & Epic-Ableitung

← [Agenten-Übersicht](./overview.md) | [Index](../../masterplan.md)

Der Stratege analysiert Plandokumente (Masterpläne, PRDs, RFCs, Roadmaps) und leitet daraus eine strukturierte Epic-Landschaft mit Abhängigkeiten und Phasen-Zuordnung ab. Er ist die Brücke zwischen dem großen Bild (Plan) und der taktischen Zerlegung (Architekt).

> Analogie: Ein Feldherr der die Strategiekarte studiert und die Feldzüge plant — bevor die Offiziere (Architekten) ihre Einsatzbefehle ableiten.

---

## Kernaufgaben

1. **Plan→Epics** — Analysiert Plandokumente und leitet Epics mit Beschreibung und Rationale ab
2. **Dependency-Mapping** — Definiert Abhängigkeiten und Reihenfolge zwischen Epics
3. **Epic-Scoping-Empfehlung** — Schlägt Priorität, SLA-Rahmen und DoD-Rahmen pro Epic vor
4. **Phasen-Zuordnung** — Ordnet Epics logischen Phasen oder Meilensteinen zu
5. **Resource-Empfehlung** — Empfiehlt Epic-Owner und Team-Zusammensetzung (ab Team-Modus)

---

## RBAC

Der Stratege arbeitet als `developer` (eigene Projekte) oder `admin` (alle Projekte):

| Permission | Beschreibung |
| --- | --- |
| `read_any_epic` | Alle Epics sehen (für Dependency-Mapping und Duplikatvermeidung) |
| `read_any_wiki` | Alle Wiki-Artikel sehen (für Plan-Dokumente und Systemverständnis) |
| `read_any_doc` | Alle Docs sehen (für Kontext) |
| `read_any_skill` | Alle aktiven Skills sehen (für Resource-Empfehlung) |
| `propose_epic` | Epic-Proposals erstellen |
| `write_wiki` | Wiki-Artikel erstellen/aktualisieren (Roadmap, Strategy-Docs) |

> Der Stratege ist keine eigene Rolle im Actor-Modell — er nutzt die `developer`- oder `admin`-Rolle. "Stratege" beschreibt die **Funktion** im Workflow, nicht die RBAC-Rolle.

---

## Typischer Workflow

```
1. Plan-Dokument existiert im Wiki (tags: ["plan","roadmap","architecture"])
   ODER: Kartograph hat Repo kartiert (Wiki + Docs vorhanden)
   → Prompt Station zeigt: "Jetzt: Stratege"

2. User fügt Strategie-Prompt in AI-Client ein
   → AI liest Plan-Dokument(e): hivemind/search_wiki { "query": "...", "tags": ["plan"] }
   → AI liest bestehende Epics: hivemind/list_epics { "project_id": "uuid" }
   → AI liest Team-Roster: hivemind/get_project_members { "project_id": "uuid" }

3. AI leitet Epics ab:
   hivemind/propose_epic {
     "project_id": "uuid",
     "title": "Phase 1 — Datenfundament",
     "description": "Schema, State Machine, Docker Setup...",
     "rationale": "Abgeleitet aus Masterplan Sektion 'Phasen': Grundlage für alle weiteren Features",
     "suggested_priority": "critical",
     "suggested_phase": 1,
     "depends_on": [],
     "suggested_owner_id": "uuid"
   }

   hivemind/propose_epic {
     "project_id": "uuid",
     "title": "Phase 2 — Identity & RBAC",
     "description": "Auth, Rollen, Command Deck...",
     "rationale": "Abgeleitet aus Masterplan: RBAC ist Voraussetzung für Team-Modus",
     "suggested_priority": "high",
     "suggested_phase": 2,
     "depends_on": ["<proposal-uuid-phase-1>"],
     "suggested_owner_id": "uuid"
   }

4. Proposals landen in Triage Station als [EPIC PROPOSAL]
   → Admin/Owner reviewed: Akzeptieren → Epic (incoming)
   → Kann direkt scopen → Epic (scoped)
   → Ablehnen mit Begründung → Notification an Strategen

5. Stratege dokumentiert Roadmap-Entscheidungen:
   hivemind/create_wiki_article {
     "title": "Roadmap — Epic-Abhängigkeiten",
     "slug": "roadmap-dependencies",
     "content": "...",
     "tags": ["roadmap", "strategy"]
   }

6. Nach Akzeptanz:
   → Kartograph schreibt initiale Epic-Docs (bestehender Flow)
   → Architekt zerlegt gescopte Epics in Tasks (bestehender Flow)
```

---

## MCP-Tools

```text
-- Read-Tools (geteilt mit anderen Agenten)
hivemind/search_wiki          { "query": "...", "tags": [...] }
hivemind/list_epics           { "project_id": "uuid" }
hivemind/get_epic             { "id": "uuid" }
hivemind/get_project_members  { "project_id": "uuid" }
hivemind/list_skills          { "service_scope": [...] }

-- Write-Tools (Stratege-spezifisch)
hivemind/propose_epic         { "project_id": "uuid", "title": "...", "description": "...",
                                "rationale": "...", "suggested_priority": "critical|high|medium|low",
                                "suggested_phase": 1, "depends_on": ["uuid"],
                                "suggested_owner_id": "uuid" }
                                -- Erstellt Epic-Proposal (state: proposed)
                                -- Landet als [EPIC PROPOSAL] in Triage Station
                                -- Optional: depends_on verweist auf andere Proposal-UUIDs oder Epic-UUIDs

hivemind/update_epic_proposal { "proposal_id": "uuid", "title": "...", "description": "..." }
                                -- Proposal nachbessern (nur solange state = proposed)

-- Write-Tools (geteilt — Wiki für Roadmap-Dokumentation)
hivemind/create_wiki_article  { "title": "...", "slug": "...", "content": "...", "tags": [...] }
hivemind/update_wiki_article  { "id": "uuid", "content": "..." }
```

---

## Strategie-Dokument Design

Der Stratege arbeitet mit **Plan-Dokumenten** — Wiki-Artikeln die mit spezifischen Tags markiert sind:

| Tag | Bedeutung | Beispiel |
| --- | --- | --- |
| `plan` | Übergeordneter Projektplan | Masterplan, PRD |
| `roadmap` | Phasen-/Meilensteinplanung | Epic-Abhängigkeitsmatrix |
| `strategy` | Strategische Entscheidung | Technologiewahl, Build-vs-Buy |
| `rfc` | Request for Comments | Architekturvorschlag |

Der Stratege kann auch selbst Wiki-Artikel mit diesen Tags erstellen (z.B. die abgeleitete Roadmap).

---

## Abhängigkeiten zwischen Epic-Proposals

Epic-Proposals können über `depends_on` aufeinander verweisen:

```text
[Proposal: Phase 1 — Datenfundament]
  depends_on: []

[Proposal: Phase 2 — Identity & RBAC]
  depends_on: [<Phase-1-Proposal-UUID>]

[Proposal: Phase 3 — MCP Read-Tools]
  depends_on: [<Phase-2-Proposal-UUID>]
```

Wenn ein Proposal akzeptiert wird, werden die `depends_on`-Referenzen auf die echten Epic-UUIDs aufgelöst. Wenn ein abhängiges Proposal abgelehnt wird, erhält der Stratege eine Notification: "Proposal X abgelehnt — abhängige Proposals Y, Z prüfen."

---

## Sichtweite & Abgrenzung

| | Stratege | Kartograph | Architekt |
| --- | --- | --- | --- |
| **Input** | Plan-Docs, Wiki, bestehende Epics | Code-Repo + Hivemind-Daten | Ein gescoptes Epic |
| **Output** | Epic-Proposals, Roadmap, Dependencies | Wiki, Epic-Docs, Restructure-Proposals | Tasks, Boundaries, Zuweisung |
| **Sichtweite** | Breit (alle Hivemind-Daten, kein Code) | Alles (inkl. Code-Repo) | Ein Epic (gesetzt) |
| **Kognitiver Modus** | Strategisch Planen (top-down) | Entdecken (bottom-up) | Taktisch Planen (middle-out) |
| **Timing** | Vor Architekt; nach Plan-Import oder Kartograph-Bootstrap | Initial + nach Epic-Abschluss | Nach Epic-Scoping |
| **Metapher** | Feldherr mit Strategiekarte | Soldat mit Geländezugang | Offizier mit Einsatzbefehl |
| **Repo-Zugriff** | Nein (arbeitet auf Hivemind-Daten) | Ja (Filesystem + Git) | Nein (arbeitet auf Epic-Daten) |

---

## Infinite Context via Memory Ledger

Bei komplexen Plandokumenten oder großen Epic-Landschaften nutzt der Stratege das Memory Ledger (→ [Memory Ledger](../features/memory-ledger.md)) um Analysen über Sessions hinweg zu persistieren:

```text
Session 1:  Masterplan-Abschnitte 1-3 analysiert → Dependencies erkannt → Summary + Fakten
Session 2:  Resume → Weiß was analysiert ist → Abschnitte 4-6 → Widerspruch entdeckt
Session 3:  Resume → Offene Frage klären → Epic-Landschaft graduiert als Wiki-Artikel
```

→ Vollständiger Memory-Skill: [Agent Skills — Memory Skill](../features/agent-skills.md#memory-skill)

---

## Solo-Modus

Im Solo-Modus ist der Entwickler selbst der Stratege. Der Strategie-Prompt hilft trotzdem strukturiert zu planen — er verhindert "direkt loscoden" und erzwingt eine bewusste Epic-Landschaft bevor der Architekt übernimmt.

---

## Zusammenspiel mit dem Kartographen

Stratege und Kartograph ergänzen sich, aber haben **unterschiedliche Auslöser**:

| Auslöser | Agent | Aktion |
| --- | --- | --- |
| Neues Projekt + Plan-Dokument liegt vor | **Stratege** | Plan→Epics ableiten (top-down) |
| Neues Projekt + Code-Repo liegt vor | **Kartograph** | Repo kartieren, Wiki + Docs erstellen |
| Kartograph entdeckt: "Epic schlecht geschnitten" | **Kartograph** | `propose_epic_restructure` (discovery-basiert) |
| Stratege erkennt: "Neue Phase braucht zusätzliches Epic" | **Stratege** | `propose_epic` (strategy-basiert) |
| Projekt hat sowohl Plan als auch Code | **Erst Kartograph**, dann **Stratege** | Kartograph kartiert Ist-Stand → Stratege plant Soll-Zustand |

---

## Phase-Einordnung

- **Phase 1–3:** Stratege-Prompt wird manuell generiert und im AI-Client ausgeführt. `propose_epic` existiert noch nicht als MCP-Tool — Epics werden manuell angelegt. Der Strategie-Prompt dient als **strukturierte Planungshilfe**.
- **Phase 4:** `propose_epic` wird als MCP-Write-Tool implementiert (zusammen mit Architekt Planer-Writes). Triage Station erhält `[EPIC PROPOSAL]`-Kategorie. Stratege wird vollständig MCP-gestützt.
- **Phase 8:** Stratege kann autonom Prompts konsumieren und Epic-Proposals erstellen.
