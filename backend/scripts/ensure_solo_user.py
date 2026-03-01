"""Ensure solo admin user exists in DB."""
import psycopg2

conn = psycopg2.connect("postgresql://hivemind:hivemind@postgres:5432/hivemind")
cur = conn.cursor()

# Check for existing users
cur.execute("SELECT id, username, role FROM users")
users = cur.fetchall()
print(f"Existing users: {users}")

# Insert solo admin if not present
cur.execute("""
    INSERT INTO users (id, username, display_name, role)
    VALUES ('00000000-0000-0000-0000-000000000001', 'solo', 'Solo Admin', 'admin')
    ON CONFLICT (username) DO NOTHING
""")
conn.commit()

cur.execute("SELECT id, username, role FROM users")
print(f"Users after: {cur.fetchall()}")
conn.close()
