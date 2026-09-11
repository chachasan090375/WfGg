#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REMOTE="ChaChaVPS"
PUBLIC_HOST="${RADAR_VPS_PUBLIC_IP:-206.189.12.92}"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/collector-v1/collector/release"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR=%s\n' "$*" >&2; exit 1; }
for cmd in curl ssh scp sha256sum; do command -v "$cmd" >/dev/null 2>&1 || die "${cmd}_MISSING"; done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM
curl -fsSL "$RAW/SHA256SUMS" -o "$TMP/SHA256SUMS" || die RELEASE_NOT_READY
curl -fsSL "$RAW/radar-native-template" -o "$TMP/radar-native-template" || die RELEASE_NOT_READY
(cd "$TMP" && sha256sum -c SHA256SUMS) >/dev/null || die SHA256_FAILED
chmod 0755 "$TMP/radar-native-template"

SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
if ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1; then
  say 'SSH_ROUTE=ChaChaVPS'
else
  SSH_OPTS+=(-o HostName="$PUBLIC_HOST")
  ssh "${SSH_OPTS[@]}" "$REMOTE" 'true' </dev/null >/dev/null 2>&1 || die VPS_UNREACHABLE
  say 'SSH_ROUTE=PUBLIC_IPV4'
fi

TAG="$$"
RBIN="/tmp/wfgg-collector-native-$TAG"
scp "${SSH_OPTS[@]}" -q "$TMP/radar-native-template" "$REMOTE:$RBIN"
ssh "${SSH_OPTS[@]}" -T "$REMOTE" "
set -eu
install -d -o wfgg-radar -g wfgg-radar -m 0750 /opt/wfgg-collector /opt/wfgg-collector/bin
install -o root -g root -m 0755 '$RBIN' /opt/wfgg-collector/bin/radar-native-template
rm -f '$RBIN'
echo COLLECTOR_NATIVE_SHA=\$(sha256sum /opt/wfgg-collector/bin/radar-native-template | cut -d' ' -f1)
"
say 'RADAR_PRODUCTION_BINARY_CHANGED=NO'
