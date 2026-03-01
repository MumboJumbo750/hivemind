"""Quick API helper script for Hivemind."""
import urllib.request
import json
import sys

BASE = "http://localhost:8000"

def api_get(path):
    url = f"{BASE}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def api_post(path, data):
    url = f"{BASE}{path}"
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": str(e), "body": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}

def api_patch(path, data):
    url = f"{BASE}{path}"
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="PATCH")
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": str(e), "body": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}

def mcp_call(tool_name, args):
    """Call an MCP tool via the convenience REST endpoint."""
    return api_post("/api/mcp/call", {"tool": tool_name, "arguments": args})

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tasks"
    
    if cmd == "tasks":
        result = api_get("/api/epics/EPIC-PHASE-5/tasks")
        if isinstance(result, list):
            for t in result:
                print(f"{t.get('task_key', '?'):15s} | {t.get('state', '?'):12s} | {t.get('title', '?')}")
        else:
            print(json.dumps(result, indent=2))
    
    elif cmd == "skills":
        skills = api_get("/api/skills?limit=50")
        if isinstance(skills, list):
            for s in skills:
                print(f"{s.get('id', '?')[:8]}... | {s.get('lifecycle', '?'):12s} | {s.get('title', '?')}")
        else:
            print(json.dumps(skills, indent=2))
    
    elif cmd == "mcp-tools":
        result = api_get("/api/mcp/tools")
        if isinstance(result, list):
            for t in result:
                print(f"  {t.get('name', '?')}")
        else:
            print(json.dumps(result, indent=2))
    
    elif cmd == "mcp":
        tool = sys.argv[2]
        args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        result = mcp_call(tool, args)
        print(json.dumps(result, indent=2))
    
    elif cmd == "task":
        key = sys.argv[2]
        result = api_get(f"/api/tasks/{key}")
        print(json.dumps(result, indent=2))
    
    else:
        print(f"Unknown command: {cmd}")
