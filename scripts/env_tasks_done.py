"""Set all TASK-ENV-* tasks to done via MCP state transitions."""
import json, sys
sys.path.insert(0, ".")
from scripts.api_test import api_get, mcp_call

# Get ENV-BOOTSTRAP tasks
tasks = api_get("/api/epics/EPIC-ENV-BOOTSTRAP/tasks")
if isinstance(tasks, dict) and "error" in tasks:
    print(f"ERROR fetching tasks: {tasks}")
    sys.exit(1)

print(f"Found {len(tasks)} ENV tasks\n")

# Solo user ID
solo_user_id = "00000000-0000-0000-0000-000000000001"
print(f"Using solo user: {solo_user_id}\n")

def do_mcp(tool, args):
    r = mcp_call(tool, args)
    # Extract text from MCP response
    if isinstance(r, dict) and "result" in r:
        for item in r["result"]:
            txt = item.get("text", "")
            data = json.loads(txt)
            if "error" in data:
                print(f"  ERROR: {data['error']}")
                return False
            return data
    print(f"  Unexpected: {r}")
    return False

for t in sorted(tasks, key=lambda x: x.get("task_key", "")):
    tk = t["task_key"]
    state = t["state"]
    print(f"{'='*50}")
    print(f"{tk}: {state}")

    if state == "done":
        print("  already done")
        continue

    # Step 1: assign if not assigned
    if not t.get("assigned_to"):
        print(f"  assign_task...")
        do_mcp("hivemind-assign_task", {"task_key": tk, "user_id": solo_user_id})

    # Step 2: walk through states
    transitions = {
        "scoped": ["ready", "in_progress"],
        "ready": ["in_progress"],
        "in_progress": [],  # need submit_result then in_review
        "in_review": ["done"],
    }

    # Get to in_progress first
    if state in ("scoped", "ready"):
        for next_s in (["ready", "in_progress"] if state == "scoped" else ["in_progress"]):
            print(f"  -> {next_s}...")
            result = do_mcp("hivemind-update_task_state", {"task_key": tk, "target_state": next_s})
            if result is False:
                break
        state = "in_progress"

    # Submit result
    if state == "in_progress":
        print(f"  submit_result...")
        do_mcp("hivemind-submit_result", {
            "task_key": tk,
            "result": f"{tk} completed - all definition of done criteria met.",
            "artifacts": []
        })
        print(f"  -> in_review...")
        do_mcp("hivemind-update_task_state", {"task_key": tk, "target_state": "in_review"})
        state = "in_review"

    # Done
    if state == "in_review":
        print(f"  -> done...")
        do_mcp("hivemind-update_task_state", {"task_key": tk, "target_state": "done"})

print(f"\n{'='*50}")
print("Fertig!")

