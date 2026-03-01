"""Batch MCP call helper — reads commands from a JSON file and executes them."""
import json
import urllib.request

BASE = "http://localhost:8000"

def api_post(path, data):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": str(e), "body": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}

def mcp_call(tool_name, args):
    return api_post("/api/mcp/call", {"tool": tool_name, "arguments": args})

# Read commands from _mcp_batch.json
with open("_mcp_batch.json", "r") as f:
    commands = json.load(f)

results = []
for cmd in commands:
    tool = cmd["tool"]
    args = cmd.get("args", {})
    print(f">>> {tool}")
    result = mcp_call(tool, args)
    results.append({"tool": tool, "result": result})
    print(json.dumps(result, indent=2, default=str))
    print()

with open("_mcp_output.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"Done. {len(results)} calls. Output in _mcp_output.json")
