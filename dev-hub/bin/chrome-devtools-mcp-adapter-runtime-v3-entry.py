#!/usr/bin/env python3
"""Thin Chrome DevTools MCP adapter V3 entry.

Preserves the qualified V2 adapter policy and toolset. It only adds a bounded
startup retry for the first list_pages observation because real external preview
navigation can race browser target discovery. No new MCP tool is exposed.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "adapters" / "chrome-devtools-mcp-adapter.py"
spec = importlib.util.spec_from_file_location("chacha_chrome_adapter_v2", BASE)
if spec is None or spec.loader is None:
    raise SystemExit("CHROME_ADAPTER_IMPORT_FAILED")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_original_request = mod.MCPClient.request


def _request_with_page_discovery_retry(self, req_id, method, params=None):
    msg = _original_request(self, req_id, method, params)
    if method != "tools/call" or not isinstance(params, dict) or params.get("name") != "list_pages":
        return msg
    text = mod.result_text(msg)
    if mod.selected_page_id(text) is not None:
        return msg
    for attempt in range(1, 6):
        time.sleep(1)
        retry_id = f"{req_id}-page-retry-{attempt}"
        msg = _original_request(self, retry_id, method, params)
        text = mod.result_text(msg)
        if mod.selected_page_id(text) is not None:
            return msg
    return msg


mod.MCPClient.request = _request_with_page_discovery_retry
raise SystemExit(mod.main())
