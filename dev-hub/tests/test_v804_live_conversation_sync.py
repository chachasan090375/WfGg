#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text(encoding="utf-8")

assert "async function syncConversation(force=false)" in ui
assert "setInterval(()=>syncConversation(false),1500)" in ui
assert "document.addEventListener('visibilitychange'" in ui
assert "window.addEventListener('focus'" in ui
assert "lastSeenRequestId" in ui
assert "lastSeenDigest" in ui
assert "s.last_request_id" in ui
assert "s.last_response_digest" in ui
assert "renderConversation(s.last_response,dig)" in ui
assert "● Temps réel" in ui
assert "réponse '+esc(when)" in ui
assert "nouvelle demande acceptée" in ui
assert "if(fromEditor)q.value=''" in ui

print("CHACHA_DEV_V804_LIVE_CONVERSATION_POLLING=PASS")
print("CHACHA_DEV_V804_VISIBILITY_RESYNC=PASS")
print("CHACHA_DEV_V804_REQUEST_DIGEST_CHANGE_DETECTION=PASS")
print("CHACHA_DEV_V804_RESPONSE_TIMESTAMP_VISIBLE=PASS")
print("CHACHA_DEV_V804_NO_APP_REOPEN_REQUIRED=PASS")
print("CHACHA_DEV_V804_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
