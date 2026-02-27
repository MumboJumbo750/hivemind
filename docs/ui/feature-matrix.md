# Feature-Matrix — Funktionalität vs. UI-Element

← [UI-Konzept](./concept.md) | [Index](../../masterplan.md)

Vollständige Zuordnung aller System-Funktionen zu konkreten UI-Elementen und Entwicklungsphasen.

---

## Prompt & Workflow

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Aktiven Prompt anzeigen | Prompt Station | Prompt Card + Copy-Button | 1 |
| Agent-Queue verwalten | Prompt Station | Geordnete Warteschlange mit Priorisierung | 1 |
| Queue-Priorisierung begruenden | Prompt Station | "Warum jetzt?"-Badges pro Queue-Eintrag. **Phase 1–2:** nur `NORMAL` und `FOLLOW-UP` (da Escalations/Decisions/SLA erst später existieren). **Ab Phase 6:** vollständige Badge-Palette (`ESCALATED`, `DECISION OFFEN`, `SLA <4h`, etc.) | 1 |
| Menschliche Aktionen ankündigen | Prompt Station | "Jetzt bist DU dran"-State mit Link zur Aktion | 1 |
| Menschliche Aktion kontextualisieren | Prompt Station | Deadline + Grund im `human_action_required`-State | 1 |
| Prompt anpassen (manuell) | Prompt Station | Bearbeitbares Textfeld vor dem Kopieren | 2 |
| Token Radar | Prompt Station | Progress-Ring Animation (630/8000) | 3 |
| Prompt-Verlauf | Prompt Station | Kollabierbare History | 4 |
| Auto-Modus (API-Key) | Prompt Station | Monitoring-Ansicht statt Prompt Card | 8 |

## Command Deck

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Epic-Liste | Command Deck | Epic-Cards mit State-Badge | 2 |
| Task-State-Machine | Command Deck | State-Badge + Transition-Buttons | 2 |
| SLA-Timer | Command Deck + Status Bar | Countdown, Farb-Warnung (amber → rot) | 2 |
| Epic anlegen | Command Deck | "+ Epic anlegen"-Button + Modal | 2 |
| Epic Scoping | Command Deck | Scoping-Modal (Owner, SLA, DoD, Priority) | 2 |
| Task Review (Basis) | Command Deck | Review Panel mit DoD-Checkliste + Approve/Reject | 2 |
| Guard-Status im Review (Basis) | Command Deck | Review Panel zeigt Guard-Status + result-Text (passed/failed/skipped) — ohne Provenance | 5 |
| Guard-Ergebnisse im Review (vollständig) | Command Deck | Review Panel zeigt Guard-Status + Ergebnisdetails + Provenance (`source`, `checked_at`) | 5 |
| Review-Semantik trennen | Command Deck | Bereiche "Hard Gates" (systemisch) und "Owner Judgment" (fachlich) | 2 |
| DoD-Checkliste | Command Deck | Interaktive Checklist im Review Panel | 2 |
| Actor-Identity | System Bar | User-Badge + Rolle | 2 |
| Context Boundary anzeigen | Command Deck | Read-only Panel im Task-Detail (Skills, Docs, Token-Budget) | 4 |
| Guard-Provenance anzeigen | Command Deck | Guard-Zeile mit `source` (self-reported oder system-executed) + `checked_at` — Phase 2–4: Review zeigt nur DoD-Checkliste, kein Guard-Status | 5 |
| Decision Records lesen | Command Deck | Kollabierbare Decision-Records-Liste im Epic-Detail | 5 |
| Decision-Request-Dialog | Command Deck | Modal mit Optionen + SLA-Timer | 6 |
| Eskalations-Ansicht | Command Deck + Triage | Priorisierte Eskalations-Cards | 6 |

