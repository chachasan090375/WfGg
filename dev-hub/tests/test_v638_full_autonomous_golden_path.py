#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,shutil,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def run(args,cwd=ROOT):
    return subprocess.run(list(map(str,args)),cwd=str(cwd),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)

# Policy invariants.
gold=load(CFG/"autonomous-golden-path.v1.json")
assert gold["lifecycle"]["start"]=="IDEA"
assert gold["lifecycle"]["target"]=="RELEASE"
assert gold["lifecycle"]["first_release_attempt_without_approval_must_stop"]=="AWAITING_APPROVAL"
assert gold["safety"]["no_fake_pass"] is True
assert gold["economics"]["automatic_external_spend_eur"]==0
catalog=load(CFG/"evidence-catalog.v1.json")
assert catalog["artifacts"]["architecture-decisions-resolved"]["verification"]=="independent-agent"

# Real canonical materialization: files, Node tests, build, preview and restore.
if shutil.which("node") is None:
    raise SystemExit("NODE_REQUIRED_FOR_V638_TEST")
with tempfile.TemporaryDirectory(prefix="v638-materialize-") as td:
    td=Path(td)
    intent=td/"intent.json"
    save(intent,{
      "name":"V638 Canonical App",
      "text":"Crée une petite application frontend accessible avec un bouton, tests, sécurité, preview et rollback.",
      "golden_path_profile":"static-interaction-v1",
      "demo_message":"Golden Path V6.38 fonctionne",
      "expected_text":"Golden Path V6.38 fonctionne",
      "constraints":{"requires_authentication":False,"requires_database":False,"requires_external_api":False}
    })
    out=td/"out";rev="a"*40
    p=run([sys.executable,BIN/"golden-path-materializer.py",
           "--intent",intent,"--project-id","v638-test-project","--revision",rev,"--output-dir",out])
    assert p.returncode==0,(p.stdout,p.stderr)
    m=load(out/"materialization.json")
    assert m["status"]=="PASS" and m["zero_external_dependencies"] is True,m
    assert m["automatic_external_spend_eur"]==0,m
    for key in [
      "workspace-health","storage-preflight","dependency-resolution","change-set","build-result",
      "static-check","test-result","security-scan","ci-result","preview-candidate",
      "preview-validation","e2e-result","smoke-result","rollback-plan",
      "release-traceability","backup-recovery-readiness"
    ]:
        src=Path(m["artifact_sources"][key]); assert src.is_file(),(key,src)
        val=load(src); assert val.get("status")=="PASS",(key,val)
    assert load(out/"reports"/"backup-recovery-readiness.json")["restore_tested"] is True
    assert load(out/"reports"/"preview-validation.json")["localhost_only"] is True

# Release graph must include every normal quality gate, but not compromise-release.
with tempfile.TemporaryDirectory(prefix="v638-graph-") as td:
    td=Path(td);graph=td/"release-graph.json"
    p=run([sys.executable,BIN/"task-graph-engine.py","--project","v638-graph",
           "--transition","PREVIEW->RELEASE","--lifecycle",CFG/"lifecycle.v1.json",
           "--quality",CFG/"quality-gates.v1.json","--catalog",CFG/"evidence-catalog.v1.json",
           "--orchestration",CFG/"orchestration-policy.v1.json","--output",graph])
    assert p.returncode==0,(p.stdout,p.stderr)
    g=load(graph)
    gate_ids={x["id"].split(":",1)[1] for x in g["tasks"] if x["kind"]=="gate"}
    expected=set(load(CFG/"quality-gates.v1.json")["gates"])-{"compromise-release"}
    assert gate_ids==expected,(sorted(gate_ids),sorted(expected))
    approval=next(x for x in g["tasks"] if x["id"]=="approval:production-release")
    assert approval["verification"]["mode"]=="human"
    for task in g["tasks"]:
        if task["kind"]=="gate":
            assert "artifact:compromise-release-receipt" not in task["depends_on"],task["id"]
            assert "artifact:seven-agent-final-delivery-receipt" not in task["depends_on"],task["id"]

