---
title: "Alembic Migration schreiben"
service_scope: ["backend"]
stack: ["python", "alembic", "sqlalchemy", "postgresql"]
version_range: { "python": ">=3.11", "alembic": ">=1.12" }
confidence: 0.5
source_epics: ["EPIC-PHASE-1A"]
guards:
  - title: "Migration Test"
    command: "alembic upgrade head"
  - title: "Migration Downgrade Test"
    command: "alembic downgrade -1 && alembic upgrade head"
---

## Skill: Alembic Migration schreiben

### Rolle
Du erstellst oder modifizierst eine Alembic-Datenbankmigration für das Hivemind-Backend.

### Konventionen
- Auto-Generate bevorzugen: `alembic revision --autogenerate -m "beschreibung"`
- Migration-Messages: lowercase, beschreibend, z.B. `"add users table"`
- Jede Migration muss `upgrade()` UND `downgrade()` implementieren
- Kein Datenverlust in Downgrades (Spalten als nullable markieren statt droppen)
- Enum-Typen als `TEXT` mit `CHECK`-Constraint (kein PostgreSQL ENUM-Typ)
- `UUID`-PKs mit `gen_random_uuid()` (built-in in PG 13+)
- Indexes explizit benennen: `ix_{table}_{column}`

### Beispiel

```python
def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.dialects.postgresql.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="incoming"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("state IN ('incoming','scoped','ready','in_progress','in_review','done','blocked','qa_failed','escalated','cancelled')", name="ck_tasks_state"),
    )

def downgrade() -> None:
    op.drop_table("tasks")
```

### Wichtig
- Vollständiges Schema wird in Phase 1 angelegt — auch Tabellen für spätere Phasen
- pgvector-Extension: `CREATE EXTENSION IF NOT EXISTS vector;` in erster Migration
- Alle `vector(768)` Spalten initial NULL (Embeddings ab Phase 3)
