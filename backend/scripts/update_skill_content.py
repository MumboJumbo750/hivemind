"""Update skill content from seed files for changed skills."""
import sys
import psycopg2
import psycopg2.extras
from pathlib import Path

SEED_DIR = Path("/seed")
DSN = "postgresql://hivemind:hivemind@postgres/hivemind"
SLUGS_TO_UPDATE = {"mcp-write-tool"}


def main():
    conn = psycopg2.connect(DSN, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    cur = conn.cursor()

    skills_dir = SEED_DIR / "skills"
    updated = 0

    for slug in SLUGS_TO_UPDATE:
        f = skills_dir / f"{slug}.md"
        if not f.exists():
            print(f"  WARNUNG: {f} nicht gefunden", file=sys.stderr)
            continue

        raw = f.read_text(encoding="utf-8")
        # strip frontmatter
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else raw
        else:
            body = raw

        cur.execute(
            "UPDATE skills SET content = %s WHERE source_slug = %s RETURNING title",
            (body, slug),
        )
        row = cur.fetchone()
        if row:
            print(f"  ✓ Skill aktualisiert: {row['title']} ({slug})")
            updated += 1
        else:
            print(f"  WARNUNG: Kein Skill mit source_slug={slug} gefunden")

    conn.commit()
    print(f"\n→ {updated} Skills aktualisiert.")


main()
