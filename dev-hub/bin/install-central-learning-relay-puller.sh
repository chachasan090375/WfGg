#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V69_PULLER_REV:-}"
BASE="/opt/chacha-dev/learning-relay"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-v69-puller.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
PRIVATE_KEY="/opt/chacha-dev/runtime/secrets/central-learning-key.pem"

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V69_PULLER_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V69_PULLER_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
[ -s "$PRIVATE_KEY" ] || { echo "CHACHA_DEV_V69_PULLER_INSTALL=BLOCKED reason=central_private_key_missing"; exit 2; }

for cmd in curl tar python3 install ln systemctl openssl base64 sha256sum; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V69_PULLER_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V69_PULLER_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/knowledge /opt/chacha-dev/runtime/learning/anomaly-queue
install -m 0755 "$SRC/dev-hub/bin/central-learning-relay-puller.py" "$RELEASE/central-learning-relay-puller.py"
install -m 0755 "$SRC/dev-hub/bin/learning-delta-ingest.py" "$RELEASE/learning-delta-ingest.py"
install -m 0755 "$SRC/dev-hub/bin/global-project-memory-index.py" "$RELEASE/global-project-memory-index.py"
install -m 0644 "$SRC/dev-hub/config/worker-learning-central-identity.v1.json" "$RELEASE/central-public-identity.json"
python3 -m py_compile "$RELEASE/central-learning-relay-puller.py" "$RELEASE/learning-delta-ingest.py" "$RELEASE/global-project-memory-index.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"

ACTUAL_PUB="$(openssl pkey -in "$PRIVATE_KEY" -pubout -outform DER | base64 -w0)"
EXPECTED_PUB="$(python3 - "$RELEASE/central-public-identity.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1],encoding="utf-8"))["public_key_spki_b64"])
PY
)"
[ "$ACTUAL_PUB" = "$EXPECTED_PUB" ] || { echo "CHACHA_DEV_V69_PULLER_INSTALL=BLOCKED reason=central_key_mismatch"; exit 2; }
echo "CHACHA_DEV_V69_CENTRAL_KEY_MATCH=PASS"

ln -sfn "$RELEASE" "$CURRENT"
install -m 0644 "$SRC/dev-hub/systemd/chacha-dev-central-learning-relay-pull.service" /etc/systemd/system/chacha-dev-central-learning-relay-pull.service
install -m 0644 "$SRC/dev-hub/systemd/chacha-dev-central-learning-relay-pull.timer" /etc/systemd/system/chacha-dev-central-learning-relay-pull.timer
systemctl daemon-reload

# Live auth proof against the Worker relay. An empty mailbox is a valid PASS.
CHACHA_NAS_ADAPTER=/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter   python3 "$CURRENT/central-learning-relay-puller.py"     --relay-url https://chacha-dev-learning-relay.chachasan090375.workers.dev     --private-key "$PRIVATE_KEY"     --ingest "$CURRENT/learning-delta-ingest.py"     --db /opt/chacha-dev/runtime/knowledge/learning-deltas.db     --anomaly-queue /opt/chacha-dev/runtime/learning/anomaly-queue     --batch-limit 25     --experience-db /opt/chacha-dev/runtime/knowledge/experience.db     --global-indexer "$CURRENT/global-project-memory-index.py"     --global-index /opt/chacha-dev/runtime/knowledge/global-project-memory-index.json >"$WORK/live-pull.json"

grep -Fq '"status": "PASS"' "$WORK/live-pull.json"
echo "CHACHA_DEV_V69_LIVE_RELAY_AUTH=PASS"

systemctl enable --now chacha-dev-central-learning-relay-pull.timer
systemctl is-active --quiet chacha-dev-central-learning-relay-pull.timer

echo "CHACHA_DEV_V69_OUTBOUND_PULL_TIMER=PASS"
echo "CHACHA_DEV_V69_TUNNEL_REQUIRED=NO"
echo "CHACHA_DEV_V69_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V69_PULLER_INSTALL=PASS"
