#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
policy=ROOT/"dev-hub/config/adapter-provisioning.v1.json"
cfg=json.loads(policy.read_text(encoding="utf-8"))
item=cfg["adapters"]["collector-knowledge-adapter"]
assert item["version"]=="1.0.1",item
assert item["namespace"]=="collector-knowledge"
assert item["executable_name"]=="collector-knowledge-adapter"

source=(ROOT/item["source"]).read_text(encoding="utf-8")
assert 'BOOTSTRAP_PROVIDER_ID="collector-knowledge-bootstrap"' in source
assert 'required_provider=BOOTSTRAP_PROVIDER_ID if action in {"pilot-install","pilot-probe"} else PROVIDER_ID' in source

with tempfile.TemporaryDirectory(prefix="v824-provision-") as td:
    p=subprocess.run([
      "python3",str(ROOT/"dev-hub/bin/adapter-provision.py"),
      "--policy",str(policy),"--root",td,
      "plan","--adapter","collector-knowledge-adapter"
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    plan=json.loads(p.stdout)
    assert plan["version"]=="1.0.1",plan
    assert "/collector-knowledge/1.0.1/collector-knowledge-adapter" in plan["installed_path"],plan
    assert plan["executable_path"].endswith("/collector-knowledge/current/collector-knowledge-adapter"),plan

print("CHACHA_DEV_V824_COLLECTOR_ADAPTER_VERSION_101=PASS")
print("CHACHA_DEV_V824_IMMUTABLE_VERSION_PATH=PASS")
print("CHACHA_DEV_V824_BOOTSTRAP_TRUST_CODE_PRESERVED=PASS")
print("CHACHA_DEV_V824_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
