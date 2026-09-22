#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/opt/wfgg-messenger-pilot"
BIN="$ROOT/bin/wfgg-messenger-outbox"
DATA="$ROOT/data"
EXPECTED="${WFGG_V624_MESSENGER_SHA256:-}"

fail(){ printf 'RADAR_V624_MESSENGER_RUNTIME_PROBE=FAIL reason=%s\n' "$1"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
[[ -x "$BIN" ]] || fail BINARY_MISSING
command -v python3 >/dev/null 2>&1 || fail PYTHON3_MISSING

ACTUAL="$(sha256sum "$BIN" | awk '{print $1}')"
echo "RADAR_V624_MESSENGER_SHA=$ACTUAL"
if [[ -n "$EXPECTED" && "$ACTUAL" != "$EXPECTED" ]]; then
  fail SHA_MISMATCH
fi

# Static guard: this binary is only the local Outbox CLI.
if grep -aEq 'RADAR_CONNECTOR_SHARED_KEY|LASTWAR_NATIVE_TEMPLATE|/v1/scan/player|/v1/authenticate' "$BIN"; then
  fail GAME_CONNECTOR_MARKER_PRESENT
fi

LEDGER="$DATA/probe-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/draft.json" <<'JSON'
{"targetName":"RuntimeProbe","targetUid":"6240000000000003","title":"Probe","contents":"V6.24 dry-run","sendLocalTime":1700000000,"senderServer":8120,"targetServer":8120}
JSON
"$BIN" -ledger "$LEDGER" create < "$TMP/draft.json" > "$TMP/create.json"
ID="$(python3 - "$TMP/create.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['record']['state']=='DRAFT'
assert d['record']['dryRun']['networkEnabled'] is False
assert d['record']['dryRun']['mutationExecuted'] is False
print(d['record']['id'])
PY
)"
"$BIN" -ledger "$LEDGER" queue "$ID" > "$TMP/queue.json"
"$BIN" -ledger "$LEDGER" history "$ID" > "$TMP/history.json"
python3 - "$TMP/queue.json" "$TMP/history.json" <<'PY'
import json,sys
q=json.load(open(sys.argv[1])); h=json.load(open(sys.argv[2]))
assert q['state']=='QUEUED'
assert [x['state'] for x in h]==['DRAFT','QUEUED']
print('RADAR_V624_RUNTIME_DRAFT_QUEUE_HISTORY=PASS')
PY

echo "RADAR_V624_RUNTIME_ROOT=$ROOT"
echo "RADAR_V624_RUNTIME_LEDGER=$LEDGER"
echo "RADAR_V624_RUNTIME_GAME_CONNECTION=NONE"
echo "RADAR_V624_RUNTIME_GAME_SCAN_EXECUTED=NO"
echo "RADAR_V624_RUNTIME_LASTWAR_MUTATION=NO"
echo "RADAR_V624_RUNTIME_NETWORK_SEND=NO"
echo "RADAR_V624_RUNTIME_PRODUCTION_CONNECTOR_TOUCHED=NO"
echo "RADAR_V624_MESSENGER_RUNTIME_PROBE=PASS"
