#!/usr/bin/env python3
"""
Idempotenter Seed-Import für das Hivemind-Projekt.

Liest den seed/-Ordner und befüllt die Datenbank mit dem Hivemind-Projekt
als erstem Datensatz. Vollständig idempotent:
  - projects, wiki_articles, skills via ON CONFLICT (slug / title) DO NOTHING
  - epics, tasks via ON CONFLICT (external_id) DO NOTHING
  - admin-User via ON CONFLICT (username) DO NOTHING

Verwendung (aus dem backend-Verzeichnis):
    python -m scripts.seed_import

Oder via Docker Compose:
    docker compose exec backend python -m scripts.seed_import
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import yaml

# ─── Pfade ────────────────────────────────────────────────────────────────────

# backend/scripts/seed_import.py  →  backend/ (parents[1])  →  repo-root (parents[2])
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT   = BACKEND_DIR.parent
SEED_DIR    = REPO_ROOT / "seed"


# ─── DB-Verbindung ────────────────────────────────────────────────────────────

def _dsn_from_url(url: str) -> str:
    """Ersetzt SQLAlchemy-Driver-Prefix, den psycopg2 nicht versteht."""
    return url.replace("postgresql+psycopg2://", "postgresql://")


def get_connection() -> psycopg2.extensions.connection:
    """Öffnet eine synchrone psycopg2-Verbindung."""
    # Zuerst app.config (beim Laufen im Container bereits im PYTHONPATH)
    dsn: str | None = None
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        from app.config import settings
        dsn = _dsn_from_url(settings.database_url_sync)
    except Exception:
        raw = os.environ.get(
            "DATABASE_URL_SYNC",
            "postgresql+psycopg2://hivemind:hivemind@localhost:5432/hivemind",
        )
        dsn = _dsn_from_url(raw)

    try:
        conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    except psycopg2.OperationalError as exc:
        print(f"ERROR: Datenbankverbindung fehlgeschlagen: {exc}")
        print(f"       DSN: {dsn}")
        sys.exit(1)

    return conn


# ─── Frontmatter-Parser ───────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Trennt YAML-Frontmatter (zwischen ---) vom Markdown-Body."""
    text = text.lstrip()
    if not text.startswith("---"):
        return {}, text
    rest = text[3:]
    parts = rest.split("---", 1)
    if len(parts) < 2:
        return {}, text
    fm_raw, body = parts
    try:
        meta: dict[str, Any] = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as exc:
        print(f"  WARNUNG: YAML-Frontmatter konnte nicht geparst werden: {exc}")
        meta = {}
    return meta, body.lstrip()


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def as_str(val: Any) -> str | None:
    """Konvertiert UUID-Objekte und None sicher zu str."""
    return str(val) if val is not None else None


# ─── Bootstrap Admin-User ─────────────────────────────────────────────────────

def upsert_admin_user(cur: psycopg2.extensions.cursor) -> str:
    """
    Erstellt den bootstrap-admin-User falls noch nicht vorhanden.
    Gibt die UUID als String zurück.
    """
    cur.execute("SELECT id FROM users WHERE username = 'admin'")
    row = cur.fetchone()
    if row:
        admin_id = as_str(row["id"])
        print(f"  ✓ Admin bereits vorhanden: {admin_id}")
        return admin_id

    admin_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO users (id, username, display_name, role)
        VALUES (%s, 'admin', 'Admin', 'admin')
        ON CONFLICT (username) DO NOTHING
        """,
        (admin_id,),
    )
    # Sicherheitshalber nochmal lesen (ON CONFLICT könnte zugeschlagen haben)
    cur.execute("SELECT id FROM users WHERE username = 'admin'")
    admin_id = as_str(cur.fetchone()["id"])
    print(f"  ✓ Admin erstellt: {admin_id}")
    return admin_id


# ─── Project ──────────────────────────────────────────────────────────────────

def import_project(cur: psycopg2.extensions.cursor, admin_id: str) -> str:
    """
    Importiert seed/project.json → projects-Tabelle.
    Gibt die project_id als String zurück.
    """
    project_file = SEED_DIR / "project.json"
    if not project_file.exists():
        print(f"  ERROR: {project_file} nicht gefunden.")
        sys.exit(1)

    data: dict[str, Any] = json.loads(project_file.read_text(encoding="utf-8"))
    slug: str = data["slug"]

    cur.execute("SELECT id FROM projects WHERE slug = %s", (slug,))
    row = cur.fetchone()
    if row:
        project_id = as_str(row["id"])
        print(f"  ✓ Project bereits vorhanden (slug={slug}): {project_id}")
        return project_id

    project_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO projects (id, name, slug, description, created_by)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (slug) DO NOTHING
        """,
        (project_id, data["name"], slug, data.get("description"), admin_id),
    )
    cur.execute("SELECT id FROM projects WHERE slug = %s", (slug,))
    project_id = as_str(cur.fetchone()["id"])
    print(f"  ✓ Project importiert (slug={slug}): {project_id}")
    return project_id


