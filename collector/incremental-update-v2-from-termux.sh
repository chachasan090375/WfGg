#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

TRIGGER="${1:-MANUAL}"
QUERY="${2:-}"
REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/collector-v1/collector"

for c in curl python3 ssh; do command -v "$c" >/dev/null 2>&1 || { echo "ERROR=${c}_MISSING"; exit 2; }; done

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  echo 'SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || { echo 'ERROR=VPS_UNREACHABLE'; exit 2; }
  echo 'SSH_ROUTE=PUBLIC_IPV4'
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
REGION_SCRIPT="$TMP/test-region-native-from-termux.sh"
curl -fsSL "$RAW/test-region-native-from-termux.sh" -o "$REGION_SCRIPT"
chmod 0755 "$REGION_SCRIPT"

post_json(){
  local path="$1" body="$2"
  printf '%s' "$body" | ssh "${SSH_OPTS[@]}" -T "$REMOTE" curl -fsS -X POST -H 'Content-Type: application/json' --data-binary @- "http://127.0.0.1:8790$path"
}

get_json(){
  local path="$1"
  ssh "${SSH_OPTS[@]}" -T "$REMOTE" curl -fsS "http://127.0.0.1:8790$path" </dev/null
}

START_BODY="$(python3 - "$TRIGGER" "$QUERY" <<'PY'
import json,sys
print(json.dumps({'trigger':sys.argv[1],'query':sys.argv[2]},separators=(',',':')),end='')
PY
)"
START_JSON="$(post_json '/cycle/start' "$START_BODY")"
readarray -t META < <(python3 - "$START_JSON" <<'PY'
import json,sys
x=json.loads(sys.argv[1]); c=x['cycle']
print(c['id']); print('YES' if x.get('joined') else 'NO'); print(c['status'])
PY
)
CYCLE_ID="${META[0]}"
JOINED="${META[1]}"
STATUS="${META[2]}"
echo "COLLECTOR_CYCLE_ID=$CYCLE_ID"
echo "COLLECTOR_CYCLE_JOINED=$JOINED"

if [[ "$JOINED" == YES ]]; then
  for _ in $(seq 1 120); do
    CUR="$(get_json "/cycle/status?id=$CYCLE_ID")"
    STATUS="$(python3 - "$CUR" <<'PY'
import json,sys
print(json.loads(sys.argv[1])['cycle']['status'])
PY
)"
    [[ "$STATUS" != RUNNING ]] && break
    sleep 2
  done
  [[ "$STATUS" == SUCCESS ]] || { echo "ERROR=CYCLE_$STATUS"; exit 3; }
  echo 'COLLECTOR_INCREMENT=JOINED_SUCCESS'
  exit 0
fi

FAIL=0
for REGION in 0 1 2 3 4 5 6 7 8; do
  echo "COLLECTOR_REGION_START=$REGION"
  OUT="$(bash "$REGION_SCRIPT" "$REGION" "$CYCLE_ID" 2>&1 || true)"
  printf '%s\n' "$OUT" | grep -E '^(COLLECTOR_REGION|NATIVE_RC|NATIVE_JSON|NATIVE_PLAYERS|COLLECTOR_CACHE_ACCEPTED|COLLECTOR_CACHE_CHANGED|COLLECTOR_TOTAL_PLAYERS)=' || true
  RC="$(printf '%s\n' "$OUT" | sed -n 's/^NATIVE_RC=//p' | tail -n1)"
  JS="$(printf '%s\n' "$OUT" | sed -n 's/^NATIVE_JSON=//p' | tail -n1)"
  [[ "$RC" == 0 && "$JS" == YES ]] || FAIL=1
done

if [[ "$FAIL" -eq 0 ]]; then
  FIN_BODY="$(printf '{\"cycleId\":%s,\"status\":\"SUCCESS\"}' "$CYCLE_ID")"
else
  FIN_BODY="$(printf '{\"cycleId\":%s,\"status\":\"FAILED\",\"error\":\"REGION_SCAN_FAILED\"}' "$CYCLE_ID")"
fi
FIN_JSON="$(post_json '/cycle/finish' "$FIN_BODY")"
python3 - "$FIN_JSON" <<'PY'
import json,sys
c=json.loads(sys.argv[1])['cycle']
for k in ('id','status','players_seen','new_players','changed_players','unchanged_players','missing_players','enriched_players','started_at','finished_at'):
    print('COLLECTOR_CYCLE_'+k.upper()+'='+str(c.get(k,'')))
PY

[[ "$FAIL" -eq 0 ]] || exit 3