## Triage Station

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Unrouted Events | Triage Station | [UNROUTED]-Cards mit Routing-Vorschlägen + route/ignore Buttons | 3 |
| Skill Proposals | Triage Station + Skill Lab | [SKILL PROPOSAL]-Cards mit Diff-Ansicht + Merge/Reject | 4 |
| Guard-Proposals reviewen | Triage Station | [GUARD PROPOSAL]-Cards mit Diff-Ansicht + Merge/Reject | 5 |
| Skill Change Proposals | Triage Station + Skill Lab | [SKILL CHANGE]-Cards mit Diff-Ansicht + Accept/Reject | 5 |
| Guard Change Proposals | Triage Station | [GUARD CHANGE]-Cards mit Diff-Ansicht + Accept/Reject | 5 |
| Epic Restructure Proposals | Triage Station | [RESTRUCTURE]-Cards mit Proposal-Text + Accept/Reject | 5 |
| Dead-Letter-Queue | Triage Station | [DEAD LETTER]-Cards mit Requeue-Option (ruft `hivemind/requeue_dead_letter`) | 7 |
| Eskalations-Queue | Triage Station | [ESCALATED]-Cards nach SLA-Risiko + resolve_escalation Button | 6 |

## Arsenal / Skill Lab

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Skills browsen (Fach-Skills) | Arsenal → Tab "Skills" | Skill-Cards mit Lifecycle-Badge + Confidence Bar | 4 |
| System-Skills browsen | Arsenal → Tab "Skills" | Filter "System" — Agent-Rollen-Skills mit system-Badge | 4 |
| Federated Skills anzeigen | Arsenal → Tab "Skills" | Filter "Federated" — Origin-Badge `[von: peer-name]` + read-only | 4 |
| Skill-Detail anzeigen | Arsenal | Markdown-Reader mit Frontmatter-Metadaten | 4 |
| Skill Composition anzeigen | Arsenal | Extends-Chain-Visualisierung (Pill-Kette: A → B → C) | 4 |
| Skill-Proposal einsehen | Arsenal | Diff-Ansicht (vorher/nachher) | 4 |
| Skill mergen / ablehnen | Arsenal | Admin: Merge / Reject Buttons | 4 |
| Guards browsen | Arsenal → Tab "Guards" | Guard-Cards mit Scope-Badge (global/project/skill/task) + Typ-Badge | 4 |
| Guard-Detail anzeigen | Arsenal → Tab "Guards" | Scope-Kette + Typ (executable/declarative/manual) + Command | 4 |
| Skill-Versions-History | Arsenal | Versions-Timeline (immutable, append-only) | 5 |
| Skill-Change-Proposal | Arsenal | Bearbeitungsformular + Markdown-Preview | 5 |

## Wiki

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Wiki-Artikel lesen | Wiki | Markdown-Reader + Breadcrumb-Navigation | 5 |
| Wiki suchen | Wiki | Suchleiste mit Tag-Filterung | 5 |
| Wiki-Artikel verlinken | Wiki | "Mit Epic verknüpfen"-Dialog | 5 |
| Wiki-Artikel bearbeiten (Kartograph + Admin) | Wiki | Inline-Markdown-Editor + "Speichern"-Button (kartograph + admin) | 5 |
| Wiki-Artikel anlegen (Kartograph + Admin) | Wiki | "+ Artikel anlegen"-Button + Editor-Modal (kartograph + admin) | 5 |

## Nexus Grid / Weltkarte

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Code-Graph 2D | Nexus Grid | Force-directed Graph (**Cytoscape.js**) | 5 |
| Fog of War Overlay | Nexus Grid | Semi-transparente Maske über unerkundeten Nodes | 5 |
| Node Detail | Nexus Grid | Click → Detail-Panel (Docs, Skills, Bugs, Tasks) | 5 |
| Epic-Overlay Toggle | Nexus Grid | Layer-Switcher (welches Epic deckt welche Nodes) | 5 |
| Bug-Heatmap | Nexus Grid | Knoten-Färbung nach Bug-Dichte | 7 |
| Code-Graph 3D | Nexus Grid | WebGL-Modus Toggle (Three.js) | 8 |
| Peer-Farben im Graph | Nexus Grid | Knoten-Färbung nach Origin-Node (Cyan/Magenta/Amber) | F |
| Discovery Session Overlay | Nexus Grid | Pulsierender Badge `[◬ clara erkundet frontend/ ...]` | F |
| Node-Filter nach Peer | Nexus Grid | Layer-Toggle: nur Nodes von bestimmter Node anzeigen | F |