# ─── Epics ────────────────────────────────────────────────────────────────────

def import_epics(
    cur: psycopg2.extensions.cursor,
    project_id: str,
    admin_id: str,
) -> dict[str, str]:
    """
    Importiert seed/epics/*.json → epics-Tabelle.
    Gibt {external_id → epic_id} zurück.
    """
    epics_dir = SEED_DIR / "epics"
    if not epics_dir.exists():
        print("  WARNUNG: seed/epics/ nicht gefunden, übersprungen.")
        return {}

    epic_map: dict[str, str] = {}
    ok = skipped = 0

    for f in sorted(epics_dir.glob("*.json")):
        data: dict[str, Any] = json.loads(f.read_text(encoding="utf-8"))
        external_id: str | None = data.get("external_id")
        if not external_id:
            print(f"  WARNUNG: {f.name}: kein external_id — übersprungen.")
            skipped += 1
            continue

        cur.execute("SELECT id FROM epics WHERE external_id = %s", (external_id,))
        row = cur.fetchone()
        if row:
            epic_map[external_id] = as_str(row["id"])
            print(f"  ✓ Epic bereits vorhanden: {external_id}")
            skipped += 1
            continue

        epic_id = str(uuid.uuid4())

        # definition_of_done: Text-String → JSON-Objekt {text: "..."}
        dod: Any = data.get("definition_of_done")
        if isinstance(dod, str):
            dod_jsonb = json.dumps({"text": dod})
        elif dod is not None:
            dod_jsonb = json.dumps(dod)
        else:
            dod_jsonb = None

        priority: str = data.get("priority", "medium")
        if priority not in ("low", "medium", "high", "critical"):
            print(f"  WARNUNG: {external_id}: ungültiger priority-Wert '{priority}', auf 'medium' zurückgesetzt.")
            priority = "medium"

        state: str = data.get("state", "incoming")

        cur.execute(
            """
            INSERT INTO epics (
                id, epic_key, project_id, external_id,
                title, description,
                owner_id, state, priority, dod_framework
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (external_id) DO NOTHING
            """,
            (
                epic_id,
                external_id,      # epic_key = external_id (Sequenz nicht verwendet)
                project_id,
                external_id,
                data["title"],
                data.get("description"),
                admin_id,
                state,
                priority,
                dod_jsonb,
            ),
        )

        cur.execute("SELECT id FROM epics WHERE external_id = %s", (external_id,))
        epic_map[external_id] = as_str(cur.fetchone()["id"])
        print(f"  ✓ Epic importiert: {external_id} → {epic_map[external_id]}")
        ok += 1

    print(f"  → {ok} neu importiert, {skipped} übersprungen.")
    return epic_map


# ─── Tasks ────────────────────────────────────────────────────────────────────

