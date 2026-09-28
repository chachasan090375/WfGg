#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"; CFG=ROOT/"dev-hub/config"
with tempfile.TemporaryDirectory(prefix="capsule-contract-") as td:
    td=Path(td)
    project="capsule-contract-project"
    def branch(domain,mem,disk,cpu):
        return {"branch_id":f"{project}:{domain}:primary","project_id":project,"scope":"PROJECT","runtime_required":True,
          "ttl_seconds":60,"resource_budget":{"memory_hard_limit_mb":mem,"disk_soft_limit_mb":disk,"cpu_weight":cpu,"processes_max":1},
          "universal_materialization":{"required":True,"governance_class":"RUNTIME_INFRASTRUCTURE","owner_foundry":"branch-foundry",
            "status":"PENDING_CANONICAL_REGISTRATION","retention_policy":"TTL_AND_CLASS_DEFAULT_RETENTION","purge_policy":"UNIVERSAL_HYGIENE",
            "materialization_gate_required":True,"birth_contract":{"owner_foundry":"branch-foundry"},"automatic_external_spend_eur":0},
          "automatic_external_spend_eur":0}
    topo={"project_id":project,"decisions":[branch("a",192,256,35),branch("b",128,128,25)]}
    (td/"topo.json").write_text(json.dumps(topo))
    p=subprocess.run([sys.executable,str(BIN/"capsule-scheduler.py"),"--topology",str(td/"topo.json"),"--policy",str(CFG/"branch-foundry.v1.json"),"--output",str(td/"waves.json")],check=True)
    p=subprocess.run([sys.executable,str(BIN/"capsule-runtime-controller.py"),"--runtime-root",str(td/"runtime"),"--emergency-state",str(td/"stop.json"),
      "materialize","--topology",str(td/"topo.json"),"--wave-plan",str(td/"waves.json"),"--wave","1","--ttl","60","--worker",str(BIN/"capsule-worker.py"),"--dry-run"],
      stdout=subprocess.PIPE,text=True,check=True)
    x=json.JSONDecoder().raw_decode(p.stdout)[0]
    assert len(x["capsules"])==2,x
    assert all(c["unit"].startswith("chacha-dev-branch@") for c in x["capsules"]),x
    assert all(c["state"]=="DRY_RUN" for c in x["capsules"]),x
    assert all(c["project_id"]==project and c["scope"]=="PROJECT" for c in x["capsules"]),x
    assert (td/"runtime"/project/"registry.json").is_file()
    assert sum(c["resource_budget"]["memory_hard_limit_mb"] for c in x["capsules"])<=1024,x
surface=(BIN/"emergency-stop-surface.py").read_text(encoding="utf-8")
assert 'DEFAULT_BIND="127.0.0.1"' in surface
assert "DEFAULT_PORT=0" in surface
assert "emergency-stop-surface.json" in surface
assert "STOP D’URGENCE" in surface
assert "X-ChaCha-Stop-Token" in surface
unit=(ROOT/"dev-hub/systemd/chacha-dev-emergency-stop-surface.service").read_text(encoding="utf-8")
assert "--port 0" in unit
assert "--endpoint-file /opt/chacha-dev/runtime/control/emergency-stop-surface.json" in unit
pilot=(BIN/"run-v64-runtime-pilot-via-chacha-dev.sh").read_text(encoding="utf-8")
assert "--nas" in pilot and "EXPERIENCE_LEDGER_NAS_E2E=PASS" in pilot
assert "CHACHA_NAS_ADAPTER=" in pilot
assert "NAS_ADAPTER_STAGED" in pilot
assert "NAS_ADAPTER_PROMOTED=PASS" in pilot
assert "dev-hub/adapters/nas-ssh-adapter.py" in pilot
assert "api/emergency-stop/activate" in pilot
assert "systemctl stop chacha-dev-emergency-stop-surface.service" in pilot
assert "CHACHA_DEV_V64_EMERGENCY_DYNAMIC_ENDPOINT=PASS" in pilot
assert "EMERGENCY_ENDPOINT_FILE" in pilot
assert "EMERGENCY_BASE_URL" in pilot
assert "127.0.0.1:8788" not in pilot
assert "emergency-stop-surface.py" in unit
assert "CHACHA_DEV_V64_EMERGENCY_SURFACE_READY=PASS" in pilot
assert "reason=emergency_surface_not_ready" in pilot
print("CHACHA_DEV_V64_CAPSULE_RUNTIME_CONTRACT=PASS")
print("CHACHA_DEV_V64_EMERGENCY_SURFACE_CONTRACT=PASS")
print("CHACHA_DEV_V64_NAS_E2E_PILOT_CONTRACT=PASS")
