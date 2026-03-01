"""Quick utility to check and fix epic_proposals schema."""
import psycopg2

conn = psycopg2.connect("postgresql://hivemind:hivemind@postgres:5432/hivemind")
cur = conn.cursor()

# Check current columns
cur.execute(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name='epic_proposals' ORDER BY ordinal_position"
)
cols = [r[0] for r in cur.fetchall()]
print("Current columns:", cols)

# Add missing columns if needed
needed = {
    "rejection_reason": "ALTER TABLE epic_proposals ADD COLUMN IF NOT EXISTS rejection_reason TEXT",
    "rationale": "ALTER TABLE epic_proposals ADD COLUMN IF NOT EXISTS rationale TEXT",
    "depends_on": "ALTER TABLE epic_proposals ADD COLUMN IF NOT EXISTS depends_on UUID[]",
}

for col, sql in needed.items():
    if col not in cols:
        print(f"  Adding missing column: {col}")
        cur.execute(sql)

# Remove old columns we don't use
old_cols = {"suggested_owner_id", "reviewed_by", "review_reason", "reviewed_at"}
for col in old_cols:
    if col in cols:
        print(f"  (keeping old column {col} for now)")

conn.commit()

# Check again
cur.execute(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name='epic_proposals' ORDER BY ordinal_position"
)
print("Final columns:", [r[0] for r in cur.fetchall()])

# Also check context_boundaries and task_skills
for tbl in ["context_boundaries", "task_skills"]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name=%s ORDER BY ordinal_position", (tbl,)
    )
    cols = [r[0] for r in cur.fetchall()]
    print(f"{tbl} columns: {cols}")

conn.close()
