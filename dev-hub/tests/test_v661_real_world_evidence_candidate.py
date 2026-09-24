#!/usr/bin/env python3
from __future__ import annotations
import hashlib,importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

att=loadmod("v661_att",BIN/"real-world-evidence-attestor-v661.py")
afo=loadmod("v661_afo",BIN/"agent_fleet_observatory.py")

def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def sha_ref(p):
    return str(p)+"#sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()

with tempfile.TemporaryDirectory(prefix="v661-real-world-") as td:
    rt=Path(td);run=rt/"golden-path-runs/run-1";p=run/"planning";p.mkdir(parents=True)
    top=p/"agent-topology.json";branch=p/"branch-topology-effective.json";cap=p/"capability-foundry.json"
    gaps=p/"capability-gaps.json";finalp=p/"final-plan.json";boot=p/"bootstrap-result.json"
    council=p/"architecture-decision-council.json";logic=p/"logic-search-report.json";comp=p/"multi-agent-compromise.json"
    snap=rt/"technology-watch/optimizer-input.json"
    decision={"package_id":"domain:product","decision":"REUSE_EXISTING_AGENT","agent_id":"product-domain-architect",
              "technology_watch":{"consulted":True,"automatic_external_spend_eur":0}}
    save(top,{"schema":"chacha.dev/agent-topology/v1","project_id":"p1","technology_watch_consulted":True,
              "central_memory_recall_consumed":True,"decisions":[decision]})
    bdec={"package_id":"domain:product","branch_id":"p1:product:primary","decision":"MATERIALIZE_EPHEMERAL_BRANCH",
          "runtime_required":True,"technology_watch":{"consulted":True,"automatic_external_spend_eur":0}}
    save(branch,{"schema":"chacha.dev/branch-topology/v1","project_id":"p1","technology_watch_consulted":True,"decisions":[bdec]})
    save(cap,{"schema":"chacha.dev/capability-foundry-plan/v1","project_id":"p1","plans":[],
              "created_domain_count":0,"created_capability_count":0,"technology_watch_consulted":True,
              "central_memory_recall_consumed":True,"promotion_requires_qualification":True})
    save(gaps,{"schema":"chacha.dev/capability-gap-analysis/v1","gaps":[]})
    save(finalp,{"schema":"chacha.dev/domain-plan/v1","packages":[{
      "id":"domain:product","agent_topology_status":"RESOLVED","execution_mode":"REUSE_EXISTING_AGENT",
      "agent_id":"product-domain-architect","branch_id":"p1:product:primary",
      "branch_decision":"MATERIALIZE_EPHEMERAL_BRANCH","runtime_required":True
    }]})
    advisors={x:"PASS" for x in ("agent-foundry","branch-foundry","capability-foundry","logic-ux-compromise","technology-watch-pre","technology-watch-final")}
    save(council,{"schema":"chacha.dev/architecture-decision-council/v1","decisions":[{"mandatory_advisors":advisors}],
                  "logic_ux_compromise":{"valid":True}})
    best={"candidate_id":"logic-1","score":120.0,"metrics":{"hard_constraints_ok":True},"automatic_external_spend_eur":0}
    save(logic,{"schema":"chacha.dev/logic-search-report/v1","baseline":{"score":90.0},"best_candidate":best,
                "score_gain":30.0,"challenge_status":"REPLAN_REQUIRED"})
    save(comp,{"schema":"chacha.dev/multi-agent-compromise/v1","positions":[{"agent":"logician","proposal":{"candidate":best}}],
               "central_compromise_found":True,"continuation_allowed":True,
               "compromise":{"logic_proposal":{"candidate":best}}})
    save(boot,{"schema":"chacha.dev/autonomous-project-bootstrap/v1","project_id":"p1",
               "agent_topology":str(top),"branch_topology":str(branch),"capability_foundry":str(cap),
               "capability_foundry_created_domains":0,"capability_foundry_created_capabilities":0,
               "runtime_materialized_branches":1,"runtime_schedulable":True,"domain_dispatch_allowed":True,
               "architecture_decision_allowed":True,"architecture_council_consumed_compromise":True,
               "revision_request_only_after_failed_compromise":True,
               "architecture_mandatory_advisors":["technology-watch-pre","technology-watch-final"],
               "external_spend_eur":0})
    save(snap,{"schema":"chacha.dev/technology-watch-snapshot/v1","candidate_count":2,"eligible_candidate_count":1,
               "zero_spend_candidate_count":1,"zero_spend_candidate_available":True,
               "selection_rule":"IF_ANY_ADMISSIBLE_HARD_VALID_ZERO_SPEND_CANDIDATE_EXISTS_EXCLUDE_NONZERO_CANDIDATES",
               "automatic_external_spend_eur":0,"provider_candidates":[
                 {"admissible_for_automatic_selection":True,"zero_external_spend":True},
                 {"admissible_for_automatic_selection":False,"zero_external_spend":True}
               ]})
    out=att.build(rt,rt/"attest")
    for aid,x in out.items():
        assert x["case_count"]==1 and x["passed_case_count"]==1,(aid,x)
        assert x["dimension_values"]=={"evidence_quality":100.0,"handoff_quality":100.0,"authority_discipline":100.0},(aid,x)
        assert x["accuracy_inference"] is False and x["direct_mutation"] is False,(aid,x)

    # Production-structural ingestion must not infer accuracy.
    policy=json.loads((ROOT/"dev-hub/config/agent-fleet-observatory.v1.json").read_text())
    attest_root=rt/"agent-evolution/real-world-attestations/test";attest_root.mkdir(parents=True)
    for aid,x in out.items():save(attest_root/("attestation-"+aid+".json"),x)
    review=rt/"plans/p/automatic-finalization/rev/digest/reviews/bastion-source-reverified-review.json"
    save(review,{"schema":"chacha.dev/compromise-agent-review/v1","agent":"bastion","receipt_id":"b1","project_id":"p1",
                 "revision":"a"*40,"compromise_digest":"sha256:"+"b"*64,"verdict":"REVISE","hard_objections":["NO_SPECIALIST_EVIDENCE"],
                 "soft_objections":[],"evidence_refs":[],"implementation_verified":True,"source_authority":"EXTERNAL",
                 "source_reverified":True,"source_payload_digest":"sha256:"+"c"*64,"post_implementation_second_read":True,
                 "direct_mutation":False})
    ids=list(out)+["bastion"]
    inv={"agents":[{"agent_id":aid,"scope":"PLATFORM","capabilities":[]} for aid in ids]}
    metrics=afo.build_metrics(inv,rt,policy)
    for aid in ids:
        m=metrics[aid]
        for d in ("evidence_quality","handoff_quality","authority_discipline"):
            assert m["dimensions"][d]["status"]=="MEASURED",(aid,d,m)
        assert m["dimensions"]["accuracy"]["status"]=="UNMEASURED",(aid,m["dimensions"]["accuracy"])

    # Acceptance candidate must match a real-style valid case and remain isolated.
    arun=rt/"golden-path-runs/acceptance-real";(arun/"planning").mkdir(parents=True);(arun/"external-assurance").mkdir()
    artifact=arun/"artifact.json";artifact.write_text('{"ok":true}\n',encoding="utf-8")
    contract=arun/"planning/functional-contract.json";evidence=arun/"external-assurance/acceptance-evidence.json"
    observed=arun/"external-assurance/acceptance.json"
    save(contract,{"schema":"chacha.dev/functional-contract/v1","criteria":[{"criterion_id":"c1","dimension":"functional","required":True,"owner":"product"}]})
    save(evidence,{"criteria":[{"criterion_id":"c1","state":"PASS","evidence":sha_ref(artifact)}]})
    subprocess.run([sys.executable,str(ROOT/"dev-hub/bin/acceptance-engine.py"),"--contract",str(contract),"--evidence",str(evidence),"--output",str(observed)],check=True,capture_output=True,text=True)
    save(rt/"agent-evolution/fleet-observatory-latest.json",{"agents":[{"agent_id":"acceptance-engineer","plan":{
      "candidate":{"owner":"agent-foundry","isolated":True,"incumbent_control_group":True,"shadow_required":True,"pilot_required":True},
      "evidence_maturity":{"candidate_evidence_mature":True}
    }}]})
    qout=rt/"candidate-qualification.json"
    q=subprocess.run([sys.executable,str(BIN/"acceptance-candidate-shadow-qualifier-v661.py"),"--repo-root",str(ROOT),
                      "--runtime-root",str(rt),"--output",str(qout)],check=False,capture_output=True,text=True)
    assert q.returncode==0,(q.stdout,q.stderr)
    qx=json.load(open(qout))
    assert qx["decision"]=="ISOLATED_PILOT_ELIGIBLE_HOLD_INCUMBENT",qx
    assert qx["real_shadow_no_regression"] is True and qx["adversarial_digest_mismatch_gain"] is True,qx
    assert qx["production_activation_allowed"] is False and qx["promotion_allowed"] is False,qx

print("CHACHA_DEV_V661_REAL_WORLD_ATTESTATION=PASS")
print("CHACHA_DEV_V661_BASTION_EXTERNAL_STRUCTURAL=PASS")
print("CHACHA_DEV_V661_ACCURACY_INFERENCE=NO")
print("CHACHA_DEV_V661_ACCEPTANCE_SHADOW_NO_REGRESSION=PASS")
print("CHACHA_DEV_V661_ACCEPTANCE_ADVERSARIAL_GAIN=PASS")
print("CHACHA_DEV_V661_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_V661_SELF_MUTATION=NO")
print("CHACHA_DEV_V661_SELF_PROMOTION=NO")
print("CHACHA_DEV_V661_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V661_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
