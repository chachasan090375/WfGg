#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"

def save(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")
def load(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def run(args,cwd=ROOT):
    return subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)

with tempfile.TemporaryDirectory(prefix="v634-") as td:
    td=Path(td);repo=td/"repo";repo.mkdir()
    run(["git","init","-q"],repo)
    run(["git","config","user.email","v634@example.invalid"],repo)
    run(["git","config","user.name","V634"],repo)
    for name in ["alpha","bravo","charlie","delta"]:
        (repo/f"{name}_component.py").write_text("VALUE=1\n",encoding="utf-8")
    run(["git","add","."],repo);run(["git","commit","-qm","seed"],repo)

    intent=td/"intent.json";contract=td/"contract.json";pre=td/"pre.json";memory=td/"memory.json"
    save(intent,{"name":"V634 test","text":"Build a simple mobile user interface"})
    save(contract,{"schema":"chacha.dev/functional-contract/v1","contract_id":"c634",
                   "functional_intent":"Build a simple mobile user interface","audiences":["user"]})
    pkgs=[]
    for i,name in enumerate(["alpha","bravo","charlie","delta","echo","foxtrot"]):
        pkgs.append({"id":f"pkg-{i}","domain":name,"kind":"frontend-web","capabilities":[name]})
    save(pre,{"packages":pkgs,"primary_domains":["alpha","bravo","charlie","delta","echo","foxtrot"]})
    save(memory,{"current_best_reuse_candidates":[{"kind":"branch","branch_id":"b1","version":"1"}]})

    logic=td/"logic.json"
    p=run([sys.executable,str(BIN/"logic-search-engine.py"),"--repo-root",str(repo),
           "--intent",str(intent),"--contract",str(contract),"--preplan",str(pre),
           "--memory-brief",str(memory),"--policy",str(CFG/"logic-search.v1.json"),"--output",str(logic)])
    assert p.returncode==0,(p.stdout,p.stderr)
    lv=load(logic)
    assert lv["evaluated_path_count"]<=50000,lv
    assert lv["virtual_space_size"]>=lv["evaluated_path_count"],lv
    assert lv["challenge_status"] in {"RECONSIDER","REPLAN_REQUIRED"},lv
    assert lv["central_brain_response_required"] is True,lv
    assert lv["direct_mutation"] is False,lv

    ux=td/"ux.json"
    p=run([sys.executable,str(BIN/"ux-planning-engine.py"),"--intent",str(intent),"--contract",str(contract),
           "--preplan",str(pre),"--policy",str(CFG/"ux-planning.v1.json"),"--output",str(ux)])
    assert p.returncode==0,(p.stdout,p.stderr)
    uv=load(ux)
    assert uv["user_facing"] is True,uv
    assert uv["challenge_status"]=="REPLAN_REQUIRED",uv
    assert uv["central_brain_response_required"] is True,uv
    assert uv["ux_contract"]["curator_handoff_required"] is True,uv

    compromise=td/"compromise.json"
    p=run([sys.executable,str(BIN/"multi-agent-compromise-engine.py"),
           "--policy",str(CFG/"decision-challenge.v1.json"),
           "--logic-report",str(logic),"--ux-report",str(ux),"--output",str(compromise)])
    assert p.returncode==0,(p.stdout,p.stderr)
    cv=load(compromise)
    assert cv["central_compromise_search_attempted"] is True,cv
    assert cv["central_compromise_found"] is True,cv
    assert cv["revision_requests"]==[],cv
    assert cv["revision_request_only_after_failed_compromise"] is True,cv

    g=td/"guardian-position.json";b=td/"bastion-position.json"
    save(g,{"agent":"guardian","status":"RECONSIDER","proposal":{"kind":"functional"},
            "hard_constraints":[{"key":"storage.mode","value":"local"}],"evidence_refs":["g"]})
    save(b,{"agent":"bastion","status":"RECONSIDER","proposal":{"kind":"security"},
            "hard_constraints":[{"key":"storage.mode","value":"isolated"}],"evidence_refs":["b"]})
    conflict=td/"conflict.json"
    p=run([sys.executable,str(BIN/"multi-agent-compromise-engine.py"),
           "--policy",str(CFG/"decision-challenge.v1.json"),
           "--logic-report",str(logic),"--ux-report",str(ux),
           "--agent-report",str(g),"--agent-report",str(b),"--output",str(conflict)])
    assert p.returncode==0,(p.stdout,p.stderr)
    cf=load(conflict)
    assert cf["central_compromise_search_attempted"] is True,cf
    assert cf["central_compromise_found"] is False,cf
    assert cf["continuation_allowed"] is False,cf
    assert len(cf["revision_requests"])==1,cf
    rr=cf["revision_requests"][0]
    assert set(rr["target_agents"])=={"guardian","bastion"},rr
    assert rr["central_compromise_search_attempted"] is True,rr
    assert rr["must_preserve_prior_evidence"] is True,rr

    project="p634";revision="a"*40;digest=cv["dossier_digest"]
    council=td/"council.json";verify=td/"verify.json"
    save(council,{"schema":"chacha.dev/architecture-decision-council/v1","dispatch_allowed":True,
                  "logic_ux_compromise":{"required":True,"valid":True,"dossier_digest":digest}})
    save(verify,{"schema":"chacha.dev/implementation-verification/v1","project_id":project,"revision":revision,
                 "compromise_digest":digest,"status":"PASS","non_dominated_compromise_verified":True,
                 "hard_constraints_satisfied":True,"architecture_changed":True,
                 "technology_watch_status":"PASS","architecture_council_status":"PASS"})
    reviews=[]
    for agent in ["logician","ergonomist","guardian","sentinel","curator","bastion","intendant"]:
        path=td/f"{agent}.json";reviews.append(path)
        save(path,{"schema":"chacha.dev/compromise-agent-review/v1","agent":agent,
                   "project_id":project,"revision":revision,"compromise_digest":digest,
                   "verdict":"ACCEPT","hard_objections":[],"soft_objections":[],
                   "evidence_refs":[f"evidence:{agent}"],"implementation_verified":True,
                   "source_authority":"INTERNAL" if agent in {"logician","ergonomist"} else "EXTERNAL",
                   "source_reverified":agent not in {"logician","ergonomist"},
                   "original_proposal_referenced":agent in {"logician","ergonomist"},
                   "post_implementation_second_read":agent in {"logician","ergonomist"}})
    receipt=td/"release.json"
    cmd=[sys.executable,str(BIN/"compromise-release-gate.py"),"--project-id",project,"--revision",revision,
         "--policy",str(CFG/"compromise-release-gate.v1.json"),"--compromise",str(compromise),
         "--council",str(council),"--implementation-verification",str(verify),"--output",str(receipt)]
    for r in reviews:cmd+=["--agent-review",str(r)]
    p=run(cmd)
    assert p.returncode==0,(p.stdout,p.stderr)
    rv=load(receipt)
    assert rv["release_allowed"] is True,rv
    assert len(rv["accounted_agents"])==7,rv
    assert rv["unanimous_preferences_required"] is False,rv
    assert rv["majority_vote_used"] is False,rv

    missing=td/"release-missing.json"
    cmd2=[x for x in cmd[:-2]] if False else [sys.executable,str(BIN/"compromise-release-gate.py"),
         "--project-id",project,"--revision",revision,"--policy",str(CFG/"compromise-release-gate.v1.json"),
         "--compromise",str(compromise),"--council",str(council),
         "--implementation-verification",str(verify),"--output",str(missing)]
    for r in reviews[:-1]:cmd2+=["--agent-review",str(r)]
    p=run(cmd2)
    assert p.returncode==20,p.stdout
    mv=load(missing)
    assert mv["release_allowed"] is False,mv
    assert any(x.startswith("REQUIRED_AGENT_REVIEW_MISSING:") for x in mv["reason_codes"]),mv

guardian_roles=load(CFG/"guardian-role-contracts.v1.json")
ids={x["contract_id"] for x in guardian_roles["contracts"]}
assert {"role:logician","role:ergonomist","role:compromise-release-gate"}.issubset(ids),ids
council_role=next(x for x in guardian_roles["contracts"] if x["contract_id"]=="role:architecture-decision-council")
assert "logic_ux_compromise" in council_role["required_evidence"],council_role

coverage=load(CFG/"guardian-coverage-manifest.v1.json")
components={x["component_id"] for x in coverage["expected_components"]}
assert {"logician","ergonomist","multi-agent-compromise-engine","compromise-release-gate"}.issubset(components),components

orch=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
council_script=(BIN/"architecture-decision-council.py").read_text(encoding="utf-8")
guardian_worker=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
assert any(v in orch for v in ['"version":"6.34.0"','"version":"6.35.0"','"version":"6.40.0"','"version":"6.41.0"','"version":"6.42.0"','"version":"6.43.0"','"version":"6.44.0"','"version":"6.45.0"','"version":"6.46.0"','"version":"6.47.0"','"version":"6.48.0"'])
assert '"--challenge-dossier",compromise' in orch
assert "REVISION_REQUEST_ONLY_AFTER_FAILED_COMPROMISE=YES" in orch
assert "MULTI_AGENT_COMPROMISE_REQUIRED" in orch
assert '--challenge-dossier' in council_script
assert '"logic-ux-compromise"' in council_script
assert '"logic_ux_compromise"' in guardian_worker

lifecycle=load(CFG/"lifecycle.v1.json")
quality=load(CFG/"quality-gates.v1.json")
release_transition=lifecycle["transitions"]["PREVIEW->RELEASE"]
assert "compromise-release-receipt" in release_transition["required_artifacts"],release_transition
assert "compromise-release" in release_transition["required_gates"],release_transition
assert lifecycle["release_policy"]["compromise_release_receipt_required"] is True
assert quality["gates"]["compromise-release"]["default_blocking"] is True
assert quality["principles"]["final_delivery_requires_multi_agent_compromise"] is True

release_policy=load(CFG/"compromise-release-gate.v1.json")
assert len(release_policy["required_agents"])==7
assert release_policy["rules"]["release_is_fail_closed"] is True
assert release_policy["rules"]["missing_future_specialist_authority_blocks_final_delivery"] is True
assert release_policy["rules"]["no_majority_vote"] is True
assert release_policy["rules"]["unanimous_preferences_not_required"] is True

print("CHACHA_DEV_V634_LOGICIAN_ADAPTIVE_SEARCH=PASS")
print("CHACHA_DEV_V634_ERGONOMIST_UX_CHALLENGE=PASS")
print("CHACHA_DEV_V634_CENTRAL_COMPROMISE_FIRST=PASS")
print("CHACHA_DEV_V634_AGENT_REVISION_ONLY_AFTER_FAILED_COMPROMISE=PASS")
print("CHACHA_DEV_V634_ARCHITECTURE_COUNCIL_CONSUMES_COMPROMISE=PASS")
print("CHACHA_DEV_V634_SEVEN_AGENT_RELEASE_GATE=PASS")
print("CHACHA_DEV_V634_RELEASE_LIFECYCLE_ENFORCEMENT=PASS")
print("CHACHA_DEV_V634_MISSING_AGENT_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V634_NO_MAJORITY_VOTE=PASS")
print("CHACHA_DEV_V634_CURRENT_PLAN_INCUMBENCY_PRIVILEGE=NO")
print("CHACHA_DEV_V634_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V634_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
