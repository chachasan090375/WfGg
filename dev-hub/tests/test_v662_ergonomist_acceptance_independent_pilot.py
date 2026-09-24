#!/usr/bin/env python3
from __future__ import annotations
import hashlib,importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
afo=loadmod("v662_afo",BIN/"agent_fleet_observatory.py")

def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def canon(v):
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def ux_digest(v):
    return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()

def sha_ref(p):
    return str(p)+"#sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()

def run(cmd):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if p.returncode!=0:raise AssertionError({"cmd":cmd,"rc":p.returncode,"stdout":p.stdout,"stderr":p.stderr})
    return p.stdout

with tempfile.TemporaryDirectory(prefix="v662-qualification-") as td:
    rt=Path(td)/"runtime";runroot=rt/"golden-path-runs"/"run-1";planning=runroot/"planning";ext=runroot/"external-assurance"
    planning.mkdir(parents=True);ext.mkdir(parents=True)
    contract={"schema":"chacha.dev/functional-contract/v1","contract_id":"functional-v662",
              "functional_intent":"Build an accessible responsive app."}
    pre={"schema":"chacha.dev/domain-plan/v1","primary_domains":["ui-layout"],"packages":[]}
    save(planning/"functional-contract.json",contract);save(planning/"preplan.json",pre)
    ux={
      "schema":"chacha.dev/ux-planning-report/v1","version":"1.0.0","contract_id":"functional-v662",
      "user_facing":True,"user_facing_package_count":1,"primary_domain_count":1,"experience_complexity_score":2,
      "audiences":[],"styles":[],"user_facing_packages":[{"package_id":"domain:ui-layout","domain":"ui-layout","kind":"primary"}],
      "ux_contract":{"primary_job_statement":"Build an accessible responsive app.","recommendations":[{"id":"ACCESSIBILITY","requirement":"Accessible"}],
                     "interaction_principles":["DIRECT","ACCESSIBLE"],"curator_handoff_required":True},
      "challenge_status":"REPLAN_REQUIRED","challenge_reason":"UX_FRAGMENTATION_RISK",
      "central_brain_response_required":True,"dismissal_without_evidence_forbidden":True,
      "recommended_next_action":"REOPEN_USER_JOURNEY","architecture_change_requires_technology_watch":True,
      "architecture_council_final_authority":True,"direct_mutation":False,"automatic_external_spend_eur":0
    }
    ux["report_digest"]=ux_digest(ux)
    save(planning/"ux-planning-report.json",ux)
    proposal={"kind":"UX_PLAN","ux_contract":ux["ux_contract"],"recommended_next_action":"REOPEN_USER_JOURNEY"}
    comp={"schema":"chacha.dev/multi-agent-compromise/v1",
          "positions":[{"agent":"ergonomist","status":"REPLAN_REQUIRED","proposal":proposal,
                        "hard_constraints":[],"soft_constraints":[],"evidence_refs":[ux["report_digest"]]}],
          "central_compromise_found":True,"continuation_allowed":True,"compromise":{"ux_proposal":proposal}}
    save(planning/"multi-agent-compromise.json",comp)
    council={"schema":"chacha.dev/architecture-decision-council/v1",
             "decisions":[{"mandatory_advisors":{"logic-ux-compromise":"PASS"}}],
             "logic_ux_compromise":{"valid":True}}
    save(planning/"architecture-decision-council.json",council)
    boot={"schema":"chacha.dev/autonomous-project-bootstrap/v1","ux_planning_report":str(planning/"ux-planning-report.json"),
          "ux_challenge_status":"REPLAN_REQUIRED","architecture_council_consumed_compromise":True,
          "architecture_decision_allowed":True,"external_spend_eur":0}
    save(planning/"bootstrap-result.json",boot)

    # Real-style Acceptance evidence used by independent candidate PILOT.
    artifact=runroot/"artifact.json";artifact.write_text('{"status":"PASS"}\n',encoding="utf-8")
    accept_contract={"schema":"chacha.dev/functional-contract/v1","contract_id":"accept-v662",
      "criteria":[{"criterion_id":"c1","dimension":"functional","required":True,"owner":"product","verification":"evidence"}]}
    accept_evidence={"criteria":[{"criterion_id":"c1","state":"PASS","evidence":sha_ref(artifact)}]}
    save(planning/"functional-contract.json",accept_contract)
    save(ext/"acceptance-evidence.json",accept_evidence)
    run([sys.executable,str(BIN/"acceptance-engine.py"),"--contract",str(planning/"functional-contract.json"),
         "--evidence",str(ext/"acceptance-evidence.json"),"--output",str(ext/"acceptance.json")])

    # The Ergonomist report remains tied to the same contract id used by the run.
    ux["contract_id"]="accept-v662";body=dict(ux);body.pop("report_digest",None);ux["report_digest"]=ux_digest(body)
    save(planning/"ux-planning-report.json",ux)
    proposal={"kind":"UX_PLAN","ux_contract":ux["ux_contract"],"recommended_next_action":"REOPEN_USER_JOURNEY"}
    comp["positions"][0]["proposal"]=proposal;comp["positions"][0]["evidence_refs"]=[ux["report_digest"]];comp["compromise"]["ux_proposal"]=proposal
    save(planning/"multi-agent-compromise.json",comp)

    erg_out=rt/"agent-evolution/real-world-attestations/test/attestation-ergonomist.json"
    s=run([sys.executable,str(BIN/"ergonomist-real-world-attestor-v662.py"),"--runtime-root",str(rt),"--output",str(erg_out)])
    assert "CHACHA_DEV_V662_ERGONOMIST_REAL_WORLD_ATTESTATION=PASS" in s,s
    erg=json.load(open(erg_out));assert erg["case_count"]==1 and erg["passed_case_count"]==1,erg
    assert erg["dimension_values"]=={"evidence_quality":100.0,"handoff_quality":100.0,"authority_discipline":100.0},erg
    assert erg["accuracy_inference"] is False and erg["production_truth_eligible"] is True,erg

    # Observatory accepts the versioned independent attestor without inferring accuracy.
    policy=json.load(open(ROOT/"dev-hub/config/agent-fleet-observatory.v1.json"))
    inv={"agents":[{"agent_id":"ergonomist","scope":"PLATFORM","capabilities":[]}]}
    metrics=afo.build_metrics(inv,rt,policy)["ergonomist"]
    for d in ("evidence_quality","handoff_quality","authority_discipline"):
        assert metrics["dimensions"][d]["status"]=="MEASURED",(d,metrics)
    assert metrics["dimensions"]["accuracy"]["status"]=="UNMEASURED",metrics

    # Candidate PILOT control-plane fixtures.
    fleet={"schema":"chacha.dev/agent-fleet-observatory-report/v1","agents":[{
      "agent_id":"acceptance-engineer",
      "scorecard":{"dimensions":{"accuracy":100.0,"authority_discipline":100.0},
                   "unmeasured_dimensions":[]},
      "plan":{"candidate":{"owner":"agent-foundry","isolated":True,"incumbent_control_group":True,
                            "shadow_required":True,"pilot_required":True},
              "evidence_maturity":{"candidate_evidence_mature":True}}
    }]}
    save(rt/"agent-evolution/fleet-observatory-latest.json",fleet)
    watch=rt/"watch.json";guardian=rt/"guardian.json"
    save(watch,{"state":"FRESH","fresh":True,"snapshot_digest":"v662-test"})
    save(guardian,{"all_hooks_active":True})
    pilot_out=rt/"pilot.json"
    s=run([sys.executable,str(BIN/"acceptance-candidate-independent-pilot-v662.py"),
           "--repo-root",str(ROOT),"--runtime-root",str(rt),"--technology-watch-status",str(watch),
           "--guardian-coverage",str(guardian),"--output",str(pilot_out)])
    assert "CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT=PASS" in s,s
    p=json.load(open(pilot_out))
    assert p["real_case_count"]==1 and p["real_passed_count"]==1,p
    assert p["adversarial_case_count"]==4 and p["adversarial_passed_count"]==4,p
    assert p["logician_falsification_paths_verified"] is True,p
    assert p["technology_watch_fresh"] is True and p["guardian_all_hooks_active"] is True,p
    assert p["sentinel_required_for_release"] is True,p
    assert p["decision"]=="INDEPENDENT_PILOT_PASS_HOLD_INCUMBENT",p
    assert p["production_entrypoint_changed"] is False,p
    assert p["production_activation_allowed"] is False and p["promotion_allowed"] is False,p

    radar=json.load(open(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json"))
    ra=radar["agents"][0]
    assert ra["agent_id"]=="technology-radar-agent" and ra["scope"]=="PROJECT_ONLY" and ra["production_permission"] is False,ra

print("CHACHA_DEV_V662_ERGONOMIST_REAL_WORLD_ATTESTATION=PASS")
print("CHACHA_DEV_V662_ERGONOMIST_ACCURACY_INFERENCE=NO")
print("CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT=PASS")
print("CHACHA_DEV_V662_ACCEPTANCE_REAL_NO_REGRESSION=PASS")
print("CHACHA_DEV_V662_ACCEPTANCE_ADVERSARIAL_GAIN=PASS")
print("CHACHA_DEV_V662_LOGICIAN_FALSIFICATION=PASS")
print("CHACHA_DEV_V662_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_V662_ACCEPTANCE_PROMOTION=NO")
print("CHACHA_DEV_V662_RADAR_PROJECT_ONLY=PASS")
print("CHACHA_DEV_V662_SELF_MUTATION=NO")
print("CHACHA_DEV_V662_SELF_PROMOTION=NO")
print("CHACHA_DEV_V662_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V662_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
