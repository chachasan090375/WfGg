#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

central=loadmod("v831_central",ROOT/"dev-hub/bin/central-interface-controller.py")
conversation=loadmod("v831_conversation",ROOT/"dev-hub/bin/conversation-interface-agent.py")
direct=loadmod("v831_direct",ROOT/"dev-hub/bin/direct-operator-service.py")

# 1. D1 Quota classification: must return AWAITING_EXTERNAL_CONDITION, avoiding false BRAIN_UNAVAILABLE
d1_stderr="""Traceback (most recent call last):
RuntimeError: GUARDIAN_STAGE_UNAVAILABLE:specification-compiler.py:D1_ACCOUNT_QUOTA_CIRCUIT_OPEN
"""
status,next_action,decision=central.classify_orchestrator_failure("",d1_stderr)
assert status=="AWAITING_EXTERNAL_CONDITION",(status,next_action,decision)
assert next_action=="RETRY_WHEN_D1_AVAILABLE",(status,next_action,decision)
assert decision["external_dependency"]=="D1_DATABASE",decision
assert decision["reason"]=="D1_ACCOUNT_QUOTA_CIRCUIT_OPEN",decision
assert decision["retryable"] is True,decision
assert decision["authority_bypass"] is False,decision

receipt=central.make_receipt(
    "INSTRUCTION","chacha-dev-platform",status,next_action,[],decision
)
reply=conversation.compose(receipt,{"request_id":"v831-test"})
assert reply["kind"]=="WARNING",reply
assert "quota quotidien de la base d1" in reply["message"].casefold(),reply
assert "sans dépense externe" in reply["message"].casefold(),reply
assert "n’arrive pas à joindre correctement le cerveau central" not in reply["message"],reply
assert "quota d1 sera réinitialisé" in reply["message"].casefold(),reply
assert direct.should_auto_continue(receipt) is False,receipt

# 2. Daily row read limit payload classification
d1_row_read_err="RuntimeError: Failed query: Your account has exceeded D1's free tier daily row read limit."
status_rr,next_rr,decision_rr=central.classify_orchestrator_failure("",d1_row_read_err)
assert status_rr=="AWAITING_EXTERNAL_CONDITION",(status_rr,next_rr,decision_rr)
assert next_rr=="RETRY_WHEN_D1_AVAILABLE",(status_rr,next_rr,decision_rr)

# 3. Generic error preserves BRAIN_UNAVAILABLE
status_gen,next_gen,decision_gen=central.classify_orchestrator_failure("","unexpected internal crash")
assert status_gen=="BRAIN_UNAVAILABLE",(status_gen,next_gen,decision_gen)
assert next_gen=="RETRY_WHEN_BRAIN_AVAILABLE",(status_gen,next_gen,decision_gen)

# 4. Continuation contract: RUN_CONTROLLER_COMPLETE must route to domain execution continuation,
# never falling through to FRESH_CENTRAL_REORCHESTRATION (preventing loop).
central_src=(ROOT/"dev-hub/bin/central-interface-controller.py").read_text(encoding="utf-8")
assert 'prior_next in {"SCHEDULER_READY","RUN_CONTROLLER_COMPLETE"}' in central_src

print("CHACHA_DEV_V831_D1_NO_FALSE_BRAIN_UNAVAILABLE=PASS")
print("CHACHA_DEV_V831_D1_CONVERSATIONAL_EXPLANATION=PASS")
print("CHACHA_DEV_V831_D1_FAIL_CLOSED_NO_LOOP=PASS")
print("CHACHA_DEV_V831_RUN_CONTROLLER_COMPLETE_CONTINUATION=PASS")
print("CHACHA_DEV_V831_AUTOMATIC_EXTERNAL_SPEND_EUR=0")

# 5. Provider/model quota circuit: exact 429 becomes a durable no-loop external condition.
import contextlib,io,os,subprocess
pqc=loadmod("v831_provider_quota",ROOT/"dev-hub/bin/provider_quota_circuit.py")
antigravity=loadmod("v831_antigravity",ROOT/"dev-hub/adapters/antigravity-adapter.py")
runctl=loadmod("v831_runctl",ROOT/"dev-hub/bin/run-controller.py")
with tempfile.TemporaryDirectory(prefix="v831-provider-quota-") as raw:
    td=Path(raw);state=td/"provider-model-quota.json";os.environ["CHACHA_PROVIDER_QUOTA_CIRCUIT_STATE"]=str(state)
    err='''RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 167h9m10s.\n{"metadata":{"model":"gemini-3.8-flash-medium","quotaResetTimeStamp":"2026-10-04T17:53:18Z"},"reason":"QUOTA_EXHAUSTED"}'''
    row=pqc.observe_text("antigravity","gemini-3.8-flash-medium",err,"v831-test",epoch=1790534648)
    assert row and row["reason"]=="PROVIDER_MODEL_QUOTA_EXHAUSTED",row
    assert row["resume_at"]=="2026-10-04T17:53:23Z",row
    assert row["automatic_paid_upgrade"] is False and row["automatic_external_spend_eur"]==0,row
    assert pqc.blocked("antigravity","gemini-3.8-flash-medium",epoch=1790534649),row
    assert pqc.blocked("antigravity","gemini-3.8-flash-medium",epoch=row["resume_epoch"]+1) is None

