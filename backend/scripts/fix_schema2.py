"""Quick utility to align epic_proposals schema with what the app expects."""
import psycopg2

conn = psycopg2.connect("postgresql://hivemind:hivemind@postgres:5432/hivemind")
cur = conn.cursor()

# Add missing updated_at column
fixes = [
    "ALTER TABLE epic_proposals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now()",
    # Ensure version default is 1 not 0
    "ALTER TABLE epic_proposals ALTER COLUMN version SET DEFAULT 1",
]

for sql in fixes:
    print(f"  Executing: {sql[:80]}...")
    cur.execute(sql)

conn.commit()

# Final schema
cur.execute(
    "SELECT column_name, data_type FROM information_schema.columns "
    "WHERE table_name='epic_proposals' ORDER BY ordinal_position"
)
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
print("Done.")
