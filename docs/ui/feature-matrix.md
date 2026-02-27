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
| Guard-Status im Review (Basis) | Command Deck | Review Panel zeigt Guard-Status + result-Text (passed/failed/skipped) — informativ, kein Blocker, ohne Provenance (→ [guards.md](../features/guards.md#kanonische-guard-enforcement-timeline)) | 2 |
| Guard-Ergebnisse im Review (vollständig) | Command Deck | Review Panel zeigt Guard-Status + Ergebnisdetails + Provenance (`source`, `checked_at`) | 5 |
| Review-Semantik trennen | Command Deck | Bereiche "Hard Gates" (systemisch) und "Owner Judgment" (fachlich) | 2 |
| DoD-Checkliste | Command Deck | Interaktive Checklist im Review Panel | 2 |
| Actor-Identity | System Bar | User-Badge + Rolle | 2 |
| Context Boundary anzeigen | Command Deck | Read-only Panel im Task-Detail (Skills, Docs, Token-Budget) | 4 |
| Guard-Provenance anzeigen | Command Deck | Guard-Zeile mit `source` (self-reported oder system-executed) + `checked_at` — Phase 2–4: Guard-Status sichtbar als informative Checkliste (ohne Provenance), Phase 5+: Provenance-Details (`source`, `checked_at`) | 5 |
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
| Dead-Letter-Queue | Triage Station | [DEAD LETTER]-Cards mit Requeue-Option (ruft `POST /api/triage/dead-letters/:id/requeue`) | 7 |
| Eskalations-Queue | Triage Station | [ESCALATED]-Cards nach SLA-Risiko + resolve_escalation Button | 6 |
| Bug→Epic manuell zuweisen | Triage Station → Tab "Unrouted" | [BUG ZUWEISEN]-Button auf Bug-Cards (Sentry-Events); öffnet Epic-Auswahl-Dropdown → ruft `hivemind/assign_bug` via REST-Alias `POST /api/triage/bugs/:id/assign` | 7 |

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
| Spotlight-Suche (Ctrl+K) | Global (Overlay) | Schnellsuche über Tasks + Epics (Phase 2), Skills + Guards (Phase 4), Wiki + Code-Nodes (Phase 5). Gruppierte Ergebnisse, RBAC-gefiltert. Client-seitiger Fuzzy-Match via **Fuse.js** (entschieden — kein WASM, einfache Vue-Integration, trifft auf gecachte API-Ergebnisse). Serverseitige Suche via `GET /api/search?q=` (ILIKE Phase 2–3, pgvector-Hybrid ab Phase 3). | 2 |
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
| AI-Provider Config | Settings → Tab "KI" | Per-Agent-Rolle: Provider + Modell + API-Key + Token-Budget; Global-Fallback; Hybrid BYOAI+Auto | 8 |
| Governance Config | Settings → Tab "Governance" | Pro Entscheidungstyp: manual/assisted/auto; Confidence-Threshold + Grace-Period bei auto; Autonomie-Spektrum-Visualisierung; Safeguard-Anzeige | 8 |
| AI-Review-Empfehlung | Command Deck → Review Panel | Reviewer-Agent Confidence-Badge + Checklist + 1-Click Bestätigung (assisted) / Grace-Period-Countdown (auto) | 8 |

## Profil & Personalisierung

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Profil-Zugang | System Bar → UserDropdown | Klick auf UserAvatar → Dropdown: [PROFIL] [EINSTELLUNGEN] [ABMELDEN] | 2 |
| Profil anzeigen | Profil | Username, Display-Name, E-Mail, Bio, Rolle, Projekt-Zugehörigkeiten | 2 |
| Display-Name ändern | Profil | Inline-Edit-Feld für `display_name` (wird statt `username` im UI angezeigt wenn gesetzt) | 2 |
| Bio bearbeiten | Profil | Freitext-Feld (max 280 Zeichen) | 2 |
| Avatar hochladen | Profil → AvatarUploadModal | Upload (max 2 MB, WebP/PNG/JPG) + Vorschau + serverseitige Konvertierung zu WebP 256x256 | 2 |
| Initialen-Avatar | Profil | Auto-generierter Avatar aus Display-Name/Username (deterministisches Farb-Hashing) als Fallback | 2 |
| Avatar-Rahmen auswählen | Profil → AvatarUploadModal | Freigeschaltete Rahmen (silver/gold/holo) aus Gamification wählbar; gesperrte mit Lock-Icon | 2 (Rahmen-Freischaltung ab Phase 5) |
| Per-User Theme | Profil → PreferencesPanel | Theme-Switch (space-neon/industrial-amber/operator-mono) — überschreibt globalen Default für diesen User | 2 |
| Per-User Tone | Profil → PreferencesPanel | 🎮 Game Mode / 💼 Pro Mode Toggle — überschreibt globalen Default für diesen User | 2 |
| Notification-Präferenzen | Profil → PreferencesPanel | Checkbox-Gruppen: SLA-Warnungen, Review-Anfragen, Skill-Proposals, Eskalationen, Peer-Events, EXP-Notifications | 2 |
| Peer-Profil (read-only) | Gilde → PeerProfilePanel | Avatar, Level, Badges, Gilde-Beiträge, aktive Quest | F |

## Gamification & Progression

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| EXP-Anzeige (kompakt) | Status Bar | ExpBar (compact): `[EXP: ████████░░░ Lvl. 5 Commander]` | 2 |
| EXP-Anzeige (detailliert) | Profil | ExpBar: exp_total, Level, EXP bis nächstes Level, letzter Delta | 2 |
| EXP-Award-Feedback | Prompt Station | `+50 EXP (Clean Run: +20) (SLA: +10)` nach Task-Done | 5 |
| Level-Up-Animation | Global (Layout-Overlay) | LevelUpToast: Glow + Partikel-Effekt, neuer Rang-Titel, Unlock-Info | 5 |
| Trophäenschrank | Profil → TrophyCabinet | Badge-Grid mit Kategorien (Quest, Wissen, Exploration, Federation, Governance); gesperrte Badges als ░░ mit Unlock-Bedingung | 5 |
| Badge-Anzeige (kompakt) | Gilde | Inline-Badge-Reihe pro Peer (🥇 🥈 🥉) | F |
| Leaderboard | Gilde → Tab "Rangliste" | Sortierte Peer-Liste nach EXP + Level + Badges; Zeitraum-Filter (Woche/Monat/Gesamt) | F |
| Persönliche Statistiken | Profil → StatsPanel | Quests erledigt, Clean Runs, Reviews, Skills erstellt, Wiki-Artikel, Code-Nodes, Avg. Zeiten | 5 |

## Memory Ledger (Agenten-Gedächtnis)

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Memory-Kontext im Context Panel | Command Deck → Context Panel | MemoryContextBadge: Summary-Count, Fakten-Count, offene Fragen, letzter Agent | 5 |
| Memory Ledger Browser | Memory Ledger (eigene View) | Scope-Filter, Agent-Filter, Ebenen-Filter (L0/L1/L2), Suchfeld | 5 |
| Offene Fragen anzeigen | Memory Ledger | OpenQuestionsPanel: priorisierte Liste aus L2-Summaries mit Quell-Agent und Session | 5 |
| L2-Summaries browsen | Memory Ledger | SummaryCard: Zusammenfassung, Fakten-Count, Coverage, Graduation-Status, Quell-Entries | 5 |
| L1-Fakten browsen | Memory Ledger | FactTable: Entity/Key/Value kompakt, filterbar nach Entity oder Agent | 5 |
| Skill-Candidates anzeigen | Memory Ledger | SkillCandidateCard: Tag `skill-candidate`, Verarbeitungsstatus, Link zu resultierendem Skill | 5 |
| Abdeckungs-Status | Memory Ledger | CoverageStatus: % Observations durch Summaries abgedeckt, Trend-Anzeige | 5 |
| Memory-Integrity-Warnung | Prompt Station | Warnbanner wenn >30% Observations unbedeckt; [KOMPAKTIERUNG ANFORDERN] Button | 5 |
| Memory via Spotlight suchen | Global (Ctrl+K) | Spotlight erweitert um Memory-Entries und Fakten (Scope: Memory) | 5 |

## Conductor Monitoring (Phase 8)

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Conductor-Status | Settings → Tab "KI" → ConductorStatus | Aktiv/Pausiert-Badge + [PAUSIEREN/FORTSETZEN] Button | 8 |
| Aktive Dispatches | Settings → ConductorStatus | Live-Liste laufender Agent-Dispatches (Agent, Task/Epic, Provider, Laufzeit) | 8 |
| Provider-Auslastung | Settings → ConductorStatus | RPM-Balken pro Provider + Endpoint-Health-Status (✓ / ⚠ / ✗) | 8 |
| Dispatch-History | Settings → ConductorStatus | Letzte Dispatches mit Status (completed/failed/vetoed), Latenz, Provider | 8 |
| Dispatch-Fehler-Detail | Settings → ConductorStatus | Klappbares Error-Detail bei failed-Dispatches (Error-Message, Retry-Status) | 8 |

## Gilde / Federation (Phase F)

| Funktion | View | UI-Element | Phase |
| --- | --- | --- | --- |
| Gilde-Übersicht | Gilde | Node-Liste mit Online-Status + aktiver Quest + Beiträgen | F |
| Peer hinzufügen / entfernen | Gilde | `[+ PEER HINZUFÜGEN]` Button + Bestätigungs-Flow | F |
| Peer blockieren | Gilde | `[BLOCKIEREN ✗]` — blockierte Nodes senden/empfangen nichts mehr | F |
| Eigene Node-Identität anzeigen | Gilde + Settings → SYSTEM | Node-Name, Node-URL, Public Key + Copy-Button | F |
| Gildenwissen browsen | Gilde | Federated-Skill-Liste von Peers mit `[ÜBERNEHMEN]`-Button (ruft `POST /api/skills/:id/fork` — REST-Endpoint, kein direkter MCP-Aufruf aus UI) | F |
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
         System Bar (Node-Name, Project-Switcher, MCP-Status, UserAvatar)
         + Prompt Queue mit "Warum jetzt?"-Badges

Phase 2: + Command Deck (Epics, Tasks, Review, Scoping, SLA)
         + Profil (Avatar, Display-Name, Bio, Theme/Tone per-User, Notification-Präferenzen)
         + Avatar-Upload + Initialen-Avatar-Fallback
         + System Bar: UserAvatar klickbar → Profil-Dropdown
         + Status Bar: ExpBar (compact) + Level-Anzeige
         + Notification Tray
         + Settings -> Projekt-Mitgliederverwaltung
         + Review-Struktur: Hard Gates vs Owner Judgment
         + Focus Mode (Prompt-Fkus)
         + Spotlight-Suche Ctrl+K (Tasks + Epics)

Phase F: + Gilde / Federation (Peer-Uebersicht, Gildenwissen, Node-Identitaet)
         + Leaderboard (Rangliste in Gilde-View)
         + Peer-Profile (read-only)
         + Badge-Anzeige pro Peer (kompakt)
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
         + Memory Ledger Browser (Agenten-Gedächtnis durchsuchbar)
         + Memory-Kontext im Context Panel
         + Trophäenschrank / Badge-Grid im Profil
         + EXP-Award-Feedback in Prompt Station
         + Level-Up-Animation (globaler Overlay)
         + Persönliche Statistiken im Profil
         + Arsenal: Versions-History, Change-Proposals, Composition-View
         + Triage: Skill Change, Guard Change, Epic Restructure Proposals
         + Command Deck: Decision Records
         + Review: Guard-Provenance (`source`, `checked_at`)
         + Focus Mode (Map-Fokus)
         + Spotlight erweitert um Memory-Entries

Phase 6: + Decision Requests + Eskalations-UI
         + Notification Tray als Action Queue (`ACTION NOW`, `SOON`, `FYI`)

Phase 7: + Dead Letter Queue + Bug Heatmap + Sync-Status

Phase 8: + 3D Nexus Grid (Weltkarte in WebGL) + Auto-Modus (API Keys, Settings -> KI)
         + Settings -> Governance (Autonomie-Spektrum, pro-Typ manual/assisted/auto)
         + AI-Review-Panel (Reviewer-Empfehlung, Grace Period, 1-Click)
         + Conductor Dashboard (aktive Dispatches, Provider-Auslastung, Fehlerlog)
```

---

## Frontend State Management — Pinia Store-Strategie

**State-Management-Library: Pinia** (Vue 3 Standard, Composition API kompatibel, DevTools-Support).

| Store | Inhalt | Scope |
| --- | --- | --- |
| `useAuthStore` | Access-Token (in-memory), User-Profil (id, role, display_name, avatar_url, avatar_frame, preferred_theme, preferred_tone, memberships) | Global, persistent über Navigation |
| `useProjectStore` | Aktives Projekt, Projekt-Liste | Global |
| `usePromptStationStore` | Aktueller State (idle/agent_required/...), aktive Queue, Polling-Interval | Global |
| `useNotificationStore` | Ungelesene Notifications, Badge-Count | Global |
| `useSettingsStore` | App-Settings (notification_mode, default_theme, default_tone, hivemind_mode, current_phase) | Global, gecacht |
| `useProfileStore` | User-Profil-Daten, EXP, Level, Badges, Statistiken, Präferenzen | Global, lazy-loaded |
| `useGamificationStore` | Level-Thresholds, Badge-Definitionen, aktuelle EXP-Deltas (für Toast-Anzeige) | Global, SSE-subscribed (`level_up`, `badge_awarded`) |
| `useMemoryLedgerStore` | Memory-Entries, Summaries, Facts, Filter-State, Coverage-Daten | View-scoped (reset bei Nav-Wechsel) |
| `useCommandDeckStore` | Gefilterte Epics/Tasks, aktiver Filter-State | View-scoped (reset bei Nav-Wechsel) |
| `useTriageStore` | Triage-Items, aktiver Tab (unrouted/proposals/escalated/dead-letter) | View-scoped |

**Composables für Server-State:** API-Calls werden nicht direkt in Stores verwaltet, sondern via **VueUse `useFetch`** oder leichte Composables (`useEpics`, `useTaskDetail`). Stores halten nur Client-State (Filter, UI-Mode, gecachte Token-Daten). Serverseitiger State wird bei Bedarf refetched — kein globaler Cache-Layer.

**SSE-Integration:** `usePromptStationStore` und `useNotificationStore` abonnieren SSE-Kanäle (`/events/tasks`, `/events/notifications`) via shared Composable `useSSEChannel`. Reconnect-Logik: exponentieller Backoff (1s → 2s → 4s → max 30s).
