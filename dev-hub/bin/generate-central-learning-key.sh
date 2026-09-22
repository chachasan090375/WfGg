#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${1:-/opt/chacha-dev/runtime/secrets/central-learning-key}"
mkdir -p "$(dirname "$ROOT")"
umask 077

if [ ! -s "$ROOT.pem" ]; then
  openssl genpkey -algorithm ED25519 -out "$ROOT.pem"
  chmod 600 "$ROOT.pem"
fi

openssl pkey -in "$ROOT.pem" -pubout -out "$ROOT.pub.pem"
chmod 644 "$ROOT.pub.pem"

PUB_B64="$(openssl pkey -in "$ROOT.pem" -pubout -outform DER | base64 -w0)"
KEY_ID="central-$(printf '%s' "$PUB_B64" | sha256sum | cut -c1-16)"

python3 - "$KEY_ID" "$PUB_B64" <<'PY'
import json,sys
key_id,pub=sys.argv[1:]
print(json.dumps({
  "schema":"chacha.dev/central-learning-public-key/v1",
  "key_id":key_id,
  "algorithm":"Ed25519",
  "public_key_spki_b64":pub,
  "private_key_exported":False
},indent=2))
PY

echo "CHACHA_DEV_CENTRAL_KEYGEN=PASS" >&2
echo "CHACHA_DEV_CENTRAL_PRIVATE_KEY=$ROOT.pem" >&2
