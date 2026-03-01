"""Gärtner scan: list all done tasks across completed phases and identify skill gaps for Phase 7."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.api_test as a
import json

PHASE_EPICS = [
    'EPIC-PHASE-1A', 'EPIC-PHASE-1B', 'EPIC-PHASE-2', 'EPIC-PHASE-F',
    'EPIC-PHASE-3', 'EPIC-PHASE-4', 'EPIC-PHASE-5', 'EPIC-PHASE-6'
]

all_done = []
for epic_key in PHASE_EPICS:
    r = a.mcp_call('hivemind/list_tasks', {'epic_key': epic_key})
    data = json.loads(r['result'][0]['text'])
    tasks = data['data']
    done = [t for t in tasks if t['state'] == 'done']
    print(f"{epic_key}: {len(done)} done tasks")
    for t in done:
        tk = t['task_key']
        title = t['title']
        print(f"  {tk:15s} | {title}")
        all_done.append(t)

print(f"\nTotal done tasks: {len(all_done)}")

# Phase 7 relevant keywords
p7_keywords = ['outbox', 'sync', 'dlq', 'dead letter', 'sentry', 'youtrack', 
               'webhook', 'bug', 'heatmap', 'kpi', 'dashboard', 'embedding',
               'pgvector', 'routing', 'consumer', 'cron', 'retention',
               'nexus', 'graph', 'triage']

print("\n--- Phase 7 relevant done tasks ---")
for t in all_done:
    title_lower = t['title'].lower()
    matching = [kw for kw in p7_keywords if kw in title_lower]
    if matching:
        print(f"  {t['task_key']:15s} | {t['title']:50s} | keywords: {matching}")
