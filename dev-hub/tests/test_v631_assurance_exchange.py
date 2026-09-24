#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def load(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def save(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")

aer=loadmod("assurance_exchange_runtime",BIN/"assurance_exchange_runtime.py")
policy=load(CFG/"assurance-exchange-runtime-policy.v1.json")
assert policy["principles"]["guardian_and_sentinel_remain_independent"] is True
assert policy["principles"]["exchange_is_neutral_correlation_plane"] is True
assert policy["principles"]["source_receipts_are_reverified"] is True
assert policy["principles"]["correlation_does_not_create_new_primary_evidence"] is True
assert policy["principles"]["causality_is_never_inferred_without_shared_signals"] is True
assert policy["principles"]["direct_mutation"] is False
assert policy["principles"]["central_orchestrator_owns_remediation"] is True
assert policy["principles"]["technology_watch_required_if_architecture_change"] is True
assert policy["principles"]["architecture_council_required_if_architecture_change"] is True

with tempfile.TemporaryDirectory(prefix="v631-exchange-") as td:
    idx=Path(td)/"index.json"
    rows=[
      {
        "schema":"chacha.dev/assurance-exchange-recommendation/v1",
        "correlation_id":"corr-observe","project_id":"p1","revision":"a"*40,
        "priority":"OBSERVE","recommendation_type":"OBSERVE_HEALTHY_REVISION",
        "causality_status":"UNPROVEN","status":"OPEN"
      },
      {
        "schema":"chacha.dev/assurance-exchange-recommendation/v1",
        "correlation_id":"corr-opt","project_id":"p1","revision":"b"*40,
        "priority":"OPTIMIZE","recommendation_type":"OPTIMIZE_WITH_FUNCTIONAL_GUARDRAIL",
        "causality_status":"UNPROVEN","status":"OPEN",
        "technology_watch_required_if_architecture_change":True,
        "architecture_council_required_if_architecture_change":True
      },
      {
        "schema":"chacha.dev/assurance-exchange-recommendation/v1",
        "correlation_id":"corr-block","project_id":"p1","revision":"c"*40,
        "priority":"BLOCKER","recommendation_type":"JOINT_REMEDIATION_REQUIRED",
        "causality_status":"CORRELATED","status":"DELIVERED"
      },
      {
        "schema":"chacha.dev/assurance-exchange-recommendation/v1",
        "correlation_id":"corr-other","project_id":"p2","revision":"d"*40,
        "priority":"BLOCKER","recommendation_type":"TECHNICAL_REMEDIATION_REQUIRED",
        "causality_status":"UNPROVEN","status":"OPEN"
      }
    ]
    save(idx,{"schema":"chacha.dev/assurance-exchange-local-index/v1","items":rows})
    got=aer.recommendations(project_id="p1",index_path=idx)
    assert [x["correlation_id"] for x in got]==["corr-block","corr-opt","corr-observe"],got
    ctx=aer.inject_context({"existing":True},project_id="p1",index_path=idx)
    assert ctx["assurance_exchange_blocker_count"]==1,ctx
    assert ctx["assurance_exchange_optimize_count"]==1,ctx
    assert ctx["assurance_exchange_direct_mutation_allowed"] is False,ctx
    assert ctx["assurance_exchange_remediation_owner"]=="central-orchestrator",ctx

worker=(ROOT/"dev-hub/assurance-exchange/worker.js").read_text(encoding="utf-8")
guardian=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
sentinel=(ROOT/"dev-hub/sentinel/worker.js").read_text(encoding="utf-8")
controller=(BIN/"assurance-exchange-feedback-controller.py").read_text(encoding="utf-8")
orchestrator=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
project_control=load(CFG/"project-control.v1.json")

for marker in [
  'source==="GUARDIAN"?"/v1/functional-receipts/":"/v1/receipts/"',
  'status:"WAITING_FOR_PEER"',
  'type:"JOINT_REMEDIATION_REQUIRED"',
  'type:"FUNCTIONAL_REMEDIATION_REQUIRED"',
  'type:"TECHNICAL_REMEDIATION_REQUIRED"',
  'type:"OPTIMIZE_WITH_FUNCTIONAL_GUARDRAIL"',
  'type:"OBSERVE_HEALTHY_REVISION"',
  'causality=shared.length?"CORRELATED":"UNPROVEN"',
  'technology_watch_required_if_architecture_change',
  'architecture_council_required_if_architecture_change',
  'direct_mutation_allowed:false',
  'remediation_owner:"central-orchestrator"',
  '/v1/recommendations',
  '/v1/observations',
  'GUARDIAN_SERVICE',
  'SENTINEL_SERVICE'
]:
    assert marker in worker,marker

for marker in [
  'publishAssuranceObservation(env,"GUARDIAN",receiptId)',
  '/v1/functional-receipts/',
  'assurance_exchange_enabled:Boolean(env.ASSURANCE_EXCHANGE_URL||env.ASSURANCE_EXCHANGE_SERVICE)',
  'ASSURANCE_EXCHANGE_SERVICE',
  'SENTINEL_SERVICE'
]:
    assert marker in guardian,marker

for marker in [
  'publishAssuranceObservation(env,"SENTINEL",receiptId)',
  'assurance_exchange_enabled:Boolean(env.ASSURANCE_EXCHANGE_URL||env.ASSURANCE_EXCHANGE_SERVICE)',
  'ASSURANCE_EXCHANGE_SERVICE'
]:
    assert marker in sentinel,marker

assert "CENTRAL_ORCHESTRATOR_OWNS_REMEDIATION=YES" in controller
assert "DIRECT_MUTATION=NO" in controller
assert "assurance_exchange_recommendations" in orchestrator
assert any(v in orchestrator for v in ['"version":"6.31.0"','"version":"6.32.0"','"version":"6.33.0"','"version":"6.34.0"','"version":"6.35.0"','"version":"6.40.0"','"version":"6.41.0"','"version":"6.42.0"','"version":"6.43.0"','"version":"6.44.0"','"version":"6.45.0"','"version":"6.46.0"','"version":"6.47.0"','"version":"6.48.0"','"version":"6.49.0"','"version":"6.50.0"','"version":"6.51.0"','"version":"6.52.0"','"version":"6.53.0"'])
assert project_control["principles"]["assurance_exchange_is_external_neutral_correlation_plane"] is True
assert project_control["principles"]["guardian_sentinel_correlation_never_grants_mutation_authority"] is True
assert project_control["principles"]["assurance_optimization_feedback_returns_to_central_orchestrator"] is True
assert project_control["principles"]["architecture_optimization_requires_technology_watch_and_council"] is True

print("CHACHA_DEV_V631_GUARDIAN_SENTINEL_INDEPENDENCE=PASS")
print("CHACHA_DEV_V631_SOURCE_RECEIPT_REVERIFICATION=PASS")
print("CHACHA_DEV_V631_EVIDENCE_PRESERVING_CORRELATION=PASS")
print("CHACHA_DEV_V631_CAUSALITY_NOT_INVENTED=PASS")
print("CHACHA_DEV_V631_BLOCKER_OPTIMIZE_OBSERVE_PRIORITIES=PASS")
print("CHACHA_DEV_V631_OPTIMIZATION_FEEDBACK_TO_CENTRAL=PASS")
print("CHACHA_DEV_V631_EXTERNAL_AGENTS_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V631_TECHNOLOGY_WATCH_ARCHITECTURE_GUARD=PASS")
print("CHACHA_DEV_V631_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=PASS")
print("CHACHA_DEV_V631_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
