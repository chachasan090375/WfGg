#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,hashlib,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
apo=loadmod("apo_v664",BIN/"autonomous-project-orchestrator.py")
afo=loadmod("afo_v664",BIN/"agent_fleet_observatory.py")

def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def run(cmd):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if p.returncode!=0:raise AssertionError({"cmd":cmd,"rc":p.returncode,"stdout":p.stdout,"stderr":p.stderr})
    return p.stdout
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

with tempfile.TemporaryDirectory(prefix="v664-qualification-") as td:
    td=Path(td)
    # Exact stage evidence payload: project binding + artifact digest.
    contract_out=td/"contract-reconciliation.json";save(contract_out,{"schema":"chacha.dev/contract-reconciliation/v1","compatible":True})
    integration_out=td/"integration-review.json";save(integration_out,{"schema":"chacha.dev/integration-architecture-review/v1","integration_ready":True})
    rev="a"*40
    ce=apo._stage_observation_payload(
      Path("contract-registry.py"),
      ["--project-id","v664-real-project","--output",str(contract_out)],
      "contract-action","contract-integrator",0,rev)
    ie=apo._stage_observation_payload(
      Path("integration-architecture-review.py"),
      ["--project-id","v664-real-project","--output",str(integration_out)],
      "integration-action","integration-architect",0,rev)
    assert ce["project_id"]=="v664-real-project" and ce["revision"]==rev,ce
    assert ce["capabilities"]==["contract-reconciliation"],ce
    assert str(contract_out)+"#sha256:"+sha(contract_out) in ce["evidence_refs"],ce
    assert ie["project_id"]=="v664-real-project" and ie["revision"]==rev,ie
    assert ie["capabilities"]==["integration-design","api-contract-review"],ie
    assert str(integration_out)+"#sha256:"+sha(integration_out) in ie["evidence_refs"],ie

    # Observatory: activity may measure coverage/robustness/efficiency only, never accuracy.
    old_read=afo.aob.read_events
    afo.aob.read_events=lambda runtime_root:[ce,ie]
    try:
        inv={"agents":[
          {"agent_id":"contract-integrator","scope":"PLATFORM","capabilities":["contract-reconciliation","api-contract-review","integration-design"]},
          {"agent_id":"integration-architect","scope":"PLATFORM","capabilities":["integration-design","api-contract-review","acceptance-criteria"]}
        ]}
        policy={"observation_bus":{"trusted_observed_sources":["central-orchestrator"]}}
        metrics=afo.build_metrics(inv,td/"runtime",policy)
    finally:
        afo.aob.read_events=old_read
    cm=metrics["contract-integrator"];im=metrics["integration-architect"]
    assert cm["dimensions"]["coverage"]["value"]==33.3,cm
    assert cm["dimensions"]["robustness"]["value"]==100.0 and cm["dimensions"]["efficiency"]["value"]==100.0,cm
    assert cm["dimensions"]["accuracy"]["status"]=="UNMEASURED",cm
    assert im["dimensions"]["coverage"]["value"]==66.7,im
    assert im["dimensions"]["robustness"]["value"]==100.0 and im["dimensions"]["efficiency"]["value"]==100.0,im
    assert im["dimensions"]["accuracy"]["status"]=="UNMEASURED",im

    # Real stage executables preserve project identity and remain non-authoritative.
    plan=td/"plan.json";contracts=td/"contracts.json";council=td/"council.json";rec=td/"rec.json";irev=td/"irev.json"
    save(plan,{"schema":"chacha.dev/domain-plan/v1","dispatch_allowed":True,
               "packages":[{"id":"domain:development","runtime_required":True,"branch_id":"p:development:primary",
                            "capabilities":["integration-design","api-contract-review"]}]})
    save(contracts,{"schema":"chacha.dev/dynamic-component-role-contract-batch/v1","contracts":[{
      "schema":"chacha.dev/dynamic-component-role-contract/v1","component_kind":"branch",
      "contract_id":"branch:p:development:primary","component_id":"p:development:primary","package_id":"domain:development",
      "allowed_capabilities":["integration-design","api-contract-review"],"production_permissions_allowed":False,
      "automatic_external_spend_eur":0
    }]})
    save(council,{"schema":"chacha.dev/architecture-decision-council/v1","dispatch_allowed":True})
    run([sys.executable,str(BIN/"contract-registry.py"),"--plan",str(plan),"--component-contracts",str(contracts),
         "--project-id","v664-real-project","--output",str(rec)])
    rv=load(rec);assert rv["project_id"]=="v664-real-project" and rv["compatible"] is True,rv
    run([sys.executable,str(BIN/"integration-architecture-review.py"),"--plan",str(plan),
         "--contract-reconciliation",str(rec),"--component-contracts",str(contracts),
         "--architecture-council",str(council),"--project-id","v664-real-project","--output",str(irev)])
    iv=load(irev)
    assert iv["project_id"]=="v664-real-project" and iv["integration_ready"] is True,iv
    assert iv["decision_authority"] is False and iv["architecture_council_final_authority"] is True,iv

    # Architecture Council candidate review gate: technical admissibility never equals promotion.
    manifest=load(ROOT/"dev-hub/candidates/acceptance-engineer/v661/candidate-manifest.json")
    readiness=td/"readiness.json";watch=td/"watch.json";runs=td/"runs.json";review=td/"review.json"
    save(readiness,{
      "schema":"chacha.dev/acceptance-candidate-promotion-readiness/v1",
      "candidate_id":manifest["candidate_id"],"owner":"agent-foundry",
      "evidence_complete_for_review":True,"decision":"READY_FOR_ARCHITECTURE_COUNCIL_REVIEW_HOLD_INCUMBENT",
      "measurable_gain_verified":True,"guardian_all_hooks_active":True,"sentinel_exact_revision_success":True,
      "technology_watch_fresh":True,"logician_falsification_satisfied":True,
      "production_entrypoint_changed":False,"human_explicit_promotion_approval_present":False,
      "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
      "automatic_external_spend_eur":0
    })
    save(watch,{"state":"FRESH","fresh":True})
    save(runs,{"workflow_runs":[
      {"name":"ChaCha DEV Sentinel technical assurance","head_sha":rev,"status":"completed","conclusion":"success"},
      {"name":"ChaCha DEV V6.64 real instrumented project and Acceptance Council gate qualification","head_sha":rev,"status":"completed","conclusion":"success"}
    ]})
    out=run([sys.executable,str(BIN/"architecture-council-agent-candidate-review-v664.py"),
             "--repo-root",str(ROOT),"--runtime-root",str(td/"runtime"),"--readiness",str(readiness),
             "--revision",rev,"--technology-watch-status",str(watch),"--github-runs-json",str(runs),
             "--output",str(review)])
    assert "CHACHA_DEV_V664_ACCEPTANCE_ARCHITECTURE_COUNCIL_REVIEW=PASS" in out,out
    rr=load(review)
    assert rr["decision"]=="TECHNICALLY_ADMISSIBLE_AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL",rr
    assert rr["architecture_council_review_complete"] is True and rr["architecture_council_technical_admissibility"] is True,rr
    assert rr["architecture_council_promotion_approval_present"] is False,rr
    assert rr["human_explicit_promotion_approval_present"] is False,rr
    assert rr["production_activation_allowed"] is False and rr["promotion_allowed"] is False,rr
    assert rr["next_action"]=="AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL",rr

    council_policy=load(CFG/"architecture-decision-council.v1.json")
    cp=council_policy["agent_candidate_review"]
    assert cp["architecture_council_may_auto_promote"] is False
    assert cp["explicit_human_promotion_approval_required"] is True
    assert cp["default_action_without_human_approval"]=="HOLD_INCUMBENT"

    radar=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
    ra=radar["agents"][0]
    assert ra["agent_id"]=="technology-radar-agent" and ra["scope"]=="PROJECT_ONLY"
    assert ra["central_brain_role"] is False and ra["technology_watch_platform_role"] is False
    assert ra["production_permission"] is False