def import_tasks(
    cur: psycopg2.extensions.cursor,
    epic_map: dict[str, str],
) -> None:
    """
    Importiert seed/tasks/**/*.json → tasks-Tabelle.
    Fehlende epic_ref-Referenzen erzeugen eine Fehlermeldung.
    """
    tasks_dir = SEED_DIR / "tasks"
    if not tasks_dir.exists():
        print("  WARNUNG: seed/tasks/ nicht gefunden, übersprungen.")
        return

    ok = skipped = err = 0

    for f in sorted(tasks_dir.rglob("*.json")):
        data: dict[str, Any] = json.loads(f.read_text(encoding="utf-8"))
        external_id: str | None = data.get("external_id")
        epic_ref: str | None = data.get("epic_ref")

        if not external_id:
            print(f"  WARNUNG: {f.name}: kein external_id — übersprungen.")
            skipped += 1
            continue

        if not epic_ref:
            print(f"  WARNUNG: {external_id}: kein epic_ref — übersprungen.")
            skipped += 1
            continue

        epic_id = epic_map.get(epic_ref)
        if not epic_id:
            print(f"  ERROR: {external_id}: epic_ref '{epic_ref}' nicht in DB / epic_map!")
            err += 1
            continue

        cur.execute("SELECT id, pinned_skills FROM tasks WHERE external_id = %s", (external_id,))
        row = cur.fetchone()
        if row:
            # Update pinned_skills wenn sie sich geändert haben
            seed_skills: list[str] = data.get("pinned_skills") or []
            db_skills: list[str] = row["pinned_skills"] or []
            if sorted(seed_skills) != sorted(db_skills):
                cur.execute(
                    "UPDATE tasks SET pinned_skills = %s::jsonb WHERE id = %s",
                    (json.dumps(seed_skills), as_str(row["id"])),
                )
                print(f"  ✓ Task bereits vorhanden, pinned_skills aktualisiert: {external_id} → {seed_skills}")
            else:
                print(f"  ✓ Task bereits vorhanden: {external_id}")
            skipped += 1
            continue

        task_id = str(uuid.uuid4())

        dod: Any = data.get("definition_of_done")
        dod_jsonb: str | None = json.dumps(dod) if dod is not None else None
        pinned_skills_jsonb: str = json.dumps(data.get("pinned_skills") or [])

        cur.execute(
            """
            INSERT INTO tasks (
                id, task_key, epic_id, external_id,
                title, description,
                state, definition_of_done, pinned_skills
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (external_id) DO NOTHING
            """,
            (
                task_id,
                external_id,    # task_key = external_id
                epic_id,
                external_id,
                data["title"],
                data.get("description"),
                data.get("state", "incoming"),
                dod_jsonb,
                pinned_skills_jsonb,
            ),
        )
        print(f"  ✓ Task importiert: {external_id}")
        ok += 1

    print(f"  → {ok} neu importiert, {skipped} übersprungen, {err} FK-Fehler.")
    if err > 0:
        print("  FEHLER: Es gab Referenzen auf nicht vorhandene Epics — bitte prüfen!")


# ─── Wiki ─────────────────────────────────────────────────────────────────────

