"""
Seed Sync: Extract data from DB, update seed files, prepare for clean reseed.

Steps:
1. Fetch all data from DB via MCP + REST
2. Compare with existing seed files
3. Create/update seed files to match DB
4. Report diffs
"""
import io
import json
import os
import re
import sys
import urllib.request
import yaml
from pathlib import Path

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"
SEED_DIR = Path(__file__).resolve().parent.parent / "seed"

# ── API helpers ───────────────────────────────────────────────────────────────

def mcp_call(tool_name: str, args: dict = None) -> dict:
    """Call MCP tool and return parsed result."""
    url = f"{BASE}/api/mcp/call"
    body = json.dumps({"tool": f"hivemind-{tool_name}", "arguments": args or {}}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode("utf-8"))
    text = resp["result"][0]["text"]
    return json.loads(text)


def api_get(path: str, params: dict = None):
    """GET request to API, unwraps paginated responses."""
    url = f"{BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{qs}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read().decode("utf-8"))
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


# ── Frontmatter helpers ──────────────────────────────────────────────────────

def parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown."""
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].lstrip("\n")
            return meta, body
    return {}, raw


def build_frontmatter_md(meta: dict, body: str) -> str:
    """Build a markdown file with YAML frontmatter."""
    fm = yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{fm}---\n\n{body}"


def slugify(title: str) -> str:
    """Convert title to filename slug."""
    s = title.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


# ── Extract ───────────────────────────────────────────────────────────────────

def extract_all() -> dict:
    """Extract all data from DB."""
    data = {}

    # Epics (via MCP for full detail)
    print("[1] Extracting epics...")
    epics_list_resp = mcp_call("list_epics")
    epics_basic = epics_list_resp.get("data", [])
    data["epics"] = []
    for e in epics_basic:
        detail = mcp_call("get_epic", {"epic_key": e["epic_key"]})
        detail["_basic"] = e
        data["epics"].append(detail)
        print(f"    {e['epic_key']}: state={e['state']}")
    print(f"    Total: {len(data['epics'])} epics")

    # Skills (via REST for full content)
    print("\n[2] Extracting skills...")
    data["skills"] = api_get("/api/skills", {"limit": "200"})
    print(f"    Total: {len(data['skills'])} skills")
    for s in data["skills"]:
        print(f"    - {s['title']} (confidence={s['confidence']}, lifecycle={s['lifecycle']})")

    # Wiki articles (list + full content)
    print("\n[3] Extracting wiki articles...")
    wiki_resp = mcp_call("list_wiki_articles")
    wiki_list = wiki_resp.get("articles", [])
    data["wiki"] = []
    for a in wiki_list:
        detail = mcp_call("get_wiki_article", {"slug": a["slug"]})
        data["wiki"].append(detail)
        print(f"    - {a['slug']}")
    print(f"    Total: {len(data['wiki'])} wiki articles")

    # Epic docs
    print("\n[4] Extracting epic docs...")
    data["docs"] = []
    for e in data["epics"]:
        ek = e["_basic"]["epic_key"]
        try:
            docs_resp = mcp_call("list_epic_docs", {"epic_key": ek})
            docs_list = docs_resp.get("docs", [])
            for d in docs_list:
                detail = mcp_call("get_epic_doc", {"doc_id": d["id"]})
                detail["_epic_key"] = ek
                data["docs"].append(detail)
                print(f"    [{ek}] {d.get('title', '?')}")
        except Exception:
            pass
    print(f"    Total: {len(data['docs'])} docs")

    # Decision records
    print("\n[5] Extracting decision records...")
    try:
        dec_resp = mcp_call("list_decisions")
        dec_list = dec_resp.get("decisions", [])
        data["decisions"] = []
        for d in dec_list:
            detail = mcp_call("get_decision", {"decision_key": d["decision_key"]})
            data["decisions"].append(detail)
            print(f"    - {d['decision_key']}: {d.get('title', '')}")
    except Exception as ex:
        data["decisions"] = []
        print(f"    WARN: {ex}")
    print(f"    Total: {len(data['decisions'])} decisions")

    # Tasks per epic
    print("\n[6] Extracting tasks...")
    data["tasks"] = {}
    total_tasks = 0
    for e in data["epics"]:
        ek = e["_basic"]["epic_key"]
        try:
            tasks_resp = mcp_call("list_tasks", {"epic_key": ek, "limit": 100})
            task_list = tasks_resp.get("tasks", [])
            data["tasks"][ek] = task_list
            total_tasks += len(task_list)
            print(f"    {ek}: {len(task_list)} tasks")
        except Exception as ex:
            data["tasks"][ek] = []
            print(f"    {ek}: Error - {ex}")
    print(f"    Total: {total_tasks} tasks")

    return data


# ── Compare & Sync ───────────────────────────────────────────────────────────

def sync_epics(epics: list):
    """Update epic JSON files with current DB state."""
    print("\n" + "=" * 60)
    print("  SYNC: Epics")
    print("=" * 60)

    changed = 0
    for e in epics:
        basic = e["_basic"]
        ek = basic["epic_key"]
        # Map epic_key to seed filename
        # EPIC-PHASE-1A -> phase-1a.json
        slug = ek.replace("EPIC-PHASE-", "phase-").lower()
        fpath = SEED_DIR / "epics" / f"{slug}.json"

        if not fpath.exists():
            print(f"  WARN: No seed file for {ek} at {fpath}")
            continue

        with open(fpath, "r", encoding="utf-8") as f:
            seed_data = json.load(f)

        # Check state diff
        db_state = basic["state"]
        seed_state = seed_data.get("state", "incoming")

        if db_state != seed_state:
            print(f"  UPDATE {ek}: state '{seed_state}' -> '{db_state}'")
            seed_data["state"] = db_state
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(seed_data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            changed += 1
        else:
            print(f"  OK {ek}: state={db_state}")

    print(f"  -> {changed} epic files updated")


def sync_skills(skills: list):
    """Create seed files for skills missing from seed directory."""
    print("\n" + "=" * 60)
    print("  SYNC: Skills")
    print("=" * 60)

    skills_dir = SEED_DIR / "skills"
    existing_titles = set()

    # Read existing seed skills
    for f in skills_dir.glob("*.md"):
        raw = f.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(raw)
        title = meta.get("title", f.stem)
        existing_titles.add(title)

    created = 0
    for s in skills:
        title = s["title"]
        if title in existing_titles:
            print(f"  OK: {title}")
            continue

        # Create new seed file
        slug = slugify(title)
        fpath = skills_dir / f"{slug}.md"

        meta = {"title": title}
        if s.get("service_scope"):
            meta["service_scope"] = s["service_scope"]
        if s.get("stack"):
            meta["stack"] = s["stack"]
        if s.get("version_range"):
            meta["version_range"] = s["version_range"]
        meta["confidence"] = s.get("confidence", 0.5)
        if s.get("source_epics"):
            meta["source_epics"] = s["source_epics"]
        if s.get("skill_type") and s["skill_type"] != "domain":
            meta["skill_type"] = s["skill_type"]

        content = s.get("content", "")
        md = build_frontmatter_md(meta, content)

        with open(fpath, "w", encoding="utf-8") as f:
            f.write(md)

        print(f"  NEW: {title} -> {fpath.name}")
        created += 1

    print(f"  -> {created} new skill files created, {len(existing_titles)} already existed")


def sync_wiki(wiki_articles: list):
    """Create seed files for wiki articles missing from seed directory."""
    print("\n" + "=" * 60)
    print("  SYNC: Wiki")
    print("=" * 60)

    wiki_dir = SEED_DIR / "wiki"
    existing_slugs = set()

    for f in wiki_dir.glob("*.md"):
        raw = f.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(raw)
        slug = meta.get("slug", f.stem)
        existing_slugs.add(slug)

    created = 0
    for a in wiki_articles:
        slug = a.get("slug", "")
        if slug in existing_slugs:
            print(f"  OK: {slug}")
            continue

        fpath = wiki_dir / f"{slug}.md"
        meta = {
            "slug": slug,
            "title": a.get("title", slug),
            "tags": a.get("tags", []),
            "linked_epics": a.get("linked_epics", []),
        }
        content = a.get("content", "")
        md = build_frontmatter_md(meta, content)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"  NEW: {slug} -> {fpath.name}")
        created += 1

    print(f"  -> {created} new wiki files, {len(existing_slugs)} already existed")


def sync_docs(docs: list):
    """Create seed files for epic docs missing from seed directory."""
    print("\n" + "=" * 60)
    print("  SYNC: Docs")
    print("=" * 60)

    docs_dir = SEED_DIR / "docs"
    existing_titles = set()

    for f in docs_dir.glob("*.md"):
        raw = f.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(raw)
        title = meta.get("title", f.stem)
        existing_titles.add(title)

    created = 0
    for d in docs:
        title = d.get("title", "")
        if title in existing_titles:
            print(f"  OK: {title}")
            continue

        epic_key = d.get("_epic_key", "")
        slug = slugify(title)
        fpath = docs_dir / f"{slug}.md"

        meta = {
            "epic_ref": epic_key,
            "title": title,
        }
        content = d.get("content", "")
        md = build_frontmatter_md(meta, content)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"  NEW: {title} -> {fpath.name}")
        created += 1

    print(f"  -> {created} new doc files, {len(existing_titles)} already existed")


def sync_decisions(decisions: list):
    """Create seed files for decision records."""
    print("\n" + "=" * 60)
    print("  SYNC: Decisions")
    print("=" * 60)

    dec_dir = SEED_DIR / "decisions"
    dec_dir.mkdir(exist_ok=True)

    existing = set()
    for f in dec_dir.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        existing.add(data.get("decision_key", f.stem))

    created = 0
    for d in decisions:
        dk = d.get("decision_key", "")
        if dk in existing:
            print(f"  OK: {dk}")
            continue

        slug = slugify(dk)
        fpath = dec_dir / f"{slug}.json"
        seed_data = {
            "decision_key": dk,
            "title": d.get("title", ""),
            "status": d.get("status", "proposed"),
            "context": d.get("context", ""),
            "decision": d.get("decision", ""),
            "consequences": d.get("consequences", ""),
            "linked_epics": d.get("linked_epics", []),
        }
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(seed_data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  NEW: {dk} -> {fpath.name}")
        created += 1

    print(f"  -> {created} new decision files, {len(existing)} already existed")


def sync_tasks(tasks_by_epic: dict):
    """Report task counts per epic. Tasks are already fully seeded."""
    print("\n" + "=" * 60)
    print("  SYNC: Tasks")
    print("=" * 60)

    tasks_dir = SEED_DIR / "tasks"
    for ek, tasks in sorted(tasks_by_epic.items()):
        slug = ek.replace("EPIC-PHASE-", "phase-").lower()
        phase_dir = tasks_dir / slug
        seed_count = len(list(phase_dir.glob("*.json"))) if phase_dir.exists() else 0
        db_count = len(tasks)
        status = "OK" if seed_count == db_count else "DIFF"
        print(f"  {status} {ek}: seed={seed_count} db={db_count}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Hivemind Seed Sync")
    print("=" * 60)
    print(f"Seed directory: {SEED_DIR}")
    print()

    data = extract_all()

    # Save raw extract
    out_file = Path(__file__).resolve().parent / "db_extract.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nRaw extract saved to: {out_file}")

    # Sync seed files
    sync_epics(data["epics"])
    sync_skills(data["skills"])
    sync_wiki(data["wiki"])
    sync_docs(data["docs"])
    sync_decisions(data["decisions"])
    sync_tasks(data["tasks"])

    print("\n" + "=" * 60)
    print("  Seed sync complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
