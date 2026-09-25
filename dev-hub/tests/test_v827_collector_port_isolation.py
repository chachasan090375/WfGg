#!/usr/bin/env python3
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parents[2]

central=json.loads((ROOT/"dev-hub/config/central-learning-ingress.v1.json").read_text(encoding="utf-8"))
collector=json.loads((ROOT/"collector-knowledge/config.example.json").read_text(encoding="utf-8"))
assert int((central.get("core") or {}).get("port") or 0)==8791,central
assert collector["listenHost"]=="127.0.0.1",collector
assert collector["listenPort"]==8793,collector
assert collector["listenPort"]!=8791

adapter=(ROOT/"dev-hub/adapters/collector-knowledge-adapter.py").read_text(encoding="utf-8")
assert 'API_BASE="http://127.0.0.1:8793"' in adapter
assert 'API_BASE="http://127.0.0.1:8791"' not in adapter
assert 'INSTALLER_PATH="radar-vps/install-collector-knowledge-v1.sh"' in adapter
assert 'PROBE_PATH="radar-vps/probe-collector-knowledge-v1-runtime.sh"' in adapter

installer=(ROOT/"radar-vps/install-collector-knowledge-v1.sh").read_text(encoding="utf-8")
for marker in [
    'PORT="${WFGG_COLLECTOR_KNOWLEDGE_PORT:-8793}"',
    'CENTRAL_LEARNING_INGRESS_PORT_RESERVED',
    'PORT_ALREADY_IN_USE:$PORT',
    'systemctl stop wfgg-collector-knowledge-api.service',
    'systemctl restart wfgg-collector-knowledge-api.service',
    "x['listenPort']=port",
    "http://127.0.0.1:8791/healthz",
    "chacha-central-learning-ingress",
    "COLLECTOR_KNOWLEDGE_PORT_ISOLATION=PASS",
    "CHACHA_CENTRAL_LEARNING_INGRESS_UNCHANGED=PASS",
]:
    assert marker in installer,marker

probe=(ROOT/"radar-vps/probe-collector-knowledge-v1-runtime.sh").read_text(encoding="utf-8")
assert 'API=http://127.0.0.1:8793' in probe
assert 'http://127.0.0.1:8791/healthz' in probe
assert 'COLLECTOR_KNOWLEDGE_PORT_ISOLATION=PASS' in probe
assert 'CHACHA_CENTRAL_LEARNING_INGRESS_UNCHANGED=PASS' in probe

engine=(ROOT/"collector-knowledge/knowledge_engine.py").read_text(encoding="utf-8")
assert 'cfg.get("listenPort",8793)' in engine
assert '/knowledge/health' in engine

pilot=(ROOT/"dev-hub/bin/run-collector-knowledge-v1-pilot-via-chacha-dev.sh").read_text(encoding="utf-8")
assert 'KNOWLEDGE_REV="$REV"' in pilot
assert '6ddbc5d848cf2aebc2c6175b2aa9ba1645c2e2ae' not in pilot
assert 'COLLECTOR_KNOWLEDGE_BOOTSTRAP_GUARDIAN_BINDING=PASS' in pilot

# No Collector endpoint may hijack the central learning ingress port.
for path in [
    ROOT/"dev-hub/adapters/collector-knowledge-adapter.py",
    ROOT/"collector-knowledge/config.example.json",
    ROOT/"radar-vps/probe-collector-knowledge-v1-runtime.sh",
]:
    text=path.read_text(encoding="utf-8")
    assert "127.0.0.1:8791/knowledge" not in text,(path,"central port collision")

print("CHACHA_DEV_V827_CENTRAL_INGRESS_PORT_RESERVED=PASS")
print("CHACHA_DEV_V827_COLLECTOR_PORT_8793=PASS")
print("CHACHA_DEV_V827_ADAPTER_PORT_ALIGNED=PASS")
print("CHACHA_DEV_V827_KNOWLEDGE_REVISION_COHERENT=PASS")
print("CHACHA_DEV_V827_GUARDIAN_BINDING_PRESERVED=PASS")
print("CHACHA_DEV_V827_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