src=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert any(v in src for v in ('"version":"6.64.0"','"version":"7.0.0"','"version":"7.1.0"','"version":"7.2.0"','"version":"7.3.0"','"version":"7.8.0"')),src[-12000:]

print("CHACHA_DEV_V664_PROJECT_BOUND_STAGE_EVIDENCE=PASS")
print("CHACHA_DEV_V664_CONTRACT_INTEGRATOR_OBSERVATION=PASS")
print("CHACHA_DEV_V664_INTEGRATION_ARCHITECT_OBSERVATION=PASS")
print("CHACHA_DEV_V664_ACTIVITY_ACCURACY_INFERENCE=NO")
print("CHACHA_DEV_V664_ACCEPTANCE_ARCHITECTURE_COUNCIL_REVIEW=PASS")
print("CHACHA_DEV_V664_ACCEPTANCE_TECHNICAL_ADMISSIBILITY=PASS")
print("CHACHA_DEV_V664_HUMAN_PROMOTION_APPROVAL_PRESENT=NO")
print("CHACHA_DEV_V664_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_V664_ACCEPTANCE_PROMOTION=NO")
print("CHACHA_DEV_V664_RADAR_PROJECT_ONLY=PASS")
print("CHACHA_DEV_V664_SELF_MUTATION=NO")
print("CHACHA_DEV_V664_SELF_PROMOTION=NO")
print("CHACHA_DEV_V664_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V664_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
