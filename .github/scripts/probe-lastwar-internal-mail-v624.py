#!/usr/bin/env python3
"""
V6.24 Internal Mail Protocol Discovery — static-only probe.

This script NEVER opens a Last War connection and NEVER emits mail.send.
It only inspects a local checkout of the pinned public lastwar-client
reference and produces aggregate protocol evidence.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

root = Path(os.environ.get("LASTWAR_CLIENT_ROOT", "/tmp/lastwar-client")).resolve()
if not root.is_dir():
    raise SystemExit(f"V624_LASTWAR_CLIENT_ROOT_MISSING={root}")

doc = root / "docs" / "alliance-chat-mail.mdx"
auth = root / "docs" / "auth.mdx"
if not doc.is_file() or not auth.is_file():
    raise SystemExit("V624_REQUIRED_UPSTREAM_DOCS_MISSING")

doc_text = doc.read_text(encoding="utf-8", errors="replace")
auth_text = auth.read_text(encoding="utf-8", errors="replace")

command_proven = "`mail.send` | Send mail (1:1 or alliance-wide)" in doc_text
chat_separate = "Real-time message text never touches the main game socket" in doc_text
sfs_mail = "Core Mail commands" in doc_text and command_proven

# Look for an authoritative request-construction source if the upstream
# repository ever starts shipping one. Do not infer field names from prose.
source_hits = []
schema_hits = []
allowed_ext = {".go", ".lua", ".md", ".mdx", ".json", ".txt"}
for p in root.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in allowed_ext:
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        continue
    if "mail.send" not in text:
        continue
    rel = str(p.relative_to(root))
    source_hits.append(rel)
    # Schema is considered proven only from implementation-like source that
    # contains mail.send plus explicit request construction/OnCreate behavior.
    implementation_like = p.suffix.lower() in {".go", ".lua"}
    if implementation_like and (
        re.search(r"OnCreate\s*\(", text)
        or re.search(r"Put(?:UtfString|Int|Long|Bool|Double)\s*\(", text)
        or re.search(r"mail\.send.{0,1500}(?:SFSObject|params|PutUtfString)", text, re.S | re.I)
    ):
        schema_hits.append(rel)

schema_status = "PROVEN_SOURCE_PRESENT" if schema_hits else "UNRESOLVED"
report = {
    "version": "V6.24",
    "mode": "STATIC_ONLY",
    "lastwarMutation": False,
    "gameScanExecuted": False,
    "command": "mail.send" if command_proven else None,
    "transport": "SFS" if sfs_mail else None,
    "scope": "1:1_OR_ALLIANCE_WIDE" if command_proven else None,
    "chatWebSocketSeparate": bool(chat_separate),
    "schemaStatus": schema_status,
    "sourceHits": sorted(source_hits),
    "schemaSourceHits": sorted(schema_hits),
}
out = Path(os.environ.get("V624_REPORT", "/tmp/v624-mail-protocol.json"))
out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print("WFGG_RADAR_DISCOVERY=V6.24")
print("DISCOVERY_MODE=STATIC_ONLY")
print("LASTWAR_MUTATION=NO")
print("GAME_SCAN_EXECUTED=NO")
print("MAIL_SEND_COMMAND=" + ("mail.send" if command_proven else "NOT_PROVEN"))
print("MAIL_SEND_TRANSPORT=" + ("SFS" if sfs_mail else "UNRESOLVED"))
print("MAIL_SEND_SCOPE=" + ("1_TO_1_OR_ALLIANCE_WIDE" if command_proven else "UNRESOLVED"))
print("CHAT_WEBSOCKET_SEPARATE=" + ("YES" if chat_separate else "UNRESOLVED"))
print("MAIL_SEND_SCHEMA_STATUS=" + schema_status)
print("MAIL_SEND_SOURCE_HITS=" + str(len(source_hits)))
print("MAIL_SEND_SCHEMA_SOURCE_HITS=" + str(len(schema_hits)))
print("REPORT=" + str(out))

if not command_proven:
    raise SystemExit("V624_MAIL_SEND_COMMAND_NOT_PROVEN")
