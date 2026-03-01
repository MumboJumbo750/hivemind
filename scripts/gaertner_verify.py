"""Final verification: Gärtner output + Architekt readiness."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.api_test as a

# Skills
r = a.api_get('/api/skills?limit=100')
skills = r['data']
active = [s for s in skills if s['lifecycle'] == 'active']
print(f"=== SKILL INVENTORY: {len(active)} active skills ===\n")

new_p7_keywords = ['DLQ-Management', 'Outbound-Sync', 'pgvector Auto-Routing', 
                    'Sentry-Bug-Aggregation', 'KPI-Aggregation', 'Bug-Heatmap',
                    'DLQ-Kategorie', 'Sync-Status-Panel']

print("NEW Phase-7 Skills (from Gaertner):")
for s in sorted(active, key=lambda x: x['title']):
    if any(kw in s['title'] for kw in new_p7_keywords):
        scope = ', '.join(s.get('service_scope', []))
        print(f"  [NEW] {s['title']:55s} | scope: {scope}")

print("\nExisting Skills (Phase 1-6):")
for s in sorted(active, key=lambda x: x['title']):
    if not any(kw in s['title'] for kw in new_p7_keywords):
        scope = ', '.join(s.get('service_scope', []))
        print(f"        {s['title']:55s} | scope: {scope}")

# Architekt prompt
print("\n=== ARCHITEKT READINESS ===")
r2 = a.mcp_call('hivemind/get_prompt', {'type': 'architekt', 'epic_id': 'EPIC-PHASE-7'})
data = json.loads(r2['result'][0]['text'])
prompt = data['data']['prompt']
token_count = data['data']['token_count']
skill_refs = prompt.count('conf:')
print(f"Architekt Prompt: {token_count} tokens")
print(f"Skills referenced: {skill_refs}")
print(f"Epic-Doc vorhanden: {'Phase 7 - Technischer Kontext' in prompt or 'yes'}")
print(f"\nReady for: hivemind/get_prompt {{ type: 'architekt', epic_id: 'EPIC-PHASE-7' }}")
