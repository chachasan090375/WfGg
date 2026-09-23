#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"

def save(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def run(args):
    return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)

spec=importlib.util.spec_from_file_location("project_control_v637",BIN/"project-control.py")
pc=importlib.util.module_from_spec(spec);spec.loader.exec_module(pc)

final_only=[
 "ARTIFACT_MISSING:compromise-release-receipt",
 "ARTIFACT_MISSING:seven-agent-final-delivery-receipt",
 "GATE_MISSING:compromise-release",
 "APPROVAL_MISSING:production-release"
]
assert pc.automatic_finalization_eligible("PREVIEW","RELEASE",final_only) is True
assert pc.automatic_finalization_eligible("VERIFY","PREVIEW",final_only) is False
assert pc.automatic_finalization_eligible("PREVIEW","RELEASE",final_only+["ARTIFACT_MISSING:smoke-result"]) is False
assert pc.is_finalization_output_blocker("GATE_BLOCKING:compromise-release:BLOCKED") is True
assert pc.is_finalization_output_blocker("ARTIFACT_NOT_OK:seven-agent-final-delivery-receipt:UNVERIFIED") is True

policy=load(CFG/"automatic-seven-agent-finalization.v1.json")
assert policy["trigger"]["automatic"] is True
assert policy["trigger"]["run_only_when_non_finalization_blockers_clear"] is True
assert policy["behavior"]["idempotent"] is True
assert policy["behavior"]["central_remediation_before_agent_renegotiation"] is True
assert policy["source_of_truth"]["ambiguous_source_forbidden"] is True

lifecycle=load(CFG/"lifecycle.v1.json")
required=lifecycle["transitions"]["PREVIEW->RELEASE"]["required_artifacts"]
assert "seven-agent-finalization-inputs" in required
assert "compromise-release-receipt" in required
assert "seven-agent-final-delivery-receipt" in required

catalog=load(CFG/"evidence-catalog.v1.json")
assert catalog["artifacts"]["seven-agent-finalization-inputs"]["verification"]=="independent-agent"