# 6. Run Controller must preserve a valid semantic BLOCKED result even when adapter exit code is non-zero.
blocked_result={
  "schema":"chacha.dev/task-result/v1","project":"p831","task_id":"task:quota","status":"BLOCKED",
  "producer":"antigravity-adapter","observed_at":"2026-09-27T18:44:07Z",
  "summary":"PROVIDER_MODEL_QUOTA_EXHAUSTED","evidence":[],
  "verification":{"status":"UNVERIFIED","method":"none","verifier":"none"},"outputs":[]}
envelope={"schema":"chacha.dev/dispatch-envelope/v1","project":"p831","task":{"id":"task:quota"}}
parsed,err=runctl.parse_adapter_result(json.dumps(blocked_result).encode(),envelope,"antigravity-adapter")
assert err is None and parsed and parsed["status"]=="BLOCKED",(parsed,err)
run_src=(ROOT/"dev-hub/bin/run-controller.py").read_text(encoding="utf-8")
assert 'semantic_blocked = result_status == "BLOCKED"' in run_src
assert 'record["summary"]["blocked"] += 1' in run_src

# 7. Central orchestration converts semantic provider quota to an explicit external dependency.
with tempfile.TemporaryDirectory(prefix="v831-run-record-") as raw:
    td=Path(raw);result_path=td/"quota-result.json";result_path.write_text(json.dumps({**blocked_result,"evidence":[{"kind":"provider-quota-circuit","source":str(td/"circuit.json"),"digest":"sha256:"+"0"*64,"details":{"provider":"antigravity","model":"gemini-3.8-flash-medium","resume_at":"2026-10-04T17:53:23Z","automatic_paid_upgrade":False,"automatic_external_spend_eur":0}}]}))
    record={"waves":[{"tasks":[{"task_result":str(result_path),"status":"BLOCKED"}]}]}
    cond=central.external_condition_from_run(record)
    assert cond and cond["external_dependency"]=="AI_PROVIDER_MODEL",cond
    assert cond["resume_at"]=="2026-10-04T17:53:23Z",cond
    assert cond["automatic_paid_upgrade"] is False,cond
    receipt=central.make_receipt("CONTINUE","chacha-dev-platform","AWAITING_EXTERNAL_CONDITION","RETRY_WHEN_PROVIDER_QUOTA_AVAILABLE",[],cond)
    reply=conversation.compose(receipt,{"request_id":"v831-provider-quota"})
    assert reply["kind"]=="WARNING",reply
    assert "quota gratuit" in reply["message"].casefold(),reply
    assert "sans achat ni dépense externe" in reply["message"].casefold(),reply
    assert "2026-10-04t17:53:23z" in reply["message"].casefold(),reply
    assert direct.should_auto_continue(receipt) is False,receipt

# 8. An already-open provider circuit is surfaced before provider execution by readiness remediation.
remediation={"remediations":[{"provider":"antigravity","blockers":["PROVIDER_MODEL_QUOTA_EXHAUSTED"],"economics_attestation_refresh":{"reason_codes":["PROVIDER_MODEL_QUOTA_EXHAUSTED"],"model":"gemini-3.8-flash-medium","resume_at":"2026-10-04T17:53:23Z"}}]}
pre=central.provider_quota_condition_from_remediation(remediation)
assert pre and pre["provider_execution_started"] is False and pre["adapter_invocation_started"] is False,pre
assert pre["external_dependency"]=="AI_PROVIDER_MODEL",pre

print("CHACHA_DEV_V831_PROVIDER_MODEL_QUOTA_CIRCUIT=PASS")
print("CHACHA_DEV_V831_PROVIDER_QUOTA_NO_LOOP=PASS")
print("CHACHA_DEV_V831_SEMANTIC_BLOCK_PRESERVED=PASS")
print("CHACHA_DEV_V831_PROVIDER_QUOTA_CONVERSATION=PASS")

# 8. Dedicated V8.3.1 workflow must exist and identify the release consistently.
workflow=ROOT/".github/workflows/dev-hub-v831-safe-autonomous-resilience-and-continuation.yml"
assert workflow.is_file(),workflow
workflow_text=workflow.read_text(encoding="utf-8")
assert "ChaCha DEV V8.3.1 Safe Autonomous Resilience and Continuation" in workflow_text,workflow_text[:200]
assert "V8.0.31" not in workflow_text,workflow_text[:200]
assert "test_v831_safe_autonomous_resilience_and_continuation.py" in workflow_text

print("CHACHA_DEV_V831_PROVIDER_QUOTA_PRE_DISPATCH_BLOCK=PASS")
print("CHACHA_DEV_V831_DEDICATED_WORKFLOW_CONTRACT=PASS")
print("CHACHA_DEV_V831_AUTOMATIC_PAID_UPGRADE=FALSE")