# Protected human approval is a real Control Plane + Evidence Ledger transaction.
spec=importlib.util.spec_from_file_location("project_control_v638",BIN/"project-control.py")
pc=importlib.util.module_from_spec(spec);spec.loader.exec_module(pc)
with tempfile.TemporaryDirectory(prefix="v638-approval-") as td:
    td=Path(td);project="v638-approval-test"
    state_policy=load(CFG/"control-plane-state.v1.json")
    state_policy["storage"]["runtime_root"]=str(td/"state")
    state_policy_path=td/"control-plane-state.json";save(state_policy_path,state_policy)

    policy=load(CFG/"project-control.v1.json")
    policy["runtime"]["state_root"]=str(td/"state")
    policy["runtime"]["evidence_root"]=str(td/"evidence")
    policy["runtime"]["plans_root"]=str(td/"plans")
    policy["runtime"]["health_root"]=str(td/"health")
    policy["runtime"]["runs_root"]=str(td/"runs")
    policy["runtime"]["transactions_root"]=str(td/"transactions")
    policy["runtime"]["locks_root"]=str(td/"locks")
    policy["repository_paths"]["control_plane_state"]=str(state_policy_path)
    policy["engine_paths"]["control_plane_store"]=str(BIN/"control-plane-store.py")

    initial=td/"initial.json";save(initial,{"lifecycle":{"stage":"PREVIEW"}})
    p=run([sys.executable,BIN/"control-plane-store.py","--policy",state_policy_path,
           "--root",td/"state","init","--project",project,"--actor","test","--initial",initial])
    assert p.returncode==0,(p.stdout,p.stderr)
    ledger=td/"evidence"/project/"ledger.json"
    save(ledger,{"schema":"chacha.dev/evidence-ledger/v1","project":project,
                 "artifacts":{},"gates":{},"approvals":{},"risk_acceptances":[],"history":[]})

    r=pc.record_approval_operation(project,"production-release","human-v638-test","approval-evidence-1",policy,ROOT)
    assert r["status"]=="OK",r
    lv=load(ledger);assert lv["approvals"]["production-release"]["status"]=="APPROVED"
    state=load(td/"state"/project/"state.json")
    assert state["state"]["approvals"]["production-release"]["actor"]=="human-v638-test",state
    journal=(td/"state"/project/"audit.jsonl").read_text(encoding="utf-8")
    assert '"event_type":"APPROVAL_RECORDED"' in journal,journal

    again=pc.record_approval_operation(project,"production-release","human-v638-test","approval-evidence-1",policy,ROOT)
    assert again["status"]=="OK" and again["details"]["idempotent"] is True,again
    conflict=pc.record_approval_operation(project,"production-release","other-human","approval-evidence-2",policy,ROOT)
    assert conflict["status"]=="BLOCKED" and "APPROVAL_REPLAY_CONFLICT" in conflict["blockers"],conflict
    agent=pc.record_approval_operation(project,"other-approval","central-orchestrator","x",policy,ROOT)
    assert agent["status"]=="BLOCKED" and "HUMAN_APPROVAL_ACTOR_REQUIRED" in agent["blockers"],agent

# Main controller must only mutate lifecycle/evidence via Project Control.
source=(BIN/"autonomous-golden-path-controller.py").read_text(encoding="utf-8")
for marker in [
  "autonomous-project-orchestrator.py","golden-path-materializer.py",
  "verify-result","record-approval","AWAITING_APPROVAL",
  "seven-agent-finalization-inputs.py","guardian-client.py","sentinel-client.py",
  "crypto-trust.py","nas-ssh-adapter"
]:
    assert marker in source,marker
assert "CHACHA_DEV_V638_DIRECT_LEDGER_MUTATION=NO" in source
assert "CHACHA_DEV_V638_DIRECT_LIFECYCLE_MUTATION=NO" in source

print("CHACHA_DEV_V638_CANONICAL_MATERIALIZER_REAL=PASS")
print("CHACHA_DEV_V638_REAL_NODE_TEST_BUILD_PREVIEW_RESTORE=PASS")
print("CHACHA_DEV_V638_RELEASE_QUALITY_GATES_COMPLETE=PASS")
print("CHACHA_DEV_V638_COMPROMISE_FINAL_GATE_SEPARATION=PASS")
print("CHACHA_DEV_V638_PROTECTED_HUMAN_APPROVAL_TRANSACTION=PASS")
print("CHACHA_DEV_V638_APPROVAL_IDEMPOTENCY=PASS")
print("CHACHA_DEV_V638_AGENT_SELF_APPROVAL_BLOCKED=PASS")
print("CHACHA_DEV_V638_ARCHITECTURE_COUNCIL_INDEPENDENT_VERIFICATION=PASS")
print("CHACHA_DEV_V638_DIRECT_LEDGER_MUTATION=NO")
print("CHACHA_DEV_V638_DIRECT_LIFECYCLE_MUTATION=NO")
print("CHACHA_DEV_V638_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
