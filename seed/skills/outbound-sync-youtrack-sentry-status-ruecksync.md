---
title: Outbound-Sync (YouTrack/Sentry Status-Rücksync)
service_scope:
- backend
stack:
- python
- fastapi
- sqlalchemy
- httpx
confidence: 0.5
source_epics:
- EPIC-PHASE-7
---

## Skill: Outbound-Sync (YouTrack/Sentry Status-Rücksync)

### Rolle
Du implementierst den outbound Sync-Consumer für die Rücksynchronisierung von Hivemind-Status-Änderungen an externe Systeme (YouTrack, Sentry). Phase 7 ergänzt den in Phase F implementierten peer_outbound-Consumer um einen outbound-Consumer.

### Konventionen
- Consumer verarbeitet `sync_outbox` mit `direction='outbound'`
- APScheduler-Job analog zum peer_outbound Consumer
- `next_retry_at = now() + 2^attempts * 60s` (Exponential Backoff)
- Nach `attempts >= HIVEMIND_DLQ_MAX_ATTEMPTS (5)` → `sync_dead_letter`
- Separate Client-Adapter pro System:
  - `YouTrackSyncAdapter`: Status-Updates + Assignee rücksyncen via YouTrack REST API
  - `SentrySyncAdapter`: Bug-Report-Aggregation in `node_bug_reports`

### Outbound-Consumer (erweitert bestehenden outbox_consumer.py)

```python
EVENT_TYPE_TO_ADAPTER = {
    "youtrack_status_sync": YouTrackSyncAdapter,
    "sentry_bug_aggregate": SentrySyncAdapter,
}

async def process_outbound():
    async with AsyncSessionLocal() as db:
        entries = await db.execute(
            select(SyncOutbox)
            .where(
                SyncOutbox.direction == "outbound",
                SyncOutbox.state == "pending",
                SyncOutbox.attempts < settings.hivemind_dlq_max_attempts,
            )
            .order_by(SyncOutbox.created_at.asc())
            .limit(BATCH_SIZE)
        )
        for entry in entries.scalars():
            adapter_cls = EVENT_TYPE_TO_ADAPTER.get(entry.entity_type)
            if not adapter_cls:
                logger.warning("Unknown outbound type: %s", entry.entity_type)
                entry.attempts += 1
                continue
            try:
                adapter = adapter_cls(settings)
                await adapter.sync(entry)
                await db.delete(entry)
            except Exception as exc:
                entry.attempts += 1
                entry.next_retry_at = datetime.utcnow() + timedelta(
                    seconds=2 ** entry.attempts * 60
                )
                if entry.attempts >= settings.hivemind_dlq_max_attempts:
                    await _move_to_dlq(db, entry, str(exc))
        await db.commit()
```

### YouTrack-Adapter

```python
class YouTrackSyncAdapter:
    def __init__(self, settings):
        self.base_url = settings.youtrack_url
        self.token = settings.youtrack_api_token

    async def sync(self, entry: SyncOutbox):
        issue_id = entry.payload["external_id"]
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.base_url}/api/issues/{issue_id}",
                json={"state": entry.payload["state"]},
                headers={"Authorization": f"Bearer {self.token}"},
            )
```

### Wichtig
- `direction='outbound'` ist für externe Systeme (YouTrack, Sentry)
- `direction='peer_outbound'` ist für Federation (existiert seit Phase F)
- Beide Consumer laufen als separate APScheduler-Jobs
- Exponential Backoff: `2^attempts * 60s` (1min, 2min, 4min, 8min, 16min)
- Env-Variablen: `HIVEMIND_YOUTRACK_URL`, `HIVEMIND_YOUTRACK_API_TOKEN`, `HIVEMIND_SENTRY_API_TOKEN`
