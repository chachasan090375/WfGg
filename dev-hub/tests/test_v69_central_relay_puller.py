#!/usr/bin/env python3
from __future__ import annotations
import base64,hashlib,importlib.util,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PULLER=ROOT/"dev-hub/bin/central-learning-relay-puller.py"
INSTALLER=ROOT/"dev-hub/bin/install-central-learning-relay-puller.sh"
SERVICE=ROOT/"dev-hub/systemd/chacha-dev-central-learning-relay-pull.service"
TIMER=ROOT/"dev-hub/systemd/chacha-dev-central-learning-relay-pull.timer"

spec=importlib.util.spec_from_file_location("puller",PULLER)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

with tempfile.TemporaryDirectory(prefix="chacha-v69-key-") as td:
    td=Path(td);key=td/"k.pem";pub=td/"k.pub"
    subprocess.run(["openssl","genpkey","-algorithm","ED25519","-out",str(key)],check=True)
    subprocess.run(["openssl","pkey","-in",str(key),"-pubout","-out",str(pub)],check=True)
    pub_b64=m.derive_public_b64(key)
    key_id=m.derive_key_id(key)
    assert key_id=="central-"+hashlib.sha256(pub_b64.encode()).hexdigest()[:16]
    msg=b"2026-09-22T16:00:00Z\nGET\n/v1/central/pull?limit=25\n"
    sig=m.sign(key,msg)
    sig_raw=base64.urlsafe_b64decode(sig+"="*((4-len(sig)%4)%4))
    sigfile=td/"sig";msgfile=td/"msg"
    sigfile.write_bytes(sig_raw);msgfile.write_bytes(msg)
    subprocess.run(["openssl","pkeyutl","-verify","-rawin","-pubin","-inkey",str(pub),"-sigfile",str(sigfile),"-in",str(msgfile)],check=True,stdout=subprocess.DEVNULL)

installer=INSTALLER.read_text(encoding="utf-8")
service=SERVICE.read_text(encoding="utf-8")
timer=TIMER.read_text(encoding="utf-8")
assert "central_key_mismatch" in installer
assert "LIVE_RELAY_AUTH=PASS" in installer
assert "enable --now chacha-dev-central-learning-relay-pull.timer" in installer
assert "workers.dev" in service
assert "central-learning-key.pem" in service
assert "OnUnitActiveSec=60s" in timer
assert "cloudflared" not in service.lower()
print("CHACHA_DEV_V69_ED25519_CENTRAL_AUTH=PASS")
print("CHACHA_DEV_V69_PULLER_CONTRACT=PASS")
print("CHACHA_DEV_V69_NO_TUNNEL_PULLER=PASS")
