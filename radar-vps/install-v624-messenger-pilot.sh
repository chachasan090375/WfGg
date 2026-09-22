#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_RADAR_V624_REV:-radar-v624-internal-mail-protocol-discovery}"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}/radar-vps/pilot-v624-messenger"
ROOT="/opt/wfgg-messenger-pilot"
BIN="${ROOT}/bin"
DATA="${ROOT}/data"
TMP_ROOT="/opt/chacha-dev/runtime/tmp"
mkdir -p "$TMP_ROOT"
TMP="$(mktemp -d "$TMP_ROOT/wfgg-messenger-v624.XXXXXX")"

log(){ printf '%s\n' "$*"; }
fail(){ log "RADAR_V624_MESSENGER_PILOT_INSTALL=FAIL reason=$*"; exit 1; }
cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
for c in curl sha256sum install mktemp grep awk python3; do
  command -v "$c" >/dev/null 2>&1 || fail "COMMAND_MISSING:$c"
done

log "=== WFGG RADAR V6.24 MESSENGER OUTBOX ISOLATED PILOT ==="
log "RADAR_V624_REV=$REV"
log "RADAR_V624_PILOT_ROOT=$ROOT"

for f in SHA256SUMS PILOT_INFO.txt wfgg-messenger-outbox; do
  curl --fail --silent --show-error --location --max-time 90 "$BASE/$f" -o "$TMP/$f" || fail "DOWNLOAD:$f"
done
(cd "$TMP" && sha256sum -c SHA256SUMS) >/dev/null || fail CHECKSUM

grep -Fq 'WFGG_RADAR_PILOT=V6.24-MESSENGER-OUTBOX' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_VERSION
grep -Fq 'MESSENGER_MODE=DRY_RUN_ONLY' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_MODE
grep -Fq 'NETWORK_SEND=NO' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_NETWORK
grep -Fq 'LASTWAR_MUTATION=NO' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_MUTATION
grep -Fq 'PRODUCTION_CONNECTOR_RESTART=NO' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_CONNECTOR

install -d -m 0750 "$BIN" "$DATA"
install -m 0755 "$TMP/wfgg-messenger-outbox" "$BIN/wfgg-messenger-outbox"
EXPECTED="$(awk '$2=="wfgg-messenger-outbox"{print $1}' "$TMP/SHA256SUMS" | head -1)"
ACTUAL="$(sha256sum "$BIN/wfgg-messenger-outbox" | awk '{print $1}')"
[[ -n "$EXPECTED" && "$ACTUAL" == "$EXPECTED" ]] || fail POST_INSTALL_SHA

PILOT_LEDGER="$DATA/outbox-pilot.jsonl"
rm -f "$PILOT_LEDGER"
cat > "$TMP/draft.json" <<'JSON'
{"targetName":"V624Pilot","targetUid":"6240000000000001","title":"WfGg V6.24","contents":"Pilot dry-run local uniquement","sendLocalTime":1700000000,"senderServer":8120,"targetServer":8120}
JSON
"$BIN/wfgg-messenger-outbox" -ledger "$PILOT_LEDGER" create < "$TMP/draft.json" > "$TMP/create.json"
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
[[ "$ID" =~ ^[a-f0-9]{24}$ ]] || fail PILOT_ID
"$BIN/wfgg-messenger-outbox" -ledger "$PILOT_LEDGER" queue "$ID" > "$TMP/queue.json"
"$BIN/wfgg-messenger-outbox" -ledger "$PILOT_LEDGER" history "$ID" > "$TMP/history.json"
python3 - "$TMP/queue.json" "$TMP/history.json" <<'PY'
import json,sys
q=json.load(open(sys.argv[1]))
h=json.load(open(sys.argv[2]))
assert q['state']=='QUEUED'
assert [x['state'] for x in h]==['DRAFT','QUEUED']
print('RADAR_V624_PILOT_DRAFT_QUEUE_HISTORY=PASS')
PY

cat > "$TMP/cross.json" <<'JSON'
{"targetName":"CrossServer","targetUid":"6240000000000002","title":"X","contents":"X","sendLocalTime":1700000000,"senderServer":8120,"targetServer":8131}
JSON
if "$BIN/wfgg-messenger-outbox" -ledger "$PILOT_LEDGER" create < "$TMP/cross.json" > "$TMP/cross.out" 2> "$TMP/cross.err"; then
  fail CROSS_SERVER_GUARD
fi
grep -Fq 'cross-server private mail is not proven' "$TMP/cross.err" || fail CROSS_SERVER_ERROR
log "RADAR_V624_PILOT_CROSS_SERVER_GUARD=PASS"

log "RADAR_V624_MESSENGER_SHA=$ACTUAL"
log "RADAR_V624_PILOT_LEDGER=$PILOT_LEDGER"
log "RADAR_V624_GAME_CONNECTION=NONE"
log "RADAR_V624_GAME_SCAN_EXECUTED=NO"
log "RADAR_V624_LASTWAR_MUTATION=NO"
log "RADAR_V624_NETWORK_SEND=NO"
log "RADAR_V624_PRODUCTION_CONNECTOR_RESTART=NO"
log "RADAR_V624_MESSENGER_PILOT_INSTALL=PASS"
