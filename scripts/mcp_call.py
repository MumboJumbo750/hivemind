"""Helper to call MCP tools and save output to file."""
import json
import sys
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

if __name__ == "__main__":
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    result = mcp_call(tool, args)
    output = json.dumps(result, indent=2, default=str)
    
    # Write to file for reliable reading
    with open("_mcp_output.json", "w") as f:
        f.write(output)
    
    print(output)
