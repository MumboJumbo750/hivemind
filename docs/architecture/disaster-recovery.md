# Disaster Recovery — Backup, PITR & Wiederherstellung

← [Index](../../masterplan.md)

**Scope:** PostgreSQL-Datenbank, Federation-Keys, Konfiguration
**Zielgruppe:** Node-Admin (Einzelperson im Solo/Team-Betrieb)

---

## Risikomatrix

| Risiko | Eintrittswahrscheinlichkeit | Datenverlust | Recovery-Zeit |
| --- | --- | --- | --- |
| Container-Absturz (DB läuft weiter) | Hoch | Kein | < 1 Min (Restart) |
| Docker-Volume korrupt | Niedrig | Potenziell alles | 30–120 Min (Restore) |
| Versehentliches `DROP TABLE` | Sehr niedrig | Tabellen-Daten | 5–60 Min (PITR) |
| Server-Hardware-Ausfall | Sehr niedrig | Seit letztem Backup | 60–240 Min |
| Federation-Key-Kompromittierung | Sehr niedrig | Kein Datenverlust | 30–60 Min (Key-Rotation) |

---

## Backup-Strategie

### Vollbackup (pg_dump)

**Wann:** Täglich automatisch via Cron-Container im Docker Compose Stack.
**Retention:** 7 tägliche + 4 wöchentliche + 3 monatliche Backups.
**Format:** `pg_dump --format=custom` (komprimiert, restaurierbar mit `pg_restore`).

```yaml
# docker-compose.yml Ergänzung — Backup-Sidecar
services:
  db-backup:
    image: postgres:16-alpine
    depends_on:
      - db
    environment:
      PGPASSWORD: "${POSTGRES_PASSWORD}"
      POSTGRES_DB: "${POSTGRES_DB}"
      POSTGRES_USER: "${POSTGRES_USER}"
      BACKUP_DIR: "/backups"
      HIVEMIND_BACKUP_RETENTION_DAILY: "7"
      HIVEMIND_BACKUP_RETENTION_WEEKLY: "4"
      HIVEMIND_BACKUP_RETENTION_MONTHLY: "3"
    volumes:
      - ./backups:/backups
      - ./scripts/backup.sh:/backup.sh:ro
    command: crond -f -l 2
    restart: unless-stopped
```

```bash
# scripts/backup.sh — täglich 02:00 Uhr
#!/bin/bash
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/hivemind_${TIMESTAMP}.dump"

pg_dump \
  --host=db \
  --port=5432 \
  --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" \
  --format=custom \
  --compress=9 \
  --file="${BACKUP_FILE}"

echo "Backup erstellt: ${BACKUP_FILE} ($(du -h ${BACKUP_FILE} | cut -f1))"

# Rotation: tägliche Backups > 7 Tage löschen
find "${BACKUP_DIR}" -name "hivemind_*.dump" -mtime +7 -delete
```

**CLI-Shortcut:**

```bash
hivemind backup --create            # Manuelles Backup (außerhalb des Cron)
hivemind backup --list              # Alle verfügbaren Backups anzeigen
hivemind backup --verify <file>     # Backup-Integrität prüfen (pg_restore --list)
```

### Point-in-Time Recovery (PITR) — Optional aber empfohlen

PITR erlaubt Wiederherstellung auf jeden Zeitpunkt innerhalb des WAL-Archivs. Besonders wertvoll bei: versehentlichem `DELETE`, fehlerhafter Migration, oder stufenweiser Datenkontamination.

**Voraussetzung:** WAL-Archivierung aktivieren.

```bash
# In docker-compose.yml: PostgreSQL mit WAL-Archivierung
services:
  db:
    image: pgvector/pgvector:pg16
    command: >
      postgres
        -c wal_level=replica
        -c archive_mode=on
        -c archive_command='cp %p /wal-archive/%f'
        -c archive_timeout=300
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./wal-archive:/wal-archive
```

**WAL-Retention:** 7 Tage (Cron-Job löscht ältere WAL-Files aus `/wal-archive`).