def import_wiki(
    cur: psycopg2.extensions.cursor,
    project_id: str,
    admin_id: str,
    epic_map: dict[str, str],
) -> None:
    """
    Importiert seed/wiki/*.md → wiki_articles + wiki_versions-Tabellen.
    Frontmatter-Felder: slug, title, tags, linked_epics
    linked_epics (external_ids) werden zu UUIDs aufgelöst; unbekannte werden ignoriert.
    """
    wiki_dir = SEED_DIR / "wiki"
    if not wiki_dir.exists():
        print("  WARNUNG: seed/wiki/ nicht gefunden, übersprungen.")
        return

    ok = skipped = 0

    for f in sorted(wiki_dir.glob("*.md")):
        raw = f.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)

        slug:   str       = str(meta.get("slug") or f.stem)
        title:  str       = str(meta.get("title") or slug)
        tags:   list[str] = list(meta.get("tags") or [])
        # linked_epics im Frontmatter sind externe IDs ("EPIC-PHASE-1A"),
        # in der DB ist linked_epics UUID[] → auflösen
        linked_epic_refs: list[str] = list(meta.get("linked_epics") or [])
        linked_epic_uuids: list[str] = [
            epic_map[ref] for ref in linked_epic_refs if ref in epic_map
        ]

        cur.execute("SELECT id FROM wiki_articles WHERE slug = %s", (slug,))
        if cur.fetchone():
            print(f"  ✓ Wiki-Artikel bereits vorhanden: {slug}")
            skipped += 1
            continue

        article_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO wiki_articles (
                id, title, slug, content,
                tags, linked_epics,
                author_id
            ) VALUES (
                %s, %s, %s, %s,
                %s::text[], %s::uuid[],
                %s
            )
            ON CONFLICT (slug) DO NOTHING
            """,
            (
                article_id,
                title,
                slug,
                body,
                tags,
                linked_epic_uuids,
                admin_id,
            ),
        )

        # Echte ID nach ON CONFLICT holen
        cur.execute("SELECT id FROM wiki_articles WHERE slug = %s", (slug,))
        actual_id = as_str(cur.fetchone()["id"])

        # wiki_versions: Version 1 anlegen
        cur.execute(
            """
            INSERT INTO wiki_versions (id, article_id, version, content, changed_by)
            VALUES (%s, %s, 1, %s, %s)
            ON CONFLICT (article_id, version) DO NOTHING
            """,
            (str(uuid.uuid4()), actual_id, body, admin_id),
        )

        print(f"  ✓ Wiki-Artikel importiert: {slug}")
        ok += 1

    print(f"  → {ok} neu importiert, {skipped} übersprungen.")


# ─── Skills ───────────────────────────────────────────────────────────────────

def import_skills(
    cur: psycopg2.extensions.cursor,
    project_id: str,
    admin_id: str,
) -> None:
    """
    Importiert seed/skills/*.md → skills + skill_versions-Tabellen.
    Frontmatter-Felder: title, service_scope, stack, version_range, confidence, source_epics
    Dedup-Key: title + project_id (skills-Tabelle hat keine slug-Spalte).
    """
    skills_dir = SEED_DIR / "skills"
    if not skills_dir.exists():
        print("  WARNUNG: seed/skills/ nicht gefunden, übersprungen.")
        return

    ok = skipped = 0

    for f in sorted(skills_dir.glob("*.md")):
        raw = f.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)

        title:         str        = str(meta.get("title") or f.stem)
        service_scope: list[str]  = list(meta.get("service_scope") or [])
        stack:         list[str]  = list(meta.get("stack") or [])
        confidence:    float      = float(meta.get("confidence") or 0.5)
        source_epics:  list[str]  = list(meta.get("source_epics") or [])
        version_range: Any        = meta.get("version_range")

        # Dedup via title + project_id (kein UNIQUE-Constraint auf einzelner Spalte)
        cur.execute(
            "SELECT id FROM skills WHERE title = %s AND project_id = %s",
            (title, project_id),
        )
        if cur.fetchone():
            print(f"  ✓ Skill bereits vorhanden: {title}")
            skipped += 1
            continue

        skill_id = str(uuid.uuid4())
        vr_jsonb: str | None = json.dumps(version_range) if version_range is not None else None

        cur.execute(
            """
            INSERT INTO skills (
                id, project_id, title, content,
                service_scope, stack,
                version_range, confidence,
                source_epics, owner_id
            ) VALUES (
                %s, %s, %s, %s,
                %s::text[], %s::text[],
                %s::jsonb, %s,
                %s::text[], %s
            )
            """,
            (
                skill_id,
                project_id,
                title,
                body,
                service_scope,
                stack,
                vr_jsonb,
                confidence,
                source_epics,
                admin_id,
            ),
        )

        # skill_versions: Version 1 anlegen
        cur.execute(
            """
            INSERT INTO skill_versions (id, skill_id, version, content, changed_by)
            VALUES (%s, %s, 1, %s, %s)
            ON CONFLICT (skill_id, version) DO NOTHING
            """,
            (str(uuid.uuid4()), skill_id, body, admin_id),
        )

        print(f"  ✓ Skill importiert: {title}")
        ok += 1

    print(f"  → {ok} neu importiert, {skipped} übersprungen.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  Hivemind Seed-Import")
    print("=" * 60)
    print(f"Seed-Verzeichnis : {SEED_DIR}")
    print(f"Backend-Verz.    : {BACKEND_DIR}")

    if not SEED_DIR.exists():
        print(f"\nERROR: Seed-Verzeichnis nicht gefunden: {SEED_DIR}")
        sys.exit(1)

    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print("\n[1/6] Bootstrap Admin-User")
            admin_id = upsert_admin_user(cur)

            print("\n[2/6] Project")
            project_id = import_project(cur, admin_id)

            print("\n[3/6] Epics")
            epic_map = import_epics(cur, project_id, admin_id)
            if not epic_map:
                print("  WARNUNG: Keine Epics importiert — Task-Import wird übersprungen.")

            print("\n[4/6] Tasks")
            if epic_map:
                import_tasks(cur, epic_map)
            else:
                print("  Übersprungen (kein epic_map).")

            print("\n[5/6] Wiki")
            import_wiki(cur, project_id, admin_id, epic_map)

            print("\n[6/6] Skills")
            import_skills(cur, project_id, admin_id)

        conn.commit()
        print("\n" + "=" * 60)
        print("  Import erfolgreich abgeschlossen.")
        print("=" * 60)

    except Exception as exc:
        conn.rollback()
        print(f"\nERROR: Unerwarteter Fehler — Transaktion zurückgerollt.")
        print(f"       {type(exc).__name__}: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
