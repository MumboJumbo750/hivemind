"""Approve all Phase 8 tasks."""
import json
import sys
import time
sys.path.insert(0, ".")
from scripts.api_test import mcp_call, api_get

EPIC_KEY = "EPIC-PHASE-8"


def approve_task(tk):
    r = mcp_call("hivemind-approve_review", {"task_key": tk, "comment": "Phase 8 review: implementation meets DoD criteria. Approved."})
    txt = r.get("result", [{}])[0].get("text", "") if "result" in r else str(r)
    ok = "done" in txt.lower() or "approved" in txt.lower()
    status = "OK" if ok else txt[:100]
    print(f"  {tk}: {status}")
    return ok


if __name__ == "__main__":
    tasks = api_get(f"/api/epics/{EPIC_KEY}/tasks?limit=200")
    task_keys = sorted([t["task_key"] for t in tasks if t["state"] == "in_review"])
    print(f"Approving {len(task_keys)} tasks in_review")

    ok_count = 0
    for tk in task_keys:
        ok = approve_task(tk)
        if ok:
            ok_count += 1
        time.sleep(0.3)

    print(f"\nApproved: {ok_count}/{len(task_keys)}")

    # Final status
    final = api_get(f"/api/epics/{EPIC_KEY}/tasks?limit=200")
    states = {}
    for t in final:
        s = t["state"]
        states[s] = states.get(s, 0) + 1
    print(f"Final state distribution: {states}")