> **Ohne PITR:** Wiederherstellung ist nur auf letzte Backup-Zeitpunkte möglich (täglich). Datenverlust von bis zu 23h58m ist möglich. **Empfehlung:** PITR für Produktionssysteme zwingend aktivieren; für lokale Entwicklungs-Nodes optional.

---

## Wiederherstellungs-Prozeduren

### Szenario 1: Container-Absturz (kein Datenverlust)

```bash
# Backend-Container neustart:
docker compose restart backend

# Datenbank-Container neustart (wenn DB selbst abgestürzt):
docker compose restart db
# Warte auf "database system is ready to accept connections" im Log
docker compose logs db --follow
```

PostgreSQL schreibt bei Crash automatisch ein WAL-Recovery durch — kein manuelles Eingreifen.

### Szenario 2: Restore aus Vollbackup

**Wann:** Docker-Volume korrupt, Server-Neuaufsetzen, Migration auf neuen Host.

```bash
# 1. Backup-Datei auswählen
hivemind backup --list
# → hivemind_20260226_020000.dump  (gestern, 02:00 Uhr)
# → hivemind_20260225_020000.dump  (vorgestern)

# 2. Stack stoppen
docker compose down

# 3. Altes Volume löschen (ACHTUNG: irreversibel!)
docker volume rm hivemind_postgres_data

# 4. Neues leeres Volume + DB starten
docker compose up db -d
# Warte bis DB bereit ist (max 30s)

# 5. Backup einspielen
docker compose exec db pg_restore \
  --host=localhost \
  --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" \
  --no-owner \
  --no-privileges \
  /backups/hivemind_20260226_020000.dump

# 6. Migrationen prüfen (falls Backup älter als aktuelle Codebase)
docker compose run --rm backend alembic current
docker compose run --rm backend alembic upgrade head

# 7. Vollständigen Stack starten
docker compose up -d
```

**Datenverlust-Fenster:** Alle Changes seit Backup-Erstellungszeit (bis zu 23h58m bei täglichem Backup ohne PITR).

### Szenario 3: PITR — Wiederherstellung auf Zeitpunkt T

**Wann:** Versehentliches `DELETE FROM tasks WHERE ...`, fehlerhafte Alembic-Migration.

```bash
# 1. Ziel-Zeitpunkt bestimmen (z.B. 5 Minuten vor der fehlerhaften Migration)
TARGET_TIME="2026-02-27 14:25:00"

# 2. Stack stoppen
docker compose down

# 3. Letztes Vollbackup einspielen (vor dem Ziel-Zeitpunkt)
# (wie Szenario 2, Schritte 3–5)

# 4. recovery.conf erstellen (PostgreSQL 16: recovery_target_time in postgresql.conf)
docker compose exec db psql -U "${POSTGRES_USER}" -c \
  "SELECT pg_create_restore_point('pre_recovery');"

# Manuell in postgresql.conf im Volume ergänzen:
# recovery_target_time = '2026-02-27 14:25:00 UTC'
# recovery_target_action = 'promote'

# 5. WAL-Dateien aus Archive nach /var/lib/postgresql/data/pg_wal kopieren
# (automatisch via archive_command)

# 6. DB im Recovery-Mode starten
docker compose up db -d
# PostgreSQL replayed WAL bis zum Ziel-Zeitpunkt und promoted

# 7. Nach Recovery: recovery_target_time aus postgresql.conf entfernen
# 8. Voller Stack-Start + Alembic-Check
docker compose up -d
docker compose run --rm backend alembic current
```

> **CLI-Shortcut (Phase 7+):**
> ```bash
> hivemind restore --to-time "2026-02-27 14:25:00" --backup-file hivemind_20260227_020000.dump
> ```
> Das CLI automatisiert Schritte 2–8. Bei fehlendem PITR: Fehlermeldung "WAL-Archivierung nicht konfiguriert — nur vollständiger Backup-Restore möglich."

### Szenario 4: Federation-Key-Verlust

