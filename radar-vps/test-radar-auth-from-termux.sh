#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

SESSION="$HOME/.wfgg-lastwar-probe/home/.lastwar_goclient_session.json"
RADAR_URL="https://wfgg-radar.chachasan090375.workers.dev"
PY="$(command -v python3 || command -v python || true)"

[[ -n "$PY" ]] || { echo 'ERROR=PYTHON_MISSING'; exit 2; }
[[ -s "$SESSION" ]] || { echo 'ERROR=SESSION_MISSING'; exit 2; }

"$PY" - "$SESSION" "$RADAR_URL" <<'PY'
import json, sys, urllib.request, urllib.error
session_path, base = sys.argv[1], sys.argv[2].rstrip('/')
with open(session_path, encoding='utf-8') as f:
    token = json.load(f).get('accessToken')
if not token:
    raise SystemExit('ERROR=ACCESS_TOKEN_MISSING')
req = urllib.request.Request(
    base + '/api/auth/game-token',
    data=json.dumps({'token': token}).encode(),
    method='POST',
    headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36',
    },
)
try:
    with urllib.request.urlopen(req, timeout=75) as r:
        raw = r.read().decode('utf-8', 'replace')
        code = r.status
except urllib.error.HTTPError as e:
    raw = e.read().decode('utf-8', 'replace')
    code = e.code
print('HTTP=' + str(code))
try:
    data = json.loads(raw)
except Exception:
    print('RADAR_JSON=NO')
    print('BODY=' + raw[:220].replace('\n',' '))
    raise SystemExit(1)
print('RADAR_JSON=YES')
if data.get('ok') is True:
    print('RADAR_AUTH=OK')
    user = data.get('user') or {}
    print('PSEUDO_OBSERVED=' + ('YES' if user.get('pseudo') else 'NO'))
    print('ROLE=' + str(user.get('role','')))
else:
    print('RADAR_AUTH=FAILED')
    print('ERROR=' + str(data.get('error','UNKNOWN')))
PY
