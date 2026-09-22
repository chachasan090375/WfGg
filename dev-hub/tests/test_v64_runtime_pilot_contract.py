#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"; CFG=ROOT/"dev-hub/config"
with tempfile.TemporaryDirectory(prefix="capsule-contract-") as td:
    td=Path(td)
    topo={"decisions":[
      {"branch_id":"a","runtime_required":True,"resource_budget":{"memory_hard_limit_mb":192,"disk_soft_limit_mb":256,"cpu_weight":35,"processes_max":1}},
      {"branch_id":"b","runtime_required":True,"resource_budget":{"memory_hard_limit_mb":128,"disk_soft_limit_mb":128,"cpu_weight":25,"processes_max":1}}
    ]}
    (td/"topo.json").write_text(json.dumps(topo))
    p=subprocess.run([sys.executable,str(BIN/"capsule-scheduler.py"),"--topology",str(td/"topo.json"),"--policy",str(CFG/"branch-foundry.v1.json"),"--output",str(td/"waves.json")],check=True)
    p=subprocess.run([sys.executable,str(BIN/"capsule-runtime-controller.py"),"--runtime-root",str(td/"runtime"),"--emergency-state",str(td/"stop.json"),
      "materialize","--topology",str(td/"topo.json"),"--wave-plan",str(td/"waves.json"),"--wave","1","--ttl","60","--worker",str(BIN/"capsule-worker.py"),"--dry-run"],
      stdout=subprocess.PIPE,text=True,check=True)
    x=json.JSONDecoder().raw_decode(p.stdout)[0]
    assert len(x["capsules"])==2,x
    assert all(c["unit"].startswith("chacha-dev-branch@") for c in x["capsules"]),x
    assert all(c["state"]=="DRY_RUN" for c in x["capsules"]),x
    assert sum(c["resource_budget"]["memory_hard_limit_mb"] for c in x["capsules"])<=1024,x
surface=(BIN/"emergency-stop-surface.py").read_text(encoding="utf-8")
assert 'DEFAULT_BIND="127.0.0.1"' in surface
assert "STOP D’URGENCE" in surface
assert "X-ChaCha-Stop-Token" in surface
pilot=(BIN/"run-v64-runtime-pilot-via-chacha-dev.sh").read_text(encoding="utf-8")
assert "--nas" in pilot and "EXPERIENCE_LEDGER_NAS_E2E=PASS" in pilot
assert "api/emergency-stop/activate" in pilot
assert "systemctl stop chacha-dev-emergency-stop-surface.service" in pilot
assert "CHACHA_DEV_V64_EMERGENCY_PORT_RECOVERY=PASS" in pilot
assert "CHACHA_DEV_V64_EMERGENCY_PORT_CONFLICT=BLOCKED" in pilot
assert "emergency-stop-surface.py" in pilot
assert "CHACHA_DEV_V64_EMERGENCY_SURFACE_READY=PASS" in pilot
assert "reason=emergency_surface_not_ready" in pilot
print("CHACHA_DEV_V64_CAPSULE_RUNTIME_CONTRACT=PASS")
print("CHACHA_DEV_V64_EMERGENCY_SURFACE_CONTRACT=PASS")
print("CHACHA_DEV_V64_NAS_E2E_PILOT_CONTRACT=PASS")
