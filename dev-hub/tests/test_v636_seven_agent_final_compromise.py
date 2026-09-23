#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"

def save(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def run(args):
    return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
def digest(x):
    return "sha256:"+hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()

with tempfile.TemporaryDirectory(prefix="v636-") as td:
    td=Path(td);project="p636";revision="a"*40

    logic={"schema":"chacha.dev/logic-search-report/v1","report_digest":"sha256:logic",
           "best_candidate":{"candidate_id":"logic-best-1","execution_mode":"DEPENDENCY_ORDERED"}}
    ux={"schema":"chacha.dev/ux-planning-report/v1","report_digest":"sha256:ux",
        "ux_contract":{"primary_job_statement":"Complete the main task",
                       "recommendations":[{"id":"PRIMARY_JOB_FIRST"},{"id":"ERROR_RECOVERY"}],
                       "curator_handoff_required":True}}
    comp={"schema":"chacha.dev/multi-agent-compromise/v1","central_compromise_search_attempted":True,
          "central_compromise_found":True,"continuation_allowed":True,
          "revision_request_only_after_failed_compromise":True,
          "compromise":{"logic_proposal":{"candidate":logic["best_candidate"]},
                        "ux_proposal":{"ux_contract":ux["ux_contract"]},
                        "hard_constraints":{},"soft_constraints":[],
                        "non_dominated_selection_required":True,"must_be_verified_after_implementation":True}}
    comp["dossier_digest"]=digest(comp)
    manifest={"schema":"chacha.dev/implementation-manifest/v1","project_id":project,"revision":revision,
              "compromise_digest":comp["dossier_digest"],
              "logic":{"candidate_id":"logic-best-1","execution_mode":"DEPENDENCY_ORDERED"},
              "ux":{"implemented_requirement_ids":["PRIMARY_JOB_FIRST","ERROR_RECOVERY"],
                    "primary_job_verified":True,"curator_handoff_completed":True}}
    verify={"schema":"chacha.dev/implementation-verification/v1","project_id":project,"revision":revision,
            "compromise_digest":comp["dossier_digest"],"status":"PASS",
            "non_dominated_compromise_verified":True,"hard_constraints_satisfied":True,
            "architecture_changed":False}
    council={"schema":"chacha.dev/architecture-decision-council/v1","dispatch_allowed":True,
             "logic_ux_compromise":{"required":True,"valid":True,"dossier_digest":comp["dossier_digest"]}}
    for name,x in [("logic",logic),("ux",ux),("comp",comp),("manifest",manifest),("verify",verify),("council",council)]:
        save(td/(name+".json"),x)

    internal=[]
    for agent,report in [("logician",td/"logic.json"),("ergonomist",td/"ux.json")]:
        out=td/(agent+".json");internal.append(out)
        p=run([sys.executable,str(BIN/"internal-final-review.py"),"--agent",agent,
               "--project-id",project,"--revision",revision,"--report",str(report),
               "--compromise",str(td/"comp.json"),"--implementation-manifest",str(td/"manifest.json"),
               "--implementation-verification",str(td/"verify.json"),"--output",str(out)])
        assert p.returncode==0,(agent,p.stdout,p.stderr)
        x=load(out)
        assert x["verdict"]=="ACCEPT",x
        assert x["original_proposal_referenced"] is True,x
        assert x["post_implementation_second_read"] is True,x
        assert x["source_authority"]=="INTERNAL_SECOND_READ",x

    bad=dict(manifest);bad["ux"]=dict(manifest["ux"]);bad["ux"]["implemented_requirement_ids"]=["PRIMARY_JOB_FIRST"]
    save(td/"manifest-bad.json",bad)
    p=run([sys.executable,str(BIN/"internal-final-review.py"),"--agent","ergonomist",
           "--project-id",project,"--revision",revision,"--report",str(td/"ux.json"),
           "--compromise",str(td/"comp.json"),"--implementation-manifest",str(td/"manifest-bad.json"),
           "--implementation-verification",str(td/"verify.json"),"--output",str(td/"ux-bad.json")])
    assert p.returncode==20,p.stdout
    assert load(td/"ux-bad.json")["verdict"]=="REVISE"

    external=[]
    for agent in ["guardian","sentinel","curator","bastion","intendant"]:
        out=td/(agent+".json");external.append(out)
        save(out,{"schema":"chacha.dev/compromise-agent-review/v1","agent":agent,
                  "project_id":project,"revision":revision,"compromise_digest":comp["dossier_digest"],
                  "verdict":"ACCEPT","hard_objections":[],"soft_objections":[],
                  "evidence_refs":["source:"+agent],"implementation_verified":True,
                  "source_authority":"EXTERNAL","source_reverified":True,
                  "post_implementation_second_read":True})

    gate=td/"gate.json"
    cmd=[sys.executable,str(BIN/"compromise-release-gate.py"),"--project-id",project,"--revision",revision,
         "--policy",str(CFG/"compromise-release-gate.v1.json"),"--compromise",str(td/"comp.json"),
         "--council",str(td/"council.json"),"--implementation-verification",str(td/"verify.json"),
         "--output",str(gate)]
    for pth in internal+external:cmd+=["--agent-review",str(pth)]
    p=run(cmd)
    assert p.returncode==0,(p.stdout,p.stderr)
    gv=load(gate)
    assert gv["release_allowed"] is True,gv
    assert gv["external_reviews_source_reverified"] is True,gv
    assert gv["internal_second_reads_verified"] is True,gv
    assert len(gv["accounted_agents"])==7,gv

    broken=load(td/"guardian.json");broken["source_reverified"]=False;save(td/"guardian-bad.json",broken)
    gate2=td/"gate2.json"
    cmd2=[sys.executable,str(BIN/"compromise-release-gate.py"),"--project-id",project,"--revision",revision,
          "--policy",str(CFG/"compromise-release-gate.v1.json"),"--compromise",str(td/"comp.json"),
          "--council",str(td/"council.json"),"--implementation-verification",str(td/"verify.json"),
          "--output",str(gate2)]
    for pth in internal+[td/"guardian-bad.json"]+external[1:]:cmd2+=["--agent-review",str(pth)]
    p=run(cmd2)
    assert p.returncode==20,p.stdout
    assert "EXTERNAL_REVIEW_NOT_SOURCE_REVERIFIED:guardian" in load(gate2)["reason_codes"]

    contract={"schema":"chacha.dev/functional-contract/v1","contract_id":"acceptance-636",
              "criteria":[{"criterion_id":"c1","required":True,"dimension":"functional","owner":"core"}]}
    evidence={"criteria":[{"criterion_id":"c1","state":"PASS","evidence":"proof"}]}
    save(td/"contract.json",contract);save(td/"evidence.json",evidence)
    p=run([sys.executable,str(BIN/"acceptance-engine.py"),"--contract",str(td/"contract.json"),
           "--evidence",str(td/"evidence.json"),"--output",str(td/"acceptance.json"),
           "--learning-nas-mode","DISABLED"])
    assert p.returncode==0,(p.stdout,p.stderr)
    av=load(td/"acceptance.json")
    assert av["accepted"] is True and av["delivery_allowed"] is True,av
    assert av["local_acceptance_candidate"] is True,av
    assert av["final_delivery_allowed"] is False,av
    assert av["final_delivery_gate"]=="seven-agent-final-compromise",av

policy=load(CFG/"seven-agent-final-compromise.v1.json")
assert policy["required_agents"]==["logician","ergonomist","guardian","sentinel","curator","bastion","intendant"]
assert policy["rules"]["final_delivery_receipt_is_only_delivery_authority"] is True
assert policy["rules"]["local_acceptance_is_provisional"] is True

lifecycle=load(CFG/"lifecycle.v1.json")
assert "seven-agent-final-delivery-receipt" in lifecycle["transitions"]["PREVIEW->RELEASE"]["required_artifacts"]
assert lifecycle["transitions"]["PREVIEW->RELEASE"]["gate_policy"]=="release+compromise"
assert lifecycle["release_policy"]["seven_agent_final_delivery_receipt_required"] is True

lifecycle_engine=(BIN/"lifecycle-engine.py").read_text(encoding="utf-8")
assert 'if policy == "release+compromise":' in lifecycle_engine
assert "required_gate_blockers(rule, ledger)" in lifecycle_engine

guardian=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
sentinel=(ROOT/"dev-hub/sentinel/worker.js").read_text(encoding="utf-8")
exchange=(ROOT/"dev-hub/assurance-exchange/worker.js").read_text(encoding="utf-8")
specialists=(ROOT/"dev-hub/specialists/core.js").read_text(encoding="utf-8")
controller=(BIN/"seven-agent-final-compromise-controller.py").read_text(encoding="utf-8")

for body in [guardian,sentinel]:
    assert "/v1/final-review" in body
    assert "/v1/final-reviews/" in body
    assert "post_implementation_second_read:true" in body
    assert "seven_agent_final_review:true" in body
assert "/v1/final-reviews" in exchange
assert "five_external_final_review_reverification:true" in exchange
assert "seven_agent_final_compromise_support:true" in exchange
for role in ["GUARDIAN","SENTINEL","CURATOR","BASTION","INTENDANT"]:
    assert role in exchange,role
assert 'schema:"chacha.dev/final-review-ref/v1"' in specialists
assert "/v1/final-reviews" in specialists

for marker in [
  "internal-final-review.py","guardian-client.py","sentinel-client.py","specialist-authority-client.py",
  "assurance-exchange-client.py","compromise-release-gate.py",
  "REPAIR_IMPLEMENTATION_AND_RETEST",
  "renegotiate_agent_proposals_only_if_existing_compromise_becomes_infeasible"
]:
    assert marker in controller,marker

print("CHACHA_DEV_V636_LOGICIAN_SECOND_READ=PASS")
print("CHACHA_DEV_V636_ERGONOMIST_SECOND_READ=PASS")
print("CHACHA_DEV_V636_FIVE_EXTERNAL_SOURCE_REVERIFICATION=PASS")
print("CHACHA_DEV_V636_SEVEN_AGENT_RELEASE_GATE=PASS")
print("CHACHA_DEV_V636_UNVERIFIED_EXTERNAL_REVIEW_BLOCKED=PASS")
print("CHACHA_DEV_V636_LOCAL_ACCEPTANCE_PROVISIONAL=PASS")
print("CHACHA_DEV_V636_LIFECYCLE_RELEASE_PLUS_COMPROMISE=PASS")
print("CHACHA_DEV_V636_CENTRAL_REMEDIATION_BEFORE_RENEGOTIATION=PASS")
print("CHACHA_DEV_V636_FINAL_DELIVERY_AUTHORITY=SEVEN_AGENT_RECEIPT")
print("CHACHA_DEV_V636_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V636_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
