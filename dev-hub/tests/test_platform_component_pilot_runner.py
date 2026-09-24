#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))
spec=importlib.util.spec_from_file_location("platform_component_pilot_runner",BIN/"platform-component-pilot-runner.py")
assert spec and spec.loader
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

contract={
 "schema":"chacha.dev/platform-component-comparative-pilot-contract/v1",
 "contract_id":"pcp-test","dispatch_id":"d1","component_id":"central-orchestrator",
 "candidate_owner":"branch-foundry","harness_id":"real-test-harness",
 "harness_argv":["/usr/bin/python3","real-harness.py","--variant","{variant}","--artifact","{artifact_ref}","--output","{result_json}"],
 "resource_budget":{"memory_mb":128,"cpu_weight":50,"tasks_max":4,"timeout_seconds":30},
 "incumbent_artifact_ref":"git:incumbent@def","candidate_artifact_ref":"git:candidate@abc",
 "incumbent_revision":"def","candidate_revision":"abc",
 "pre_pilot_checks":{
   "independent_verification":True,"measurable_gain":True,"no_material_regression":True,
   "permission_non_escalation":True,"rollback_ready":True,"exact_revision_evidence":True,
   "logician_falsification_pass":True,"technology_watch_revalidation_pass":True,
   "real_harness_available":True
 },
 "pre_pilot_evidence_refs":["e:1","e:2"],
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

guardian_calls=[]
def guardian_provider(repo_root,run_root,phase,contract,result_status=None):
    guardian_calls.append({"phase":phase,"result_status":result_status})
    return {"verdict":"ALLOW","status":"PASS"}

with tempfile.TemporaryDirectory(prefix="platform-pilot-runner-") as td:
    out=runner.execute(contract,sentinel,ROOT,Path(td),executor,guardian_provider)

assert out["status"]=="PASS",out
assert len(calls)==2,calls
assert [x["phase"] for x in guardian_calls]==["PRE_ACTION","POST_ACTION"],guardian_calls
assert out["guardian_pre_pass"] is True and out["guardian_post_pass"] is True,out
assert str(out["guardian_pre_receipt_digest"]).startswith("sha256:"),out
assert str(out["guardian_post_receipt_digest"]).startswith("sha256:"),out
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

badpre=dict(contract);badpre["pre_pilot_checks"]={**contract["pre_pilot_checks"],"rollback_ready":False}
try:
    runner.validate_contract(badpre)
except RuntimeError as e:
    assert "PRECHECKS_INCOMPLETE" in str(e),e
else:
    raise AssertionError("pilot contract with incomplete prechecks accepted")

badc=dict(contract);badc["production_change_authorized"]=True
try:
    runner.validate_contract(badc)
except RuntimeError as e:
    assert "PRODUCTION_BOUNDARY_INVALID" in str(e),e
else:
    raise AssertionError("production-enabled pilot contract accepted")

guardian=json.loads((ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json").read_text(encoding="utf-8"))
assert any(x.get("component_id")=="platform-component-pilot-runner" for x in guardian.get("expected_components") or []),guardian
assert guardian["d1_write_budget"]["expected_max_component_heartbeat_writes_per_day"]==len(guardian["expected_components"])*12*24

core=json.loads((ROOT/"dev-hub/config/technology-core-watch.v1.json").read_text(encoding="utf-8"))
row=next(x for x in core["components"] if x["id"]=="platform-component-pilot-runner")
assert row["class"]=="verification" and row["criticality"]=="critical",row

roles=json.loads((ROOT/"dev-hub/config/guardian-role-contracts.v1.json").read_text(encoding="utf-8"))
role=next(x for x in roles["contracts"] if x["contract_id"]=="role:platform-component-pilot-runner")
assert "RUN_COMPARATIVE_PILOT" in role["allowed_actions"],role
assert {"PRODUCTION_DEPLOY","PROMOTE_COMPONENT","MODIFY_GUARDIAN_CONTRACTS","EXPAND_PERMISSIONS"}<=set(role["forbidden_actions"]),role
assert set(role["required_evidence"])=={"isolated_capsules","same_benchmark_contract","exact_artifacts","sentinel_exact_sha_pass"},role

print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_RUNNER=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_SAME_HARNESS=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_ISOLATED_SYSTEMD=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_EXACT_SENTINEL_SHA=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_PRECHECKS=ENFORCED")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_GUARDIAN_PRE_POST=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_GUARDIAN_RECEIPTS=PERSISTED")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_GUARDIAN_COVERAGE=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_CORE_WATCH=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_GUARDIAN_ROLE=PASS")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_COUNCIL_HANDOFF=YES")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_FINAL_DECISION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_PRODUCTION_CHANGE=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_PROMOTION=NO")
print("CHACHA_DEV_PLATFORM_COMPONENT_PILOT_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
