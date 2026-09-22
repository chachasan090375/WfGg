#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/opt/wfgg-radar"
BIN="$ROOT/messenger/bin/wfgg-messenger-outbox"
DATA="$ROOT/data/messenger"
EXPECTED="${WFGG_V624_MESSENGER_SHA256:-}"

fail(){ printf 'RADAR_V624_MESSENGER_PRODUCTION_PROBE=FAIL reason=%s\n' "$1"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
[[ -x "$BIN" ]] || fail BINARY_MISSING
[[ "$EXPECTED" =~ ^[0-9a-f]{64}$ ]] || fail EXPECTED_SHA_INVALID
ACTUAL="$(sha256sum "$BIN" | awk '{print $1}')"
[[ "$ACTUAL" == "$EXPECTED" ]] || fail SHA_MISMATCH

if grep -aEq 'RADAR_CONNECTOR_SHARED_KEY|LASTWAR_NATIVE_TEMPLATE|/v1/scan/player|/v1/authenticate|SendExtension' "$BIN"; then
  fail LASTWAR_NETWORK_CAPABILITY_MARKER
fi

install -d -m 0750 "$DATA"
LEDGER="$DATA/probe-$(date -u +%Y%m%dT%H%M%SZ).jsonl"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat >"$TMP/draft.json" <<'JSON'
{"targetName":"ProductionProbe","targetUid":"6240000000000030","title":"V6.24 Probe","contents":"Dry-run production probe","sendLocalTime":1700000000,"senderServer":8120,"targetServer":8120}
JSON

"$BIN" -ledger "$LEDGER" create <"$TMP/draft.json" >"$TMP/create.json"
ID="$(python3 - "$TMP/create.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d['record']['state']=='DRAFT'
assert d['record']['dryRun']['command']=='mail.send'
assert d['record']['dryRun']['mailType']==21
assert d['record']['dryRun']['networkEnabled'] is False
assert d['record']['dryRun']['mutationExecuted'] is False
print(d['record']['id'])
PY
)"
"$BIN" -ledger "$LEDGER" queue "$ID" >"$TMP/queue.json"
"$BIN" -ledger "$LEDGER" history "$ID" >"$TMP/history.json"
python3 - "$TMP/queue.json" "$TMP/history.json" <<'PY'
import json,sys
q=json.load(open(sys.argv[1])); h=json.load(open(sys.argv[2]))
assert q['state']=='QUEUED'
assert [x['state'] for x in h]==['DRAFT','QUEUED']
print('RADAR_V624_MESSENGER_PRODUCTION_DRAFT_QUEUE_HISTORY=PASS')
PY

cat >"$TMP/cross.json" <<'JSON'
{"targetName":"CrossServer","targetUid":"6240000000000031","title":"X","contents":"X","sendLocalTime":1700000000,"senderServer":8120,"targetServer":8131}
JSON
if "$BIN" -ledger "$LEDGER" create <"$TMP/cross.json" >"$TMP/cross.out" 2>"$TMP/cross.err"; then
  fail CROSS_SERVER_GUARD
fi
grep -Fq 'cross-server private mail is not proven' "$TMP/cross.err" || fail CROSS_SERVER_GUARD_MESSAGE

echo "RADAR_V624_MESSENGER_PRODUCTION_SHA256=$ACTUAL"
echo "RADAR_V624_MESSENGER_PRODUCTION_PATH=$BIN"
echo "RADAR_V624_MESSENGER_PRODUCTION_PROBE_LEDGER=$LEDGER"
echo "RADAR_V624_GAME_CONNECTION=NONE"
echo "RADAR_V624_GAME_SCAN_EXECUTED=NO"
echo "RADAR_V624_MAIL_SEND_EXECUTED=NO"
echo "RADAR_V624_LASTWAR_MUTATION=NO"
echo "RADAR_V624_PRODUCTION_CONNECTOR_TOUCHED=NO"
echo "RADAR_V624_MESSENGER_PRODUCTION_PROBE=PASS"