Der Private Key ist bei `HIVEMIND_KEY_PASSPHRASE` verschlüsselt gespeichert. Bei Verlust:

```bash
# 1. Key-Backup prüfen
hivemind federation export-key --encrypted --output key-backup.enc
# (sollte vor jedem Deployment erstellt werden)

# 2. Key aus Backup wiederherstellen
hivemind federation import-key --encrypted key-backup.enc

# 3. Wenn kein Backup: Neues Keypair generieren + alle Peers informieren
hivemind federation rotate-key --no-grace
# → Alle Peers müssen manuell den neuen Public Key akzeptieren
# → Outbox-Einträge mit altem Key: hivemind federation resign-dlq
```

---

## Backup-Validierung

Ein Backup das nie getestet wurde ist kein Backup. Empfehlung: Monatlicher Restore-Test.

```bash
# Backup-Integrität prüfen (schnell, kein Restore)
hivemind backup --verify backups/hivemind_20260226_020000.dump
# → Prüft pg_restore --list (vollständige Objekt-Liste ohne Datenzugriff)
# → Gibt checksum + object_count zurück

# Vollständiger Probe-Restore in temporären Container
docker run --rm \
  -e PGPASSWORD="${POSTGRES_PASSWORD}" \
  -v ./backups:/backups \
  postgres:16-alpine \
  pg_restore \
    --host=db-test \
    --username="${POSTGRES_USER}" \
    --dbname="hivemind_test" \
    --no-owner \
    --list \
    /backups/hivemind_20260226_020000.dump
```

---

## Recovery Time & Point Objectives

| Szenario | RTO (Recovery Time) | RPO (Datenverlust max) |
| --- | --- | --- |
| Container-Absturz | < 1 Min | 0 |
| Volume-Corrupt (Vollbackup) | 30–120 Min | < 24h |
| Volume-Corrupt (Vollbackup + PITR) | 30–120 Min | < 5 Min (WAL-Archiv) |
| Server-Totalausfall (neuer Host) | 2–4h | < 24h (oder < 5 Min mit PITR) |
| Key-Verlust mit Backup | 30 Min | 0 (Datenverlust ausgeschlossen) |
| Key-Verlust ohne Backup | 60 Min + Peer-Koordination | 0 |

---

## Notfall-Kontakt für Federation

Bei einem Datenverlust-Szenario auf einer Federation-Node: Peer-Nodes können als partielle Wiederherstellungsquelle dienen — für alle Entitäten die auf dieser Node als Origin angelegt wurden (`origin_node_id = <eigene-node-id>`).

```bash
# Full-Sync von allen Peers anfordern (holt alle push-sync'd Entitäten zurück)
hivemind federation sync --full --from-peers

# ACHTUNG: Stellt nur Entitäten wieder her die vorher federated waren (federation_scope='federated')
# Lokale Entitäten (tasks, epics) sind NICHT auf Peers — nur Vollbackup kann diese retten
```

> **Federation ist KEIN Backup-System.** Peers speichern nur federated Skills, Wiki und Code-Nodes — keine Epics, keine Tasks, keine Audit-Logs. Vollbackups sind zwingend.

---

## Backup-Checkliste (Deployment-Vorbereitung)

Vor dem ersten Produktionseinsatz prüfen:

- [ ] `db-backup`-Container in `docker-compose.yml` konfiguriert
- [ ] `/backups`-Volume auf externem Laufwerk oder NAS gemountet (nicht dasselbe wie DB-Volume!)
- [ ] WAL-Archivierung aktiviert (PITR-Empfehlung)
- [ ] Erstes Backup manuell via `hivemind backup --create` erstellt und mit `--verify` geprüft
- [ ] `HIVEMIND_KEY_PASSPHRASE` sicher gespeichert (Passwort-Manager)
- [ ] Federation-Key-Export: `hivemind federation export-key --encrypted` — verschlüsselt extern gespeichert
- [ ] Probe-Restore in Staging-Umgebung durchgeführt
