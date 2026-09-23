#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,os,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def load(p:Path):
    return json.loads(p.read_text(encoding="utf-8"))

def save(p:Path,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

def run(args,expect=0,env=None):
    p=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,env=env)
    assert p.returncode==expect,(args,p.returncode,p.stdout,p.stderr)
    return p

spec=importlib.util.spec_from_file_location("v627_verified_learning",BIN/"verified-evidence-learning.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

with tempfile.TemporaryDirectory(prefix="v627-verified-evidence-learning-") as td:
    td=Path(td)
    graph=td/"graph.json";result=td/"result.json";ledger=td/"ledger.json"
    outbox=td/"outbox";state=td/"state";markers=td/"markers"
    lineage={"schema":"chacha.dev/component-lineage/v1","components":[
      {"kind":"agent","component_id":"v627-agent","version":"7"},
      {"kind":"branch","component_id":"v627-branch","version":"4"}
    ]}
    save(graph,{
      "schema":"chacha.dev/task-graph/v1","project":"p-v627","transition":"VERIFY->PREVIEW",
      "tasks":[{
        "id":"artifact:test-result","kind":"artifact","owner_role":"testing","permission":"read",
        "depends_on":[],"outputs":[{"type":"artifact","id":"test-result"}],
        "verification":{"mode":"machine","self_certification_allowed":False}
      }]
    })
    save(result,{
      "schema":"chacha.dev/task-result/v1","project":"p-v627","task_id":"artifact:test-result",
      "status":"OK","producer":"test-runner","observed_at":"2026-09-23T00:00:00Z",
      "evidence":[{"kind":"report","source":"v627-runtime-proof","digest":"sha256:"+"1"*64}],
      "verification":{"status":"VERIFIED","method":"machine","verifier":"independent-verifier"},
      "outputs":[{"type":"artifact","id":"test-result","status":"OK"}],
      "learning_context":{
        "schema":"chacha.dev/verified-evidence-learning-context/v1",
        "deployment_id":"dep-v627","source_id":"verified-test-surface","surface_kind":"qualification",
        "evidence_refs":["qualification:v627"],
        "component_lineage":lineage
      }
    })
    run([sys.executable,str(BIN/"evidence-collector.py"),"init","--project","p-v627","--ledger",str(ledger)])
    run([sys.executable,str(BIN/"evidence-collector.py"),"ingest","--graph",str(graph),"--result",str(result),"--ledger",str(ledger)])
    l=load(ledger);ev=l["history"][-1]
    assert ev["verification_status"]=="VERIFIED",ev
    assert ev["learning_eligibility"]=="EXACT_LINEAGE",ev
    assert ev["learning_context"]["component_lineage"]==lineage,ev

    old=os.environ.get("CHACHA_DEV_TEST_GUARDIAN_BYPASS")
    os.environ["CHACHA_DEV_TEST_GUARDIAN_BYPASS"]="1"
    try:
        policy=load(CFG/"verified-evidence-learning.v1.json")
        first=m.reconcile_ledger(repo_root=ROOT,ledger_path=ledger,policy=policy,
                                 marker_root=markers,outbox_root=outbox,state_root=state)
        assert first["queued"]==1,first
        deltas=list(outbox.glob("ld-*.json"));assert len(deltas)==1,deltas
        delta=load(deltas[0])
        assert delta["evaluation"]["verified"] is True,delta
        assert delta["evaluation"]["outcome"]=="PASS",delta
        assert delta["lineage"]==lineage,delta
        assert delta["privacy"]["raw_user_content"] is False,delta
        second=m.reconcile_ledger(repo_root=ROOT,ledger_path=ledger,policy=policy,
                                  marker_root=markers,outbox_root=outbox,state_root=state)
        assert second["deduplicated"]==1 and second["queued"]==0,second
        assert len(list(outbox.glob("ld-*.json")))==1

        graph2=td/"graph2.json";result2=td/"result2.json";ledger2=td/"ledger2.json"
        g2=load(graph);g2["project"]="p-no-lineage";save(graph2,g2)
        r2=load(result);r2["project"]="p-no-lineage";r2.pop("learning_context");save(result2,r2)
        run([sys.executable,str(BIN/"evidence-collector.py"),"init","--project","p-no-lineage","--ledger",str(ledger2)])
        run([sys.executable,str(BIN/"evidence-collector.py"),"ingest","--graph",str(graph2),"--result",str(result2),"--ledger",str(ledger2)])
        e2=load(ledger2)["history"][-1]
        assert e2["learning_eligibility"]=="NO_CONFIDENCE_NO_PENALTY",e2
        skipped=m.reconcile_ledger(repo_root=ROOT,ledger_path=ledger2,policy=policy,
                                   marker_root=markers,outbox_root=outbox,state_root=state)
        assert skipped["skipped_no_lineage"]==1,skipped
        assert len(list(outbox.glob("ld-*.json")))==1

        bad=load(result);bad["learning_context"]["component_lineage"]["components"][0].pop("version")
        badp=td/"bad.json";save(badp,bad)
        p=subprocess.run([sys.executable,str(BIN/"evidence-collector.py"),"ingest",
                          "--graph",str(graph),"--result",str(badp),"--ledger",str(ledger)],
                          cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
        assert p.returncode!=0,(p.stdout,p.stderr)
        assert "COMPONENT_LINEAGE_ROW_INVALID" in (p.stdout+p.stderr),(p.stdout,p.stderr)
    finally:
        if old is None:os.environ.pop("CHACHA_DEV_TEST_GUARDIAN_BYPASS",None)
        else:os.environ["CHACHA_DEV_TEST_GUARDIAN_BYPASS"]=old

policy=load(CFG/"verified-evidence-learning.v1.json")
assert policy["eligibility"]["required_verification_status"]=="VERIFIED"
assert policy["eligibility"]["require_exact_component_lineage"] is True
assert policy["eligibility"]["missing_context_behavior"]=="NO_CONFIDENCE_NO_PENALTY"
assert policy["separation_of_concerns"]["learning_failure_does_not_rewrite_evidence"] is True
assert policy["separation_of_concerns"]["technology_revalidation_required"] is True
assert policy["separation_of_concerns"]["architecture_council_final_authority"] is True
assert policy["economics"]["automatic_external_spend_eur"]==0
roles=load(CFG/"guardian-role-contracts.v1.json")
assert any(x["contract_id"]=="role:verified-evidence-learning" for x in roles["contracts"])
assert any(x["contract_id"]=="component:verified-evidence-learning" for x in roles["contracts"])
coverage=load(CFG/"guardian-coverage-manifest.v1.json")
assert any(x["component_id"]=="verified-evidence-learning" for x in coverage["expected_components"])

print("CHACHA_DEV_V627_EVIDENCE_LEDGER_LEARNING_CONTEXT=PASS")
print("CHACHA_DEV_V627_VERIFIED_SUCCESS_AUTO_DELTA=PASS")
print("CHACHA_DEV_V627_EXACT_LINEAGE_REQUIRED_FOR_CONFIDENCE=PASS")
print("CHACHA_DEV_V627_MISSING_LINEAGE_NO_CONFIDENCE_NO_PENALTY=PASS")
print("CHACHA_DEV_V627_IDEMPOTENT_RECONCILIATION=PASS")
print("CHACHA_DEV_V627_LEARNING_ASYNC_FROM_FACTUAL_LEDGER=PASS")
print("CHACHA_DEV_V627_TECHNOLOGY_REVALIDATION_REMAINS_REQUIRED=PASS")
print("CHACHA_DEV_V627_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
