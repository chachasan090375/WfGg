#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V68_EDGE_REV:-}"
TOKEN="${CHACHA_CF_TUNNEL_TOKEN:-}"
PUBLIC_URL="${CHACHA_LEARNING_PUBLIC_URL:-}"
TOKEN_FILE="/opt/chacha-dev/runtime/secrets/learning-ingress-tunnel.token"
SERVICE="chacha-dev-learning-edge-cloudflared.service"

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V68_EDGE_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V68_EDGE_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }
for cmd in curl apt-get python3 install systemctl; do command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V68_EDGE_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }; done

WORK="$(mktemp -d /tmp/chacha-v68-edge.XXXXXX)";trap 'rm -rf "$WORK" 2>/dev/null || true' EXIT
curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$WORK/repo.tar.gz"
tar -xzf "$WORK/repo.tar.gz" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V68_EDGE_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

if ! command -v cloudflared >/dev/null 2>&1; then
  mkdir -p --mode=0755 /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
  chmod 0644 /usr/share/keyrings/cloudflare-main.gpg
  echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' >/etc/apt/sources.list.d/cloudflared.list
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y cloudflared
fi
cloudflared --version
echo "CHACHA_DEV_V68_CLOUDFLARED_INSTALLED=PASS"

install -m 0644 "$SRC/dev-hub/systemd/$SERVICE" "/etc/systemd/system/$SERVICE"
install -m 0755 "$SRC/dev-hub/bin/learning-identity-provisioner.py" /opt/chacha-dev/learning-ingress/current/learning-identity-provisioner.py
python3 -m py_compile /opt/chacha-dev/learning-ingress/current/learning-identity-provisioner.py
systemctl daemon-reload

mkdir -p /opt/chacha-dev/runtime/secrets
if [ -n "$TOKEN" ]; then
  umask 077
  printf '%s\n' "$TOKEN" >"$TOKEN_FILE"
  chmod 0600 "$TOKEN_FILE"
  unset TOKEN CHACHA_CF_TUNNEL_TOKEN
  echo "CHACHA_DEV_V68_TUNNEL_TOKEN_SOURCE=ENV_MIGRATED_TO_FILE"
elif [ -s "$TOKEN_FILE" ]; then
  chmod 0600 "$TOKEN_FILE"
  echo "CHACHA_DEV_V68_TUNNEL_TOKEN_SOURCE=EXISTING_PROTECTED_FILE"
else
  echo "CHACHA_DEV_V68_EDGE_PREPARED=PASS"
  echo "CHACHA_DEV_V68_TUNNEL_TOKEN_REQUIRED=YES"
  echo "CHACHA_DEV_V68_PUBLIC_ROUTE_REQUIRED=YES"
  echo "CHACHA_DEV_V68_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
  exit 0
fi

systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

READY=0
for _ in {1..80}; do
  if systemctl is-active --quiet "$SERVICE" && curl -fsS http://127.0.0.1:20042/ready >/dev/null 2>&1; then READY=1;break;fi
  sleep .25
done
if [ "$READY" != 1 ]; then
  systemctl status --no-pager "$SERVICE" || true
  journalctl -u "$SERVICE" -n 80 --no-pager || true
  echo "CHACHA_DEV_V68_EDGE_INSTALL=BLOCKED reason=tunnel_not_ready"
  exit 2
fi

echo "CHACHA_DEV_V68_TUNNEL_CONNECTED=PASS"
if [ -n "$PUBLIC_URL" ]; then
  case "$PUBLIC_URL" in https://*) ;; *) echo "CHACHA_DEV_V68_EDGE_INSTALL=BLOCKED reason=public_url_must_be_https";exit 2;; esac
  curl -fsS "$PUBLIC_URL/healthz" >/dev/null
  echo "CHACHA_DEV_V68_PUBLIC_HTTPS_HEALTH=PASS"
else
  echo "CHACHA_DEV_V68_PUBLIC_HTTPS_HEALTH=DEFERRED reason=public_url_not_supplied"
fi
echo "CHACHA_DEV_V68_DIRECT_PUBLIC_VPS_PORT=NO"
echo "CHACHA_DEV_V68_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V68_EDGE_INSTALL=PASS"
