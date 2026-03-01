"""Submit and merge all draft skills to active state."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.api_test as a

r = a.api_get('/api/skills?limit=100')
skills = r['data']
drafts = [s for s in skills if s['lifecycle'] == 'draft']
print(f"Found {len(drafts)} draft skills:")

for s in drafts:
    sid = s['id']
    title = s['title']
    print(f"\n  [{title}] ({sid[:8]}...)")
    
    # Submit for review: draft -> pending_merge
    r1 = a.mcp_call('hivemind/submit_skill_proposal', {'skill_id': sid})
    r1_text = json.dumps(r1)[:150]
    print(f"    submit: {r1_text}")
    
    # Merge: pending_merge -> active
    r2 = a.mcp_call('hivemind/merge_skill', {'skill_id': sid})
    r2_text = json.dumps(r2)[:150]
    print(f"    merge:  {r2_text}")

print("\n\nDone! Checking final state...")
r = a.api_get('/api/skills?limit=100')
skills = r['data']
active = [s for s in skills if s['lifecycle'] == 'active']
draft = [s for s in skills if s['lifecycle'] == 'draft']
pending = [s for s in skills if s['lifecycle'] == 'pending_merge']
print(f"Skills: {len(active)} active, {len(pending)} pending, {len(draft)} draft")
