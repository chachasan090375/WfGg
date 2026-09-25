#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

arch=loadmod("v822_arch",ROOT/"dev-hub/adapters/architecture-specialist-adapter.py")
ready=loadmod("v822_ready",ROOT/"dev-hub/bin/domain-toolchain-readiness.py")

fixture=json.loads((ROOT/"dev-hub/fixtures/architecture-specialist-adapter.status.v1.json").read_text())
assert fixture["bindings"][0]["health_state"]=="UNKNOWN"
action,data,error=arch.validate_request(fixture)
assert error is None,(action,error)
assert action=="status",action

probe=json.loads(json.dumps(fixture))
probe["task"]["permission"]="plan"
probe["metadata"]["architecture_specialist"]["action"]="inference-probe"
action,data,error=arch.validate_request(probe)
assert error=="ARCHITECT_PROVIDER_NOT_HEALTHY",(action,error)

probe["bindings"][0]["health_state"]="HEALTHY"
action,data,error=arch.validate_request(probe)
assert error is None and action=="inference-probe",(action,error)

with tempfile.TemporaryDirectory(prefix="v822-ready-") as td:
    root=Path(td);exe=root/"adapter";exe.write_text("#!/bin/sh\nexit 0\n");exe.chmod(0o755)
    bindings={
      "contract-ok":{"adapter":"a-contract","execution":"vps"},
      "pilot":{"adapter":"a-pilot","execution":"vps"},
      "pilot-no-probe":{"adapter":"a-pilot-no-probe","execution":"vps"},
      "designed":{"adapter":"a-designed","execution":"vps"},
    }
    defs={
      "a-contract":{"status":"CONTRACT_OK","executable":str(exe)},
      "a-pilot":{"status":"PILOT","executable":str(exe)},
      "a-pilot-no-probe":{"status":"PILOT","executable":str(exe)},
      "a-designed":{"status":"DESIGNED","executable":None},
    }
    probes={"contract-ok":{},"pilot":{},"designed":{}}
    encap={}
    def row(pid):
        return ready.provider_candidate(ROOT,{"id":pid,"status":"ADOPT"},bindings,defs,probes,encap)
    assert row("contract-ok")["gate"]=="PROVIDER_HEALTH_PROBE_REQUIRED",row("contract-ok")
    assert row("pilot")["gate"]=="PROVIDER_HEALTH_PROBE_REQUIRED",row("pilot")
    assert row("pilot-no-probe")["gate"]=="PROVIDER_PROBE_DEFINITION_REQUIRED",row("pilot-no-probe")
    assert row("designed")["gate"]=="ADAPTER_ENABLEMENT_REQUIRED",row("designed")

adapters=json.loads((ROOT/"dev-hub/config/provider-adapters.v1.json").read_text())
a=adapters["adapters"]["architecture-specialist-adapter"]
assert a["status"]=="CONTRACT_OK"
assert a["executable"]=="/opt/chacha-dev/adapters/architecture-specialist/current/architecture-specialist-adapter"

probes=json.loads((ROOT/"dev-hub/config/provider-health-probes.v1.json").read_text())
collector=probes["providers"]["collector-knowledge-runtime"]
assert collector["probe"]=="runtime-command"
assert collector["functional_check"]=="collector-knowledge-status"

print("CHACHA_DEV_V822_ARCH_STATUS_BOOTSTRAP_UNKNOWN=PASS")
print("CHACHA_DEV_V822_ARCH_INFERENCE_STILL_HEALTHY_ONLY=PASS")
print("CHACHA_DEV_V822_CONTRACT_OK_GOES_TO_HEALTH_PROBE=PASS")
print("CHACHA_DEV_V822_PILOT_GOES_TO_HEALTH_PROBE=PASS")
print("CHACHA_DEV_V822_MISSING_PROBE_FAILS_CLOSED=PASS")
print("CHACHA_DEV_V822_DESIGNED_WITHOUT_EXECUTABLE_STAYS_BLOCKED=PASS")
print("CHACHA_DEV_V822_COLLECTOR_PROBE_DEFINED=PASS")
print("CHACHA_DEV_V822_NO_AUTOMATIC_ENABLEMENT=PASS")
print("CHACHA_DEV_V822_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
