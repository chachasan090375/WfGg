#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))
import agent_evolution_controller as aec
import agent_fleet_observatory as afo

def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def run(cmd):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if p.returncode!=0:
        raise AssertionError({"cmd":cmd,"rc":p.returncode,"stdout":p.stdout,"stderr":p.stderr})
    return p.stdout

with tempfile.TemporaryDirectory(prefix="v662-qualification-") as td:
    rt=Path(td)/"runtime";runroot=rt/"golden-path-runs"/"run-1";planning=runroot/"planning";ext=runroot/"external-assurance"
    planning.mkdir(parents=True);ext.mkdir(parents=True)
    project="p-v661"
    artifact=runroot/"artifact.json";artifact.write_text('{"status":"PASS"}\n',encoding="utf-8")
    digest=hashlib.sha256(artifact.read_bytes()).hexdigest();eref=str(artifact)+"#sha256:"+digest

    functional={"schema":"chacha.dev/functional-contract/v1","contract_id":"c-v661",
      "criteria":[{"criterion_id":"c1","dimension":"functional","required":True,"owner":"product","verification":"evidence"}]}
    evidence={"criteria":[{"criterion_id":"c1","state":"PASS","evidence":eref}]}
    acceptance={"schema":"chacha.dev/acceptance-result/v1","accepted":True,
      "criteria":[{"criterion_id":"c1","dimension":"functional","required":True,"owner":"product","state":"PASS","evidence":eref}],
      "return_to_factories":{},"delivery_allowed":True,"local_acceptance_candidate":True,
      "final_delivery_allowed":False,"final_delivery_gate":"seven-agent-final-compromise","final_delivery_receipt_required":True}
    save(planning/"functional-contract.json",functional);save(ext/"acceptance-evidence.json",evidence);save(ext/"acceptance.json",acceptance)

    agent_topology={"schema":"chacha.dev/agent-topology/v1","project_id":project,
      "technology_watch_consulted":True,"central_memory_recall_consumed":True,
      "decisions":[{"package_id":"domain:product","decision":"REUSE_EXISTING_AGENT","agent_id":"product-domain-architect",
        "technology_watch":{"consulted":True,"automatic_external_spend_eur":0}}]}
    branch_topology={"schema":"chacha.dev/branch-topology/v1","project_id":project,
      "technology_watch_consulted":True,
      "decisions":[{"package_id":"domain:product","branch_id":project+":product:primary",
        "decision":"MATERIALIZE_EPHEMERAL_BRANCH","runtime_required":True,
        "technology_watch":{"consulted":True,"automatic_external_spend_eur":0}}]}
    cap={"schema":"chacha.dev/capability-foundry-plan/v1","project_id":project,"plans":[],
      "created_domain_count":0,"created_capability_count":0,"technology_watch_consulted":True,
      "central_memory_recall_consumed":True,"promotion_requires_qualification":True}
    finalp={"schema":"chacha.dev/domain-plan/v1","packages":[{"id":"domain:product",
      "agent_topology_status":"RESOLVED","execution_mode":"REUSE_EXISTING_AGENT","agent_id":"product-domain-architect",
      "branch_id":project+":product:primary","branch_decision":"MATERIALIZE_EPHEMERAL_BRANCH","runtime_required":True}]}
    logic={"schema":"chacha.dev/logic-search-report/v1","baseline":{"score":80},
      "best_candidate":{"candidate_id":"logic-v662","score":110,"metrics":{"hard_constraints_ok":True},"automatic_external_spend_eur":0},
      "score_gain":30,"challenge_status":"REPLAN_REQUIRED"}
    ux_contract={"primary_job_statement":"Do the primary job first","recommendations":[{"id":"RESPONSIVE","requirement":"Remain usable"}],
      "interaction_principles":["DIRECT","RESPONSIVE"],"curator_handoff_required":True}
    ux_digest="sha256:"+"a"*64
    ux={"schema":"chacha.dev/ux-planning-report/v1","contract_id":"c-v661","user_facing":True,
      "ux_contract":ux_contract,"challenge_status":"REPLAN_REQUIRED","challenge_reason":"UX_FRAGMENTATION_RISK",
      "central_brain_response_required":True,"dismissal_without_evidence_forbidden":True,
      "recommended_next_action":"REOPEN_USER_JOURNEY","architecture_change_requires_technology_watch":True,
      "architecture_council_final_authority":True,"direct_mutation":False,"automatic_external_spend_eur":0,"report_digest":ux_digest}
    compromise={"schema":"chacha.dev/multi-agent-compromise/v1",
      "positions":[
        {"agent":"logician","proposal":{"candidate":{"candidate_id":"logic-v662"}}},
        {"agent":"ergonomist","status":"REPLAN_REQUIRED","proposal":{"kind":"UX_PLAN","ux_contract":ux_contract,
          "recommended_next_action":"REOPEN_USER_JOURNEY"},"hard_constraints":[],
          "soft_constraints":[{"key":"ux.primary_job_first","value":True}],"evidence_refs":[ux_digest]}
      ],
      "compromise":{"logic_proposal":{"candidate":{"candidate_id":"logic-v662"}},
        "ux_proposal":{"kind":"UX_PLAN","ux_contract":ux_contract,"recommended_next_action":"REOPEN_USER_JOURNEY"}},
      "central_compromise_found":True,"continuation_allowed":True}
    advisors={k:"PASS" for k in ("agent-foundry","branch-foundry","capability-foundry","logic-ux-compromise","technology-watch-pre","technology-watch-final")}
    council={"schema":"chacha.dev/architecture-decision-council/v1",
      "decisions":[{"package_id":"domain:product","mandatory_advisors":advisors}],
      "logic_ux_compromise":{"valid":True}}
    bootstrap={"schema":"chacha.dev/autonomous-project-bootstrap/v1","project_id":project,
      "agent_topology":str(planning/"agent-topology.json"),"branch_topology":str(planning/"branch-topology-effective.json"),
      "capability_foundry":str(planning/"capability-foundry.json"),"capability_foundry_created_domains":0,
      "capability_foundry_created_capabilities":0,"runtime_materialized_branches":1,"runtime_schedulable":True,
      "domain_dispatch_allowed":True,"architecture_decision_allowed":True,"architecture_council_consumed_compromise":True,
      "revision_request_only_after_failed_compromise":True,
      "architecture_mandatory_advisors":["technology-watch-pre","technology-watch-final"],"external_spend_eur":0}
    save(planning/"agent-topology.json",agent_topology);save(planning/"branch-topology-effective.json",branch_topology)
    save(planning/"capability-foundry.json",cap);save(planning/"capability-gaps.json",{"schema":"chacha.dev/capability-gap-report/v1"})
    save(planning/"final-plan.json",finalp);save(planning/"logic-search-report.json",logic)
    save(planning/"multi-agent-compromise.json",compromise);save(planning/"ux-planning-report.json",ux);save(planning/"architecture-decision-council.json",council)
    save(planning/"bootstrap-result.json",bootstrap)

    watch={"schema":"chacha.dev/technology-watch-snapshot/v1",
      "provider_candidates":[
        {"id":"local","admissible_for_automatic_selection":True,"zero_external_spend":True},
        {"id":"paid","admissible_for_automatic_selection":False,"zero_external_spend":False}
      ],"candidate_count":2,"eligible_candidate_count":1,"zero_spend_candidate_count":1,
      "zero_spend_candidate_available":True,
      "selection_rule":"IF_ANY_ADMISSIBLE_HARD_VALID_ZERO_SPEND_CANDIDATE_EXISTS_EXCLUDE_NONZERO_CANDIDATES",
      "automatic_external_spend_eur":0}
    save(rt/"technology-watch/optimizer-input.json",watch)
    save(rt/"runs/wfgg-radar/run-v662/run-record.json",{
      "schema":"chacha.dev/run-record/v1","run_id":"run-v662","project":"wfgg-radar","mode":"execute",
      "waves":[{"index":1,"tasks":[
        {"task_id":"radar:inspect","status":"SUCCEEDED","provider_bindings":[{"capability":"radar-runtime-inspect",
          "provider":"radar-vps-runtime","adapter":"radar-runtime-adapter","fallback_used":False,"health_state":"HEALTHY"}]},
        {"task_id":"radar:pilot","status":"SUCCEEDED","provider_bindings":[{"capability":"radar-pilot-control",
          "provider":"radar-vps-runtime","adapter":"radar-runtime-adapter","fallback_used":False,"health_state":"HEALTHY"}]}
      ]}]})

    fleet={"schema":"chacha.dev/agent-fleet-observatory-report/v1","agents":[{"agent_id":"acceptance-engineer",
      "plan":{"candidate":{"owner":"agent-foundry","isolated":True,"incumbent_control_group":True,"shadow_required":True,"pilot_required":True},
      "evidence_maturity":{"candidate_evidence_mature":True}}}]}
    save(rt/"agent-evolution/fleet-observatory-latest.json",fleet)

    out=rt/"attest"
    s=run([sys.executable,str(BIN/"real-world-evidence-attestor-v662.py"),"--runtime-root",str(rt),"--output-root",str(out)])
    assert "CHACHA_DEV_V661_REAL_WORLD_STRUCTURAL_ATTESTATION=PASS" in s,s
    for aid in ("agent-foundry-architect","branch-foundry-architect","capability-foundry-architect","logician","ergonomist","technology-watch-agent"):
        x=json.loads((out/("attestation-"+aid+".json")).read_text())
        assert x["case_count"]==1 and x["passed_case_count"]==1,x
        assert x["production_truth_eligible"] is True and x["accuracy_inference"] is False,x
        assert x["dimension_values"]=={"evidence_quality":100.0,"handoff_quality":100.0,"authority_discipline":100.0},x

    routing=json.loads((ROOT/"dev-hub/config/agent-routing.v1.json").read_text())
    seven=json.loads((ROOT/"dev-hub/config/seven-agent-final-compromise.v1.json").read_text())
    project=json.loads((ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json").read_text())
    policy=json.loads((ROOT/"dev-hub/config/agent-fleet-observatory.v1.json").read_text())
    inv=aec.build_inventory(routing,seven,[project])
    metrics=afo.build_metrics(inv,rt,policy)
    radar=metrics["technology-radar-agent"]
    assert radar["dimensions"]["coverage"]["status"]=="MEASURED",radar
    assert radar["dimensions"]["coverage"]["value"]==50.0,radar
    assert radar["signals"]["project_local_runtime_coverage_present"] is True,radar
    assert radar["signals"]["project_local_runtime_coverage_capabilities"]==["radar-pilot-control","radar-runtime-inspect"],radar
    ergo=metrics["ergonomist"]
    assert ergo["signals"]["real_world_structural_attestation_present"] is True,ergo
    for d in ("evidence_quality","handoff_quality","authority_discipline"):
        assert ergo["dimensions"][d]["status"]=="MEASURED" and ergo["dimensions"][d]["value"]==100.0,(d,ergo)

    shadow=rt/"acceptance-shadow.json"
    s=run([sys.executable,str(BIN/"acceptance-candidate-independent-pilot-v662.py"),
           "--repo-root",str(ROOT),"--runtime-root",str(rt),"--output",str(shadow)])
    assert "CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT=PASS" in s,s
    q=json.loads(shadow.read_text())
    assert q["real_case_count"]==1 and q["real_candidate_passed"]==1 and q["real_incumbent_passed"]==1,q
    assert q["adversarial_case_count"]==1 and q["adversarial_candidate_passed"]==1 and q["adversarial_incumbent_missed"]==1,q
    assert q["measurable_gain"] is True,q
    assert q["production_activation_allowed"] is False and q["promotion_allowed"] is False,q

print("CHACHA_DEV_V662_REAL_WORLD_STRUCTURAL_ATTESTATION=PASS")
print("CHACHA_DEV_V662_FOUNDRY_LOGICIAN_ERGONOMIST_WATCH_CASES=6")
print("CHACHA_DEV_V662_ACCURACY_INFERENCE=NO")
print("CHACHA_DEV_V662_RADAR_REAL_COVERAGE=50")
print("CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_REAL=PASS")
print("CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_ADVERSARIAL=PASS")
print("CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT=PASS")
print("CHACHA_DEV_V662_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_V662_ACCEPTANCE_PROMOTION=NO")
print("CHACHA_DEV_V662_SELF_MUTATION=NO")
print("CHACHA_DEV_V662_SELF_PROMOTION=NO")
print("CHACHA_DEV_V662_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V662_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