## System & Notifications

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Spotlight-Suche (Ctrl+K) | Global (Overlay) | Schnellsuche über Tasks + Epics (Phase 2), Skills + Guards (Phase 4), Wiki + Code-Nodes (Phase 5). Gruppierte Ergebnisse, RBAC-gefiltert, Fuzzy-Match | 2 |
| Webhook-Konfiguration | Settings → Tab "System" | Webhook-Endpoint-Anzeige + Auth-Token + YouTrack/Sentry-Toggle + Event-Konfiguration + letzter Empfangsstatus | 3 |
| MCP-Verbindungsstatus | System Bar | Status-Badge (● verbunden / ◌ getrennt) | 1 |
| Projekt anlegen/wechseln | System Bar | Project-Switcher Dropdown | 1 |
| Solo/Team-Modus | System Bar + Settings | Mode-Badge + Toggle in Settings | 1 |
| Interface-Tone umschalten | Settings → Tab "System" | 🎮 Game Mode / 💼 Pro Mode Toggle (vue-i18n Laufzeit-Switch) | 1 |
| Tone Interaction-Profil | Global (alle Views) | Dichte/Motion-Profil pro Mode (Game vs Pro) | 1 |
| Theme-Auswahl | Settings → Tab "System" | Theme-Switch (`space-neon`, `industrial-amber`, `operator-mono`) | 1 |
| Token-basierte UI | Global (alle Views) | Komponenten lesen nur Theme-Tokens (keine Hardcoded-Farbwerte) | 1 |
| Focus Mode | Layout-Shell | Prompt-Fokus (ab Phase 2), Map-Fokus (ab Phase 5) | 2 |
| SLA-Alerts | Notification Tray | 🔔 Badge + aufklappbares Panel. **Phase 2:** Notifications werden client-seitig aus Epic/Task-Daten berechnet (SLA-Timer aus `epics.sla_due_at`, `task_assigned` aus Task-State-Changes, `review_requested` aus `in_review`-Transition). Kein Backend-Notification-Service nötig. **Ab Phase 6:** Voller Backend-Notification-Service schreibt alle Typen in `notifications`-Tabelle (inkl. SLA-Cron-basierte `sla_warning`, `sla_breach`, Decision-SLA-Kette). | 2 |
| Projekt-Mitgliederverwaltung | Settings → Tab "Projekt" | Mitglieder-Liste + Rollen pro Projekt + Invite-Button | 2 |
| Decision Request Alerts | Notification Tray | Priorisiert nach SLA | 6 |
| Notification Action Queue | Notification Tray | Gruppen `ACTION NOW`, `SOON`, `FYI` inkl. naechster Aktion | 6 |
| Sync-Status | Status Bar + Settings | Outbox-Indikatoren | 7 |
| Audit-Log | Settings → Tab "Audit" | Tabelle mit MCP-Invocations (Actor, Tool, Timestamp, Status) + Payload-Preview | 4 |
| AI-Provider Config | Settings → Tab "KI" | API-Key-Eingabe + Provider-Auswahl | 8 |

