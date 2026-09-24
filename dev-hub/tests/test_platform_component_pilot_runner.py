#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))
import platform_component_pilot_runner as runner

contract={
 "schema":"chacha.dev/platform-component-comparative-pilot-contract/v1",
 "contract_id":"pcp-test","dispatch_id":"d1","component_id":"central-orchestrator",
 "candidate_owner":"branch-foundry","harness_id":"real-test-harness",
 "harness_argv":["/usr/bin/python3","real-harness.py","--variant","{variant}","--artifact","{artifact_ref}","--output","{result_json}"],
 "resource_budget":{"memory_mb":128,"cpu_weight":50,"tasks_max":4,"timeout_seconds":30},
 "incumbent_artifact_ref":"git:incumbent@def","candidate_artifact_ref":"git:candidate@abc",
 "incumbent_revision":"def","candidate_revision":"abc",
 "same_benchmark_contract":True,"isolated_ephemeral_capsules":True,
 "pilot_execution_authorized":True,"production_change_authorized":False,
 "promotion_authorized":False,"automatic_external_spend_eur":0
}
sentinel={
 "schema":"chacha.dev/sentinel-exact-sha-receipt/v1",
 "workflow_name":"ChaCha DEV Sentinel technical assurance",
 "head_sha":"abc","conclusion":"success","exact_sha_verified":True,"run_id":12345
}
calls=[]
def executor(cmd,result_path,variant,artifact_ref):
    calls.append({"cmd":cmd,"variant":variant,"artifact_ref":artifact_ref})
    metrics={
      "schema":"chacha.dev/platform-component-pilot-metrics/v1",
      "acceptance_pass":True,
      "quality_score":97 if variant=="INCUMBENT" else 99,
      "stability_score":98 if variant=="INCUMBENT" else 99,
      "error_rate":0,
      "latency_ms":30 if variant=="INCUMBENT" else 20,
      "memory_mb":72 if variant=="INCUMBENT" else 64,
      "external_spend_eur":0
    }
    result_path.write_text(json.dumps(metrics)+"\n",encoding="utf-8")
    return 0,"ok",""

with tempfile.TemporaryDirectory(prefix="platform-pilot-runner-") as td:
    out=runner.execute(contract,sentinel,ROOT,Path(td),executor)

assert out["status"]=="PASS",out
assert len(calls)==2,calls
assert calls[0]["variant"]=="INCUMBENT" and calls[1]["variant"]=="CANDIDATE",calls
assert calls[0]["cmd"][0]=="/usr/bin/systemd-run",calls[0]
assert calls[1]["cmd"][0]=="/usr/bin/systemd-run",calls[1]
assert out["same_benchmark_contract"] is True and out["isolated_ephemeral_capsules"] is True,out
assert out["comparison"]["candidate_technically_admissible_for_council_review"] is True,out
assert out["comparison"]["final_architecture_decision_made"] is False,out
assert out["council_handoff_required"] is True,out
assert out["production_change_authorized"] is False and out["promotion_authorized"] is False,out

bad=dict(sentinel);bad["head_sha"]="wrong"
try:
    runner.validate_sentinel_receipt(contract,bad)
except RuntimeError as e:
    assert "SHA_MISMATCH" in str(e),e
else:
    raise AssertionError("sentinel SHA mismatch accepted")

badc=dict(contract);badc["production_change_authorized"]=True
try:
    runner.validate_contract(badc)
except RuntimeError as e:
    assert "PRODUCTION_BOUNDARY_INVALID" in str(e),e
else:
    raise AssertionError("production-enabled pilot contract accepted")

print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_RUNNER=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_SAME_HARNESS=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_ISOLATED_SYSTEMD=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_EXACT_SENTINEL_SHA=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_COUNCIL_HANDOFF=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_FINAL_DECISION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_PRODUCTION_CHANGE=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_PROMOTION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
