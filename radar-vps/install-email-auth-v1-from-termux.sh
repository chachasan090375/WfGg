#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
REPO_RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/radar-production-v1/radar-vps/release"
REMOTE_BIN="/opt/wfgg-radar/bin"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
for cmd in curl ssh scp sha256sum grep; do command -v "$cmd" >/dev/null 2>&1 || die "$cmd absent"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say "EMAIL_AUTH_SSH_ROUTE=ChaChaVPS"
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die "ChaChaVPS inaccessible via Tailscale et IPv4 publique"
  say "EMAIL_AUTH_SSH_ROUTE=PUBLIC_IPV4"
fi

say "=== WfGg Radar · Auth Last War e-mail v1 ==="
say "1/4 Téléchargement de la release signée par checksum"
curl -fsSL "$REPO_RAW/SHA256SUMS?ts=$(date +%s)" -o "$TMP/SHA256SUMS"
curl -fsSL "$REPO_RAW/radar-connector?ts=$(date +%s)" -o "$TMP/radar-connector"
curl -fsSL "$REPO_RAW/radar-lastwar-auth-client?ts=$(date +%s)" -o "$TMP/radar-lastwar-auth-client"
grep -E '  (radar-connector|radar-lastwar-auth-client)$' "$TMP/SHA256SUMS" > "$TMP/SELECTED_SHA256SUMS"
[[ "$(wc -l < "$TMP/SELECTED_SHA256SUMS" | tr -d ' ')" = "2" ]] || die "release e-mail auth pas encore publiée"
(
  cd "$TMP"
  sha256sum -c SELECTED_SHA256SUMS
) >/dev/null
chmod 0755 "$TMP/radar-connector" "$TMP/radar-lastwar-auth-client"
grep -aFq '/v1/auth/email/start' "$TMP/radar-connector" || die "connecteur sans auth e-mail"
say "EMAIL_AUTH_RELEASE_SHA256=OK"

say "2/4 Transfert vers le VPS"
TAG="$$"
RCON="/tmp/wfgg-radar-connector-email-$TAG"
RAUTH="/tmp/wfgg-radar-lastwar-auth-$TAG"
scp "${SSH_OPTS[@]}" -q "$TMP/radar-connector" "$REMOTE:$RCON"
scp "${SSH_OPTS[@]}" -q "$TMP/radar-lastwar-auth-client" "$REMOTE:$RAUTH"

say "3/4 Installation atomique"
ssh "${SSH_OPTS[@]}" "$REMOTE" "set -eu; install -d -o root -g root -m 0755 '$REMOTE_BIN'; install -o root -g root -m 0755 '$RCON' '$REMOTE_BIN/radar-connector'; install -o root -g root -m 0755 '$RAUTH' '$REMOTE_BIN/radar-lastwar-auth-client'; rm -f '$RCON' '$RAUTH'; systemctl restart wfgg-radar-connector; sleep 2; test \"\$(systemctl is-active wfgg-radar-connector)\" = active" </dev/null

say "4/4 Contrôle final"
ssh "${SSH_OPTS[@]}" "$REMOTE" "set -eu; test -x '$REMOTE_BIN/radar-connector'; test -x '$REMOTE_BIN/radar-lastwar-auth-client'; grep -aFq '/v1/auth/email/start' '$REMOTE_BIN/radar-connector'; grep -aFq '/v1/auth/email/finish' '$REMOTE_BIN/radar-connector'; echo EMAIL_AUTH_CONNECTOR_SERVICE=\$(systemctl is-active wfgg-radar-connector); echo EMAIL_AUTH_HELPER=READY; echo LASTWAR_CODE_PERSISTED=NO; echo LASTWAR_PLAINTEXT_CREDENTIAL_ON_VPS=NO" </dev/null
say "EMAIL_AUTH_ACTIVATION=OK"
