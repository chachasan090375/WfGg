#!/usr/bin/env python3
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone

URL = "https://mcp.context7.com/mcp"
VER = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": VER,
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "chacha-dev-hub-ci", "version": "1.0"},
}


def parse_body(raw: bytes, ctype: str):
    text = raw.decode("utf-8", "replace")
    if "text/event-stream" in (ctype or "") or text.lstrip().startswith(("event:", "data:")):
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload and payload != "[DONE]":
                    try:
                        return json.loads(payload)
                    except json.JSONDecodeError:
                        pass
        raise ValueError("no JSON SSE data frame")
    return json.loads(text)


def call(method: str, params=None, name=None, ident=1):
    body = {"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}}
    body["params"]["_meta"] = META
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": VER,
        "Mcp-Method": method,
        "User-Agent": "ChaCha-DEV-HUB/1.0",
    }
    if name:
        headers["Mcp-Name"] = name
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read(2_000_000)
            ctype = response.headers.get("content-type", "")
            return {"http_status": response.status, "content_type": ctype, "json": parse_body(raw, ctype)}
    except urllib.error.HTTPError as exc:
        raw = exc.read(200_000)
        return {
            "http_status": exc.code,
            "content_type": exc.headers.get("content-type", ""),
            "error_body": raw.decode("utf-8", "replace"),
        }
    except Exception as exc:
        return {"http_status": 0, "transport_error": f"{type(exc).__name__}: {exc}"}


def ok_rpc(result):
    return result.get("http_status") == 200 and isinstance(result.get("json"), dict) and not result["json"].get("error")


out = {
    "schema": "chacha.dev/context7-direct-mcp-probe/v1",
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "endpoint": URL,
    "protocol_version": VER,
    "anonymous": True,
    "credentials_used": False,
    "checks": {},
    "promotion": {"automatic": False, "eligible_for_pilot": False, "blockers": []},
}

# Modern MCP discovery.
discover = call("server/discover", ident=1)
out["checks"]["server_discover"] = discover
if not ok_rpc(discover):
    out["promotion"]["blockers"].append("server-discover-failed")

# Tool catalog and read-only annotations.
tools_result = call("tools/list", ident=2)
out["checks"]["tools_list"] = tools_result
expected = {"resolve-library-id", "query-docs"}
toolmap = {}
if ok_rpc(tools_result):
    tools = ((tools_result["json"].get("result") or {}).get("tools") or [])
    toolmap = {item.get("name"): item for item in tools if isinstance(item, dict)}
    missing = sorted(expected - set(toolmap))
    if missing:
        out["promotion"]["blockers"].append("tools-missing:" + ",".join(missing))
    for tool_name in expected & set(toolmap):
        annotations = toolmap[tool_name].get("annotations") or {}
        if annotations.get("readOnlyHint") is not True or annotations.get("destructiveHint") is not False:
            out["promotion"]["blockers"].append("unsafe-annotations:" + tool_name)
else:
    out["promotion"]["blockers"].append("tools-list-failed")

# Real read-only tool call #1.
resolve = call(
    "tools/call",
    {
        "name": "resolve-library-id",
        "arguments": {
            "libraryName": "Context7",
            "query": "Resolve the official Context7 library for DEV HUB MCP qualification.",
        },
    },
    name="resolve-library-id",
    ident=3,
)
out["checks"]["resolve_library_id"] = resolve
if not ok_rpc(resolve):
    out["promotion"]["blockers"].append("resolve-library-id-failed")
elif "/upstash/context7" not in json.dumps(resolve["json"], ensure_ascii=False):
    out["promotion"]["blockers"].append("resolve-library-id-unexpected-result")

# Real read-only tool call #2.
query = call(
    "tools/call",
    {
        "name": "query-docs",
        "arguments": {
            "libraryId": "/upstash/context7",
            "query": "List the current Context7 MCP tool names and their read-only annotations.",
        },
    },
    name="query-docs",
    ident=4,
)
out["checks"]["query_docs"] = query
if not ok_rpc(query):
    out["promotion"]["blockers"].append("query-docs-failed")

out["promotion"]["eligible_for_pilot"] = not out["promotion"]["blockers"]
path = os.environ.get("EVIDENCE_PATH", "context7-direct-mcp-probe.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)

print(json.dumps(out["promotion"], indent=2))
sys.exit(0 if out["promotion"]["eligible_for_pilot"] else 2)
