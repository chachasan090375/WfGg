#!/usr/bin/env python3
import json
import urllib.error
import urllib.request

SERVERS = {
    "MDN": (
        "https://mcp.mdn.mozilla.net/",
        {"X-Moz-1st-Party-Data-Opt-Out": "1"},
    ),
    "CONTEXT7": (
        "https://mcp.context7.com/mcp",
        {},
    ),
}


def call(url, payload, headers_extra=None, timeout=30):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if headers_extra:
        headers.update(headers_extra)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode(errors="replace")
    except Exception as exc:
        return 0, {}, str(exc)


def decode(body):
    try:
        return [json.loads(body)]
    except Exception:
        pass
    result = []
    for line in body.splitlines():
        if line.startswith("data:"):
            try:
                result.append(json.loads(line[5:].strip()))
            except Exception:
                pass
    return result


def probe(name, url, extra):
    print()
    print(f"=== {name} ===")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "chacha-dev-hub", "version": "1.0"},
        },
    }
    code, headers, body = call(url, payload, extra)
    print(f"{name}_HTTP={code}")
    objects = decode(body)
    answer = next((obj for obj in objects if isinstance(obj, dict) and obj.get("id") == 1), None)
    if not answer:
        print(f"{name}_INITIALIZE=FAILED")
        return False
    if "error" in answer:
        print(f"{name}_INITIALIZE=ERROR")
        print(json.dumps(answer["error"], ensure_ascii=False))
        return False

    print(f"{name}_INITIALIZE=OK")
    protocol = answer.get("result", {}).get("protocolVersion", "2025-06-18")
    session = next((value for key, value in headers.items() if key.lower() == "mcp-session-id"), None)
    common = dict(extra)
    common["MCP-Protocol-Version"] = protocol
    if session:
        common["Mcp-Session-Id"] = session

    call(
        url,
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        common,
    )
    code, _, body = call(
        url,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        common,
    )
    print(f"{name}_TOOLS_HTTP={code}")
    objects = decode(body)
    answer = next((obj for obj in objects if isinstance(obj, dict) and obj.get("id") == 2), None)
    if not answer or "error" in answer:
        print(f"{name}_TOOLS=FAILED")
        return False

    tools = answer.get("result", {}).get("tools", [])
    print(f"{name}_TOOLS=OK")
    print(f"{name}_TOOL_COUNT={len(tools)}")
    for tool in tools:
        print(f"{name}_TOOL={tool.get('name', '?')}")
    return True


def main():
    ok = True
    for name, (url, extra) in SERVERS.items():
        ok = probe(name, url, extra) and ok
    print()
    print("MCP_TRANSPORT=OK" if ok else "MCP_TRANSPORT=FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