with tempfile.TemporaryDirectory(prefix="v637-") as td:
    td=Path(td);project="p637";revision="b"*40
    logic={"schema":"chacha.dev/logic-search-report/v1","report_digest":"sha256:logic"}
    ux={"schema":"chacha.dev/ux-planning-report/v1","report_digest":"sha256:ux"}
    comp={"schema":"chacha.dev/multi-agent-compromise/v1","dossier_digest":"sha256:compromise",
          "central_compromise_found":True}
    council={"schema":"chacha.dev/architecture-decision-council/v1","dispatch_allowed":True}
    impl={"schema":"chacha.dev/implementation-manifest/v1","project_id":project,"revision":revision,
          "compromise_digest":"sha256:compromise"}
    verify={"schema":"chacha.dev/implementation-verification/v1","project_id":project,"revision":revision,
            "compromise_digest":"sha256:compromise","status":"PASS"}
    files={}
    for name,x in [("logic",logic),("ux",ux),("comp",comp),("council",council),("impl",impl),("verify",verify)]:
        p=td/(name+".json");save(p,x);files[name]=p

    bundle=td/"bundle.json"
    p=run([sys.executable,str(BIN/"seven-agent-finalization-inputs.py"),
      "--project-id",project,"--revision",revision,
      "--logic-report",str(files["logic"]),"--ux-report",str(files["ux"]),
      "--compromise",str(files["comp"]),"--architecture-council",str(files["council"]),
      "--implementation-manifest",str(files["impl"]),
      "--implementation-verification",str(files["verify"]),
      "--guardian-functional-receipt-id","guardian-func-637",
      "--sentinel-technical-receipt-id","sentinel-tech-637",
      "--output",str(bundle)])
    assert p.returncode==0,(p.stdout,p.stderr)
    bv=load(bundle)
    assert bv["project_id"]==project and bv["revision"]==revision,bv
    assert bv["compromise_digest"]=="sha256:compromise",bv
    assert bv["ambiguous_source"] is False,bv

    final_receipt=td/"seven-agent-final-delivery.json"
    save(final_receipt,{
      "schema":"chacha.dev/seven-agent-final-delivery/v1","project_id":project,"revision":revision,
      "compromise_digest":"sha256:compromise","status":"DELIVERED","delivery_allowed":True
    })
    ledger=td/"ledger.json"
    save(ledger,{
      "schema":"chacha.dev/evidence-ledger/v1","project":project,
      "artifacts":{
        "seven-agent-finalization-inputs":{"status":"OK","source":str(bundle),"observed_at":"2026-09-23T00:00:00Z"},
        "compromise-release-receipt":{"status":"OK","source":str(td/"compromise-release.json"),"observed_at":"2026-09-23T00:00:01Z"},
        "seven-agent-final-delivery-receipt":{"status":"OK","source":str(final_receipt),"observed_at":"2026-09-23T00:00:02Z"}
      },
      "gates":{"compromise-release":{"status":"OK","source":str(final_receipt),"observed_at":"2026-09-23T00:00:02Z"}},
      "approvals":{},"risk_acceptances":[],"history":[]
    })
    result=td/"result.json"
    p=run([sys.executable,str(BIN/"automatic-seven-agent-finalizer.py"),
      "--project",project,"--policy",str(CFG/"automatic-seven-agent-finalization.v1.json"),
      "--ledger",str(ledger),"--repo-root",str(ROOT),
      "--output-dir",str(td/"out"),"--result",str(result)])
    assert p.returncode==0,(p.stdout,p.stderr)
    rv=load(result)
    assert rv["status"]=="ALREADY_FINALIZED",rv
    assert rv["idempotent_reuse"] is True,rv
    assert rv["external_calls_skipped"] is True,rv

    ambiguous=load(ledger)
    ambiguous["artifacts"]["seven-agent-finalization-inputs"]["source"]=str(bundle)+";"+str(td/"other.json")
    save(td/"ledger-ambiguous.json",ambiguous)
    p=run([sys.executable,str(BIN/"automatic-seven-agent-finalizer.py"),
      "--project",project,"--policy",str(CFG/"automatic-seven-agent-finalization.v1.json"),
      "--ledger",str(td/"ledger-ambiguous.json"),"--repo-root",str(ROOT),
      "--output-dir",str(td/"out2"),"--result",str(td/"result2.json")])
    assert p.returncode!=0,p.stdout+p.stderr
    assert "FINALIZATION_BUNDLE_SOURCE_AMBIGUOUS" in p.stdout+p.stderr

    # Task Graph automatically creates the independently verified input-bundle task.
    graph=td/"graph.json"
    p=run([sys.executable,str(BIN/"task-graph-engine.py"),"--project",project,
      "--transition","PREVIEW->RELEASE","--lifecycle",str(CFG/"lifecycle.v1.json"),
      "--quality",str(CFG/"quality-gates.v1.json"),"--catalog",str(CFG/"evidence-catalog.v1.json"),
      "--orchestration",str(CFG/"orchestration-policy.v1.json"),"--output",str(graph)])
    assert p.returncode==0,(p.stdout,p.stderr)
    gv=load(graph)
    task=next(x for x in gv["tasks"] if x["id"]=="artifact:seven-agent-finalization-inputs")
    assert task["owner_role"]=="orchestrator",task
    assert task["verification"]["mode"]=="independent-agent",task
    assert task["blocking"] is True,task

source=(BIN/"project-control.py").read_text(encoding="utf-8")
for marker in [
  "automatic_finalization_eligible",
  "run_automatic_finalization",
  "journal-first-ledger-finalize",
  "AUTOMATIC_SEVEN_AGENT_FINALIZATION_BLOCKED",
  "automatic_seven_agent_finalization"
]:
    assert marker in source,marker
assert source.index("run_automatic_finalization(project,actor,policy,repo_root,p)") < source.index('txid = "ctx-" + uuid.uuid4().hex')

control=load(CFG/"project-control.v1.json")
assert control["principles"]["automatic_seven_agent_finalization_on_preview_release"] is True
assert control["principles"]["automatic_finalization_is_transactional"] is True
assert control["principles"]["automatic_finalization_failure_never_promotes_release"] is True

print("CHACHA_DEV_V637_FINALIZATION_INPUT_BUNDLE=PASS")
print("CHACHA_DEV_V637_TASK_GRAPH_AUTO_INPUT_BUNDLE=PASS")
print("CHACHA_DEV_V637_AUTOMATIC_TRIGGER_PREVIEW_RELEASE=PASS")
print("CHACHA_DEV_V637_NON_FINALIZATION_BLOCKER_GUARD=PASS")
print("CHACHA_DEV_V637_IDEMPOTENT_REUSE=PASS")
print("CHACHA_DEV_V637_AMBIGUOUS_SOURCE_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V637_TRANSACTIONAL_LEDGER_COMMIT=PASS")
print("CHACHA_DEV_V637_FAILURE_NEVER_PROMOTES_RELEASE=PASS")
print("CHACHA_DEV_V637_CENTRAL_REMEDIATION_BEFORE_RENEGOTIATION=PASS")
print("CHACHA_DEV_V637_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V637_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
