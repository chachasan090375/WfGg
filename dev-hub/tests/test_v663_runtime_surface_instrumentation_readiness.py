#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile,hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))
import agent_fleet_observatory as afo
import agent_evolution_controller as aec

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def run(cmd):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if p.returncode!=0:raise AssertionError({"cmd":cmd,"rc":p.returncode,"stdout":p.stdout,"stderr":p.stderr})
    return p.stdout
def sha256(p):return "sha256:"+hashlib.sha256(Path(p).read_bytes()).hexdigest()

policy=load(CFG/"agent-fleet-observatory.v1.json")
routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
inv=aec.build_inventory(routing,seven,[project])
assert inv["agent_count"]>=35,inv
assert routing["principles"]["project_scoped_agents_must_not_enter_platform_routing"] is True
assert routing["scope_exclusions"]["technology-radar-agent"]["scope"]=="PROJECT_ONLY"
assert project["platform_global"] is False
radar=project["agents"][0]
assert radar["agent_id"]=="technology-radar-agent" and radar["scope"]=="PROJECT_ONLY"
assert radar["central_brain_role"] is False and radar["technology_watch_platform_role"] is False
assert radar["production_permission"] is False

with tempfile.TemporaryDirectory(prefix="v663-qualification-") as td:
    rt=Path(td)/"runtime"
    # Radar attribution guard: provider/adapter success alone is never agent attribution.
    run_dir=rt/"runs/wfgg-radar/run-radar";run_dir.mkdir(parents=True)
    env1=run_dir/"envelopes/t1.json";env2=run_dir/"envelopes/t2.json"
    base_task={"kind":"runtime-diagnostic","permission":"read"}
    save(env1,{"schema":"chacha.dev/dispatch-envelope/v1","task":{**base_task,"id":"t1","owner_role":"sre-observability"}})
    save(env2,{"schema":"chacha.dev/dispatch-envelope/v1","task":{**base_task,"id":"t2","owner_role":"release"}})
    def rtask(tid,cap,env):
        return {"task_id":tid,"status":"SUCCEEDED","dispatch_envelope":str(env),"attempts":1,
                "provider_bindings":[{"capability":cap,"provider":"radar-vps-runtime","adapter":"radar-runtime-adapter",
                                      "fallback_used":False,"health_state":"HEALTHY"}]}
    record={"schema":"chacha.dev/run-record/v1","run_id":"run-radar","project":"wfgg-radar",
            "waves":[{"index":1,"tasks":[rtask("t1","radar-runtime-inspect",env1),rtask("t2","radar-pilot-control",env2)]}]}
    save(run_dir/"run-record.json",record)
    m=afo.build_metrics(inv,rt,policy)["technology-radar-agent"]
    assert m["signals"]["project_local_runtime_coverage_present"] is False,m
    assert m["signals"]["project_local_runtime_coverage_capabilities"]==[],m
    assert m["dimensions"]["coverage"]["status"]=="UNMEASURED",m

    # The exact same runtime bindings may count only with explicit technology-radar-agent actor binding.
    save(env1,{"schema":"chacha.dev/dispatch-envelope/v1","task":{**base_task,"id":"t1","owner_role":"technology-radar-agent"}})
    save(env2,{"schema":"chacha.dev/dispatch-envelope/v1","task":{**base_task,"id":"t2","owner_role":"technology-radar-agent"}})
    m=afo.build_metrics(inv,rt,policy)["technology-radar-agent"]
    assert m["signals"]["project_local_runtime_coverage_present"] is True,m
    assert m["signals"]["project_local_runtime_coverage_capabilities"]==["radar-pilot-control","radar-runtime-inspect"],m
    assert m["dimensions"]["coverage"]["value"]==50.0,m

    # Contract Integrator real dynamic-contract stage.
    work=Path(td)/"work";work.mkdir()
    plan=work/"final-plan.json";contracts=work/"component-role-contracts.json";council=work/"council.json"
    rec=work/"contract-reconciliation.json";irev=work/"integration-review.json"
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
    out=run([sys.executable,str(BIN/"contract-registry.py"),"--plan",str(plan),"--component-contracts",str(contracts),"--output",str(rec)])
    assert "CONTRACTS_COMPATIBLE=YES" in out
    rv=load(rec);assert rv["compatible"] is True and rv["assembly_allowed"] is True and rv["checked_packages"]==1,rv
    out=run([sys.executable,str(BIN/"integration-architecture-review.py"),"--plan",str(plan),
             "--contract-reconciliation",str(rec),"--component-contracts",str(contracts),
             "--architecture-council",str(council),"--output",str(irev)])
    assert "INTEGRATION_READY=YES" in out
    iv=load(irev);assert iv["integration_ready"] is True and iv["linked_package_count"]==1,iv
    assert iv["decision_authority"] is False and iv["architecture_council_final_authority"] is True,iv

    # Orchestrator instrumentation contracts: these are observed only when the real stage executes.
    spec=importlib.util.spec_from_file_location("apo_v663",BIN/"autonomous-project-orchestrator.py")
    apo=importlib.util.module_from_spec(spec);spec.loader.exec_module(apo)
    assert apo._STAGE_ROLE["contract-registry.py"]=="contract-integrator"
    assert apo._STAGE_ROLE["integration-architecture-review.py"]=="integration-architect"
    assert apo._STAGE_ROLE["knowledge-compiler.py"]=="knowledge-compiler-agent"
    assert apo._STAGE_ROLE["uncertainty-resolver.py"]=="uncertainty-resolution-agent"
    assert apo._STAGE_CAPABILITIES["contract-registry.py"]==["contract-reconciliation"]
    assert "integration-design" in apo._STAGE_CAPABILITIES["integration-architecture-review.py"]

    inst=load(CFG/"assurance-agent-instrumentation.v1.json")
    target_ids={x["agent_id"] for x in inst["priority_targets"]}
    assert {"contract-integrator","integration-architect","knowledge-compiler-agent","uncertainty-resolution-agent"}<=target_ids
    assert inst["invariants"]["historical_surface_backfill_for_v663"] is False
    assert inst["invariants"]["future_surface_observation_requires_real_artifact"] is True

    # Acceptance readiness is evidence-complete, but still cannot promote.
    acc_rt=Path(td)/"acceptance-runtime"
    incumbent=ROOT/"dev-hub/bin/acceptance-engine.py"
    candidate_id=load(ROOT/"dev-hub/candidates/acceptance-engineer/v661/candidate-manifest.json")["candidate_id"]
    pilot=acc_rt/"agent-evolution/candidate-qualifications/acceptance-engineer/v662/independent-pilot.json"
    save(pilot,{"schema":"chacha.dev/acceptance-candidate-independent-pilot/v1","candidate_id":candidate_id,
                "incumbent_digest":sha256(incumbent),"real_case_count":3,"real_candidate_passed":3,
                "adversarial_case_count":3,"adversarial_candidate_passed":3,"measurable_gain":True,
                "decision":"INDEPENDENT_ISOLATED_PILOT_PASS_HOLD_INCUMBENT","isolated":True,
                "incumbent_control_group":True,"production_activation_allowed":False,"promotion_allowed":False,
                "technology_watch_revalidation_required":True,"logician_falsification_required":True,
                "guardian_required":True,"sentinel_required":True,"architecture_council_final_authority":True})
    save(acc_rt/"agent-evolution/fleet-observatory-latest.json",{"agents":[{
      "agent_id":"acceptance-engineer","plan":{"candidate":{"owner":"agent-foundry","isolated":True,"incumbent_control_group":True}}
    }]})
    guardian=Path(td)/"guardian.json";watch=Path(td)/"watch.json";runs=Path(td)/"runs.json"
    save(guardian,{"all_hooks_active":True});save(watch,{"state":"FRESH","fresh":True})
    revision="a"*40
    save(runs,{"workflow_runs":[
      {"name":"ChaCha DEV Sentinel technical assurance","head_sha":revision,"status":"completed","conclusion":"success"},
      {"name":"ChaCha DEV V6.63 runtime surface instrumentation and Acceptance readiness qualification","head_sha":revision,"status":"completed","conclusion":"success"}
    ]})
    ready=Path(td)/"readiness.json"
    out=run([sys.executable,str(BIN/"acceptance-candidate-promotion-readiness-v663.py"),
             "--repo-root",str(ROOT),"--runtime-root",str(acc_rt),"--revision",revision,
             "--guardian-coverage",str(guardian),"--technology-watch-status",str(watch),
             "--github-runs-json",str(runs),"--output",str(ready)])
    assert "CHACHA_DEV_V663_ACCEPTANCE_READINESS=PASS" in out,out
    rd=load(ready)
    assert rd["decision"]=="READY_FOR_ARCHITECTURE_COUNCIL_REVIEW_HOLD_INCUMBENT",rd
    assert rd["evidence_complete_for_review"] is True,rd
    assert rd["architecture_council_approval_present"] is False,rd
    assert rd["human_explicit_promotion_approval_present"] is False,rd
    assert rd["production_activation_allowed"] is False and rd["promotion_allowed"] is False,rd

print("CHACHA_DEV_V663_RADAR_PROJECT_ATTRIBUTION_GUARD=PASS")
print("CHACHA_DEV_V663_RADAR_SRE_RELEASE_CREDIT=NO")
print("CHACHA_DEV_V663_CONTRACT_INTEGRATOR_RUNTIME_STAGE=PASS")
print("CHACHA_DEV_V663_INTEGRATION_ARCHITECT_RUNTIME_STAGE=PASS")
print("CHACHA_DEV_V663_MISSING_SURFACE_INSTRUMENTATION=PASS")
print("CHACHA_DEV_V663_HISTORICAL_SURFACE_BACKFILL=NO")
print("CHACHA_DEV_V663_ACCEPTANCE_READINESS=PASS")
print("CHACHA_DEV_V663_ACCEPTANCE_ARCHITECTURE_COUNCIL_APPROVAL=NO")
print("CHACHA_DEV_V663_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_V663_ACCEPTANCE_PROMOTION=NO")
print("CHACHA_DEV_V663_SELF_MUTATION=NO")
print("CHACHA_DEV_V663_SELF_PROMOTION=NO")
print("CHACHA_DEV_V663_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V663_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