## Gilde / Federation (Phase F)

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Gilde-Übersicht | Gilde | Node-Liste mit Online-Status + aktiver Quest + Beiträgen | F |
| Peer hinzufügen / entfernen | Gilde | `[+ PEER HINZUFÜGEN]` Button + Bestätigungs-Flow | F |
| Peer blockieren | Gilde | `[BLOCKIEREN ✗]` — blockierte Nodes senden/empfangen nichts mehr | F |
| Eigene Node-Identität anzeigen | Gilde + Settings → SYSTEM | Node-Name, Node-URL, Public Key + Copy-Button | F |
| Gildenwissen browsen | Gilde | Federated-Skill-Liste von Peers mit `[ÜBERNEHMEN]`-Button (ruft `hivemind/fork_federated_skill`) | F |
| Skill übernehmen (lokaler Fork) | Gilde / Arsenal | Skill aus Peer-Node als lokaler Draft-Fork mit `extends` importieren | F |
| Gilde-Status in System Bar | System Bar | `[◈ GILDE: 2/3 ▾]` Dropdown mit Live-Peer-Status | F |
| Mercenary Loadout Screen | Prompt Station | BRIEFING-State wenn Task `ready` (Architekt fertig) → intermediärer Schritt vor Worker-Prompt. **Basis-Loadout (Skill-Auswahl + Budget-Prüfung) ab Phase 4; Federated Skills im Loadout ab Phase F.** | 4 |
| Federated Skill im Loadout | Mercenary Loadout | Peer-Skills wählbar mit `[◈ peer-name]` Origin-Badge. **Voraussetzung: Phase 4 (Arsenal/Loadout).** | F |
| Task an Peer delegieren | Command Deck | Task-Detail: `[AN PEER DELEGIEREN ▾]` Dropdown. **Voraussetzung: Phase 2 (Command Deck).** | F |
| Peer-Task-Status sehen | Command Deck | Task-Badge `[◈ ben-hivemind ●]` im Epic-Überblick. **Voraussetzung: Phase 2 (Command Deck).** | F |
| Node-Filter im Command Deck | Command Deck | `[NODE-FILTER: alle ▾]` — Tasks nach Origin-Node filtern. **Voraussetzung: Phase 2 (Command Deck).** | F |
| Discovery Session starten | Nexus Grid | Beim Kartograph-Start → Area markieren + an Peers broadcasten. **Voraussetzung: Phase 5 (Nexus Grid).** | F |
| Discovery Session sehen | Nexus Grid | Pulsierender Badge über erkundetem Bereich. **Voraussetzung: Phase 5 (Nexus Grid).** | F |
| Federation-Notifications | Notification Tray | peer_task_done, peer_online, federated_skill, discovery_session | F |

---

## Zusammenfassung: Wann wird was sichtbar?

```text
Phase 1: Prompt Station + Settings (MCP, Projekt, Solo/Team-Modus, Theme, Interface-Tone)
         System Bar (Node-Name, Project-Switcher, MCP-Status)
         + Prompt Queue mit "Warum jetzt?"-Badges

Phase 2: + Command Deck (Epics, Tasks, Review, Scoping, SLA)
         + Notification Tray
         + Settings -> Projekt-Mitgliederverwaltung
         + Review-Struktur: Hard Gates vs Owner Judgment
         + Focus Mode (Prompt-Fokus)
         + Spotlight-Suche Ctrl+K (Tasks + Epics)

Phase F: + Gilde / Federation (Peer-Uebersicht, Gildenwissen, Node-Identitaet)
           Verfuegbar sofort nach Phase 2:
             Gilde-View, Settings Federation-Tab, System Bar Gilde-Status
           Progressiv verfuegbar (Features werden sichtbar sobald abhaengige Phase implementiert):
             Command Deck Integration (Delegation, Node-Filter) -> ab Phase 2
             Mercenary Loadout mit Federated Skills -> ab Phase 4 (Arsenal)
             Federated Skills im Arsenal -> ab Phase 4
             Nexus Grid: Peer-Farben + Discovery Session Overlay -> ab Phase 5

Phase 3: + Triage Station (Unrouted Events)
         + Prompt Station: Token Radar
         + Settings -> Webhook-Konfiguration (YouTrack + Sentry)
         + Spotlight: erweitert um Triage-relevante Suche

Phase 4: + Arsenal (Browse Skills + Guards, Proposals, Merge)
         + Arsenal: Federated Skills `[von: peer-name]` read-only
         + Settings -> Audit-Log
         + Command Deck: Context Boundary Read-only

Phase 5: + Wiki (lesen, suchen, verlinken, Admin: bearbeiten/anlegen)
         + Nexus Grid 2D (Weltkarte)
         + Arsenal: Versions-History, Change-Proposals, Composition-View
         + Triage: Skill Change, Guard Change, Epic Restructure Proposals
         + Command Deck: Decision Records
         + Review: Guard-Provenance (`source`, `checked_at`)
         + Focus Mode (Map-Fokus)

Phase 6: + Decision Requests + Eskalations-UI
         + Notification Tray als Action Queue (`ACTION NOW`, `SOON`, `FYI`)

Phase 7: + Dead Letter Queue + Bug Heatmap + Sync-Status

Phase 8: + 3D Nexus Grid (Weltkarte in WebGL) + Auto-Modus (API Keys, Settings -> KI)
```
