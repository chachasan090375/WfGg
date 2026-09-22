#!/usr/bin/env bash
set -Eeuo pipefail
REV="${CHACHA_DEV_V67_INGRESS_REV:-}"
PORT="${CHACHA_DEV_LEARNING_INGRESS_PORT:-8791}"
BASE="/opt/chacha-dev/learning-ingress"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-learning-ingress.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
KEYS="/opt/chacha-dev/runtime/secrets/learning-ingress-keys.json"

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V67_INGRESS_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V67_INGRESS_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl tar python3 install ln systemctl; do command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V67_INGRESS_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }; done

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V67_INGRESS_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/secrets /opt/chacha-dev/runtime/knowledge /opt/chacha-dev/runtime/learning/anomaly-queue
install -m 0755 "$SRC/dev-hub/bin/central-learning-ingress.py" "$RELEASE/central-learning-ingress.py"
install -m 0755 "$SRC/dev-hub/bin/learning-delta-ingest.py" "$RELEASE/learning-delta-ingest.py"
python3 -m py_compile "$RELEASE/central-learning-ingress.py" "$RELEASE/learning-delta-ingest.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"
ln -sfn "$RELEASE" "$CURRENT"

if [ ! -s "$KEYS" ]; then
  SECRET="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
  python3 - "$KEYS" "$SECRET" <<'PY'
import json,os,sys
p,secret=sys.argv[1:]
x={
 "schema":"chacha.dev/learning-ingress-keys/v1",
 "version":"1.0.0",
 "keys":{
   "bootstrap-local":{
     "status":"ACTIVE",
     "secret":secret,
     "project_ids":[],
     "deployment_ids":[],
     "created_for":"initial-platform-pilot"
   }
 }
}
open(p,"w",encoding="utf-8").write(json.dumps(x,indent=2)+"\n")
os.chmod(p,0o600)
PY
  echo "CHACHA_DEV_V67_INGRESS_BOOTSTRAP_KEY_CREATED=YES"
else
  echo "CHACHA_DEV_V67_INGRESS_BOOTSTRAP_KEY_CREATED=NO"
fi

python3 - "$PORT" <<'PY'
import socket,sys
p=int(sys.argv[1]);s=socket.socket()
try:s.bind(("127.0.0.1",p))
except OSError:raise SystemExit("CHACHA_DEV_V67_INGRESS_INSTALL=BLOCKED reason=port_in_use")
finally:s.close()
PY

install -m 0644 "$SRC/dev-hub/systemd/chacha-dev-central-learning-ingress.service" /etc/systemd/system/chacha-dev-central-learning-ingress.service
sed -i "s/--port 8791/--port $PORT/" /etc/systemd/system/chacha-dev-central-learning-ingress.service
systemctl daemon-reload
systemctl enable chacha-dev-central-learning-ingress.service
systemctl restart chacha-dev-central-learning-ingress.service

READY=0
for _ in {1..50}; do
  if systemctl is-active --quiet chacha-dev-central-learning-ingress.service && curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then READY=1;break;fi
  sleep .2
done
if [ "$READY" != 1 ]; then
  systemctl status --no-pager chacha-dev-central-learning-ingress.service || true
  journalctl -u chacha-dev-central-learning-ingress.service -n 60 --no-pager || true
  echo "CHACHA_DEV_V67_INGRESS_INSTALL=BLOCKED reason=service_not_ready"
  exit 2
fi

echo "CHACHA_DEV_V67_CENTRAL_LEARNING_INGRESS=PASS"
echo "CHACHA_DEV_V67_PLATFORM_SCOPE=GLOBAL"
echo "CHACHA_DEV_V67_APP_SPECIFIC_DEPENDENCY=NO"
echo "CHACHA_DEV_V67_EXTERNAL_EDGE_REQUIRED=YES"
echo "CHACHA_DEV_V67_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V67_INGRESS_INSTALL=PASS"
