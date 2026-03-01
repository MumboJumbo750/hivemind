"""Extract all data from DB via API for seed sync."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import json

BASE = "http://localhost:8000"

def api_get(path, **params):
    r = requests.get(f"{BASE}{path}", params=params)
    r.raise_for_status()
    body = r.json()
    # Unwrap paginated responses
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body

def mcp_call(tool, arguments=None):
    r = requests.post(f"{BASE}/api/mcp/call", json={"tool": tool, "arguments": arguments or {}})
    r.raise_for_status()
    return r.json()

# ── Skills ────────────────────────────────────────────────────────
print("=" * 60)
print("  SKILLS")
print("=" * 60)
skills = api_get("/api/skills", limit=100)
print(f"Total: {len(skills)}")
for s in skills:
    print(f"  {s['title']}")
    print(f"    lifecycle={s.get('lifecycle')} confidence={s.get('confidence')}")
    print(f"    service_scope={s.get('service_scope')} stack={s.get('stack')}")
    print(f"    source_epics={s.get('source_epics')}")
    print()

# ── Epics ─────────────────────────────────────────────────────────
print("=" * 60)
print("  EPICS")
print("=" * 60)
epics_resp = mcp_call("list_epics")
epics = epics_resp.get("epics", [])
if isinstance(epics, dict):
    epics = epics.get("epics", [])
print(f"Total: {len(epics)}")
for e in epics:
    print(f"  {e.get('epic_key')} | state={e.get('state')} | title={e.get('title','')[:80]}")

# ── Wiki ──────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  WIKI ARTICLES")
print("=" * 60)
try:
    wiki = mcp_call("list_wiki_articles")
    articles = wiki.get("articles", wiki.get("result", []))
    if isinstance(articles, dict):
        articles = articles.get("articles", [])
    print(f"Total: {len(articles)}")
    for a in articles:
        print(f"  slug={a.get('slug')} | title={a.get('title')}")
except Exception as ex:
    print(f"Error: {ex}")

# ── Docs ──────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  EPIC DOCS")
print("=" * 60)
for e in epics:
    try:
        docs = mcp_call("list_epic_docs", {"epic_key": e["epic_key"]})
        docs_list = docs.get("docs", docs.get("result", []))
        if isinstance(docs_list, dict):
            docs_list = docs_list.get("docs", [])
        if docs_list:
            for d in docs_list:
                print(f"  [{e['epic_key']}] title={d.get('title')} id={d.get('id')}")
    except:
        pass

# ── Decision Records ─────────────────────────────────────────────
print()
print("=" * 60)
print("  DECISION RECORDS")
print("=" * 60)
try:
    decisions = mcp_call("list_decisions")
    decs = decisions.get("decisions", decisions.get("result", []))
    if isinstance(decs, dict):
        decs = decs.get("decisions", [])
    print(f"Total: {len(decs)}")
    for d in decs:
        print(f"  key={d.get('decision_key')} | title={d.get('title')} | status={d.get('status')}")
except Exception as ex:
    print(f"Error: {ex}")

# ── Tasks ─────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  TASKS (per epic)")
print("=" * 60)
for e in epics:
    try:
        tasks = mcp_call("list_tasks", {"epic_key": e["epic_key"], "limit": 60})
        task_list = tasks.get("tasks", tasks.get("result", []))
        if isinstance(task_list, dict):
            task_list = task_list.get("tasks", [])
        print(f"  {e['epic_key']}: {len(task_list)} tasks")
    except Exception as ex:
        print(f"  {e['epic_key']}: Error - {ex}")
