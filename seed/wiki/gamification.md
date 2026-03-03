---
slug: gamification
title: "Gamification — EXP, Badges & Levels"
tags: [gamification, badges, levels, exp, phase-5]
linked_epics: [EPIC-PHASE-5]
---

# Gamification — EXP, Badges & Levels

Hivemind übersetzt echte Entwicklertätigkeiten in Spielmechaniken. Kein Gimmick — die Gamification macht Fortschritt messbar und motiviert konsistente Arbeit.

## EXP-System

Jede abgeschlossene Aktion gibt Erfahrungspunkte:
- Task abschließen → EXP basierend auf Task-Komplexität
- Review bestehen → EXP-Bonus
- Skill erstellen → EXP
- Wiki-Artikel schreiben → EXP

## Levels

EXP-Schwellwerte definieren Levels. Höhere Levels schalten keine Features frei (kein Pay-to-Win) — sie sind rein informativ und zeigen Engagement.

## Badges

Errungenschaften für besondere Leistungen:
- Erste Tasks abgeschlossen
- Bestimmte Anzahl Reviews bestanden
- Skills erstellt und gemerged
- Epics vollständig abgeschlossen

## Achievements-Endpoint

`GET /api/achievements` liefert alle freigeschalteten Badges und den aktuellen Level-Fortschritt. Die Status Bar zeigt EXP-Progress live.
