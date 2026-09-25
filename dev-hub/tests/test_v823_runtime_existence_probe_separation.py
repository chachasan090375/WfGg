#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

provision=loadmod("v823_provision",ROOT/"dev-hub/bin/adapter-provision.py")
ready=loadmod("v823_ready",ROOT/"dev-hub/bin/domain-toolchain-readiness.py")

with tempfile.TemporaryDirectory(prefix="v823-probe-") as raw:
    base=Path(raw)
    exe=base/"fake-adapter"
    def write_status(status):
        exe.write_text(
          "#!/usr/bin/env python3\nimport json,sys\n"
          "json.load(sys.stdin)\n"
          f"print(json.dumps({{'schema':'chacha.dev/task-result/v1','status':'{status}','producer':'fake-adapter','verification':{{'status':'UNVERIFIED'}}}}))\n",
          encoding="utf-8"
        )
        exe.chmod(0o755)
    item={"probe":{
      "input":{"schema":"x"},
      "expected_schema":"chacha.dev/task-result/v1",
      "expected_statuses":["OK","BLOCKED"],
      "expected_producer":"fake-adapter",
      "expected_verification_status":"UNVERIFIED"
    }}
    write_status("OK")
    p=provision.probe(exe,item,5)
    assert p["status"]=="PASS",p
    assert p["expected_statuses"]==["OK","BLOCKED"],p
    write_status("BLOCKED")
    p=provision.probe(exe,item,5)
    assert p["status"]=="PASS",p
    write_status("FAILED")
    p=provision.probe(exe,item,5)
    assert p["status"]=="FAIL",p

with tempfile.TemporaryDirectory(prefix="v823-ready-") as raw:
    base=Path(raw)
    good=base/"good";good.write_text("#!/bin/sh\nexit 0\n");good.chmod(0o755)
    missing=base/"missing"
    bindings={"missing-provider":{"adapter":"a-missing","execution":"vps"},
              "good-provider":{"adapter":"a-good","execution":"vps"}}
    defs={"a-missing":{"status":"ENABLED","executable":str(missing)},
          "a-good":{"status":"CONTRACT_OK","executable":str(good)}}
    probes={"missing-provider":{},"good-provider":{}}
    bad=ready.provider_candidate(ROOT,{"id":"missing-provider","status":"ADOPT"},bindings,defs,probes,{})
    assert bad["gate"]=="ADAPTER_ENABLEMENT_REQUIRED",bad
    assert bad["reason"]=="vps-adapter-runtime-missing-or-not-executable",bad
    assert bad["executable_exists"] is False,bad
    goodrow=ready.provider_candidate(ROOT,{"id":"good-provider","status":"ADOPT"},bindings,defs,probes,{})
    assert goodrow["gate"]=="PROVIDER_HEALTH_PROBE_REQUIRED",goodrow
    assert goodrow["executable_exists"] is True and goodrow["executable_is_executable"] is True,goodrow

policy=json.loads((ROOT/"dev-hub/config/adapter-provisioning.v1.json").read_text(encoding="utf-8"))
cp=policy["adapters"]["collector-knowledge-adapter"]["probe"]
assert cp["expected_statuses"]==["OK","BLOCKED"],cp
assert cp["health_decision_deferred_to_provider_probe"] is True,cp
assert "expected_status" not in cp,cp

print("CHACHA_DEV_V823_PROVISIONING_STATUS_HEALTH_SEPARATED=PASS")
print("CHACHA_DEV_V823_STRUCTURED_OK_ACCEPTED=PASS")
print("CHACHA_DEV_V823_STRUCTURED_BLOCKED_ACCEPTED=PASS")
print("CHACHA_DEV_V823_UNEXPECTED_STATUS_REJECTED=PASS")
print("CHACHA_DEV_V823_MISSING_RUNTIME_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V823_PHYSICAL_RUNTIME_REQUIRED=PASS")
print("CHACHA_DEV_V823_COLLECTOR_HEALTH_DEFERRED=PASS")
print("CHACHA_DEV_V823_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
