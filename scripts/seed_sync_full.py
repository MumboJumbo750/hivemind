"""
Complete Seed Sync: Extract DB state → update seed files.
Run from project root: py scripts/seed_sync_full.py
"""
import io, json, os, re, sys, urllib.request, yaml, subprocess
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"
ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed"

# ── Helpers ───────────────────────────────────────────────────────────────────

def mcp_call(tool: str, args: dict = None) -> dict:
    url = f"{BASE}/api/mcp/call"
    body = json.dumps({"tool": f"hivemind-{tool}", "arguments": args or {}}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return json.loads(resp["result"][0]["text"])

def api_get(path: str, params: dict = None):
    url = f"{BASE}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    with urllib.request.urlopen(url, timeout=30) as r:
        body = json.loads(r.read().decode("utf-8"))
    return body.get("data", body) if isinstance(body, dict) and "data" in body else body

def psql(query: str) -> str:
    """Run psql query in the postgres container."""
    result = subprocess.run(
        ["podman", "exec", "hivemind-postgres-1", "psql", "-U", "hivemind", "-d", "hivemind", "-t", "-A", "-c", query],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
    )
    return result.stdout.strip()

def slugify(title: str) -> str:
    s = title.lower()
    for a, b in [("ä","ae"),("ö","oe"),("ü","ue"),("ß","ss"),("→","-"),("—","-"),("–","-")]:
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def build_md(meta: dict, body: str) -> str:
    # Use block style for everything, match existing seed file format
    fm = yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{fm}---\n\n{body}\n"


# ══════════════════════════════════════════════════════════════════════════════
#  1) EPIC STATE SYNC
# ══════════════════════════════════════════════════════════════════════════════

def sync_epic_states():
    print("\n[1/5] Syncing epic states...")
    epics = mcp_call("list_epics").get("data", [])
    changed = 0
    for e in epics:
        ek = e["epic_key"]
        slug = ek.replace("EPIC-PHASE-", "phase-").lower()
        fpath = SEED / "epics" / f"{slug}.json"
        if not fpath.exists():
            print(f"  SKIP {ek}: no seed file")
            continue
        seed = json.loads(fpath.read_text("utf-8"))
        if seed.get("state") != e["state"]:
            old = seed["state"]
            seed["state"] = e["state"]
            fpath.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n", "utf-8")
            print(f"  UPDATE {ek}: {old} -> {e['state']}")
            changed += 1
        else:
            print(f"  OK {ek}: {e['state']}")
    print(f"  -> {changed} epic files updated")


# ══════════════════════════════════════════════════════════════════════════════
#  2) NEW SKILLS
# ══════════════════════════════════════════════════════════════════════════════

def sync_skills():
    print("\n[2/5] Syncing skills...")
    skills_dir = SEED / "skills"

    # Read existing titles from seed
    existing_titles = set()
    for f in skills_dir.glob("*.md"):
        raw = f.read_text("utf-8")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                existing_titles.add(meta.get("title", f.stem))

    # Fetch all skills from API (includes content)
    skills = api_get("/api/skills", {"limit": "200"})
    created = 0

    for s in skills:
        title = s["title"]
        if title in existing_titles:
            continue

        slug = slugify(title)
        fpath = skills_dir / f"{slug}.md"

        meta = {"title": title}
        if s.get("service_scope"):
            meta["service_scope"] = s["service_scope"]
        if s.get("stack"):
            meta["stack"] = s["stack"]
        if s.get("version_range"):
            meta["version_range"] = s["version_range"]
        meta["confidence"] = float(s.get("confidence", 0.5))
        # New Gärtner skills are from Phase 7
        meta["source_epics"] = ["EPIC-PHASE-7"]

        content = s.get("content", "")
        fpath.write_text(build_md(meta, content), "utf-8")
        print(f"  NEW: {title} -> {fpath.name}")
        created += 1

    print(f"  -> {created} new skill files, {len(existing_titles)} already existed")


# ══════════════════════════════════════════════════════════════════════════════
#  3) PHASE 6 TASKS
# ══════════════════════════════════════════════════════════════════════════════

def sync_tasks():
    print("\n[3/5] Syncing tasks...")
    tasks_dir = SEED / "tasks"

    # Get epic_key -> UUID mapping from DB
    epic_map_raw = psql("SELECT epic_key, id FROM epics ORDER BY epic_key;")
    epic_map = {}
    for line in epic_map_raw.split("\n"):
        if "|" in line:
            ek, uid = line.strip().split("|", 1)
            epic_map[ek.strip()] = uid.strip()

    epics = mcp_call("list_epics").get("data", [])
    for e in epics:
        ek = e["epic_key"]
        slug = ek.replace("EPIC-PHASE-", "phase-").lower()
        phase_dir = tasks_dir / slug
        seed_count = len(list(phase_dir.glob("*.json"))) if phase_dir.exists() else 0

        # Get task count from DB
        epic_uuid = epic_map.get(ek, "")
        if not epic_uuid:
            print(f"  SKIP {ek}: no UUID")
            continue

        tasks = mcp_call("list_tasks", {"epic_id": epic_uuid, "limit": 100}).get("data", [])
        db_count = len(tasks)

        if seed_count == db_count:
            print(f"  OK {ek}: {db_count} tasks")
            continue

        if db_count == 0:
            print(f"  SKIP {ek}: 0 tasks in DB")
            continue

        if seed_count > 0:
            print(f"  DIFF {ek}: seed={seed_count} vs db={db_count} -- not overwriting")
            continue

        # Need to create task files
        phase_dir.mkdir(parents=True, exist_ok=True)
        print(f"  CREATE {ek}: {db_count} tasks")

        for t in tasks:
            tk = t.get("task_key", "")
            task_detail = mcp_call("get_task", {"task_key": tk})

            task_data = {
                "external_id": tk,
                "epic_ref": ek,
                "title": t.get("title", ""),
                "description": task_detail.get("description", ""),
                "state": t.get("state", "incoming"),
            }

            dod = task_detail.get("definition_of_done")
            if dod:
                task_data["definition_of_done"] = dod

            ps = task_detail.get("pinned_skills")
            if ps:
                task_data["pinned_skills"] = ps

            fname = slugify(tk) + ".json"
            fpath = phase_dir / fname
            fpath.write_text(json.dumps(task_data, indent=2, ensure_ascii=False) + "\n", "utf-8")

        print(f"    -> {db_count} task files created in {phase_dir.name}/")


# ══════════════════════════════════════════════════════════════════════════════
#  4) EPIC DOCS
# ══════════════════════════════════════════════════════════════════════════════

def sync_docs():
    print("\n[4/5] Syncing epic docs...")
    docs_dir = SEED / "docs"

    # Read existing doc titles
    existing = set()
    for f in docs_dir.glob("*.md"):
        raw = f.read_text("utf-8")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                existing.add(meta.get("title", f.stem))

    # Query DB for doc metadata (id, title, epic_key) using double-pipe delimiter
    rows = psql("SELECT d.id || '||' || d.title || '||' || e.epic_key FROM docs d JOIN epics e ON d.epic_id = e.id ORDER BY e.epic_key;")
    created = 0
    for line in rows.split("\n"):
        line = line.strip()
        if not line or "||" not in line:
            continue
        parts = line.split("||", 2)
        if len(parts) < 3:
            continue
        doc_id, title, epic_key = parts[0].strip(), parts[1].strip(), parts[2].strip()

        if title in existing:
            print(f"  OK: {title}")
            continue

        slug = slugify(title)
        fpath = docs_dir / f"{slug}.md"

        # Get full content via MCP
        content = ""
        try:
            detail = mcp_call("get_doc", {"id": doc_id})
            # Response may be nested: {"data": {"content": ...}}
            if "data" in detail and isinstance(detail["data"], dict):
                content = detail["data"].get("content", "")
            else:
                content = detail.get("content", "")
        except Exception as ex:
            print(f"  WARN: Could not fetch doc content for {title}: {ex}")

        meta = {"epic_ref": epic_key, "title": title}
        fpath.write_text(build_md(meta, content), "utf-8")
        print(f"  NEW: {title} -> {fpath.name}")
        created += 1

    print(f"  -> {created} new doc files, {len(existing)} already existed")


# ══════════════════════════════════════════════════════════════════════════════
#  5) DECISION RECORDS
# ══════════════════════════════════════════════════════════════════════════════

def sync_decisions():
    print("\n[5/5] Syncing decision records...")
    dec_dir = SEED / "decisions"
    dec_dir.mkdir(exist_ok=True)

    # Query DB for decision records using concat to avoid pipe-in-content issues
    rows = psql("""
        SELECT dr.id || '^^^^' || dr.decision || '^^^^' || dr.rationale || '^^^^' || COALESCE(e.epic_key, '')
        FROM decision_records dr
        LEFT JOIN epics e ON dr.epic_id = e.id
        ORDER BY dr.created_at;
    """)

    existing = set(f.stem for f in dec_dir.glob("*.json"))
    created = 0
    idx = 1

    for line in rows.split("\n"):
        line = line.strip()
        if not line or "^^^^" not in line:
            continue
        parts = line.split("^^^^", 3)
        if len(parts) < 4:
            continue
        dr_id, decision, rationale, epic_key = [p.strip() for p in parts]

        slug = f"DR-{idx:03d}"
        fname = slug.lower()
        if fname in existing:
            print(f"  OK: {slug}")
            idx += 1
            continue

        data = {
            "decision_key": slug,
            "epic_ref": epic_key,
            "decision": decision,
            "rationale": rationale,
        }
        fpath = dec_dir / f"{fname}.json"
        fpath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
        print(f"  NEW: {slug} -> {fpath.name}")
        created += 1
        idx += 1

    print(f"  -> {created} new decision files")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Hivemind Seed Sync")
    print("=" * 60)

    sync_epic_states()
    sync_skills()
    sync_tasks()
    sync_docs()
    sync_decisions()

    print("\n" + "=" * 60)
    print("  Seed sync complete!")
    print("  Next: wipe DB and reseed fresh")
    print("=" * 60)


if __name__ == "__main__":
    main()
