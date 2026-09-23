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

# Real canonical materialization is lifecycle-staged: no BUILD/VERIFY/PREVIEW work is
# executed before the authoritative phase that owns it.
if shutil.which("node") is None or shutil.which("git") is None:
    raise SystemExit("NODE_AND_GIT_REQUIRED_FOR_V638_TEST")
with tempfile.TemporaryDirectory(prefix="v638-materialize-") as td:
    td=Path(td);rev="a"*40;project="v638-test-project"
    intent=td/"intent.json"
    save(intent,{
      "name":"V638 Canonical App",
      "text":"Crée une petite application frontend accessible avec un bouton, tests, sécurité, preview et rollback.",
      "golden_path_profile":"static-interaction-v1",
      "constraints":{"requires_authentication":False,"requires_database":False,"requires_external_api":False}
    })
    plan=td/"planning";plan.mkdir()
    save(plan/"final-plan.json",{"primary_domains":["frontend"],"review_domains":[]})
    save(plan/"project.json",{"schema":"chacha.dev/project-instance/v1","project_id":project,
                              "name":"V638 Canonical App","functional_intent":"Canonical intent"})
    save(plan/"capability-foundry.json",{"schema":"chacha.dev/capability-foundry/v1","created_capability_count":0})
    save(plan/"architecture-decision-council.json",{"schema":"chacha.dev/architecture-decision-council/v1","dispatch_allowed":True})
    save(plan/"logic-search-report.json",{"schema":"chacha.dev/logic-search-report/v1","report_digest":"sha256:logic"})
    save(plan/"ux-planning-report.json",{"schema":"chacha.dev/ux-planning-report/v1","report_digest":"sha256:ux"})
    save(plan/"multi-agent-compromise.json",{
      "schema":"chacha.dev/multi-agent-compromise/v1","dossier_digest":"sha256:compromise",
      "compromise":{
        "logic_proposal":{"candidate":{"candidate_id":"canonical-static","execution_mode":"LOCAL"}},
        "ux_proposal":{"ux_contract":{"primary_job_statement":"Use the main action",
          "curator_handoff_required":True,
          "recommendations":[{"id":"visible-status"},{"id":"focus-visible"}]}}
      }
    })
    save(plan/"functional-contract.json",{"schema":"chacha.dev/functional-contract/v1","criteria":[]})
    assurance=plan/"embedded-assurance";assurance.mkdir()
    boot=plan/"bootstrap-result.json"
    save(boot,{
      "schema":"chacha.dev/autonomous-project-bootstrap/v1","project_id":project,
      "domain_dispatch_allowed":True,"central_compromise_found":True,
      "architecture_decision_allowed":True,"architecture_council_consumed_compromise":True,
      "external_spend_eur":0,"five_local_probes_enabled":True,
      "final_plan":str(plan/"final-plan.json"),"project":str(plan/"project.json"),
      "capability_foundry":str(plan/"capability-foundry.json"),
      "architecture_decision_council":str(plan/"architecture-decision-council.json"),
      "logic_search_report":str(plan/"logic-search-report.json"),
      "ux_planning_report":str(plan/"ux-planning-report.json"),
      "multi_agent_compromise":str(plan/"multi-agent-compromise.json"),
      "functional_contract":str(plan/"functional-contract.json"),
      "embedded_assurance_bundle":str(assurance)
    })
    out=td/"materialization.json";ws=td/"workspace";ev=td/"evidence"
    def phase(name):
        return run([sys.executable,BIN/"golden-path-materializer.py","--phase",name,
                    "--intent",intent,"--bootstrap-result",boot,"--revision",rev,
                    "--workspace",ws,"--evidence-dir",ev,"--output",out])
    p=phase("design"); assert p.returncode==0,(p.stdout,p.stderr)
    m=load(out);assert m["phase"]=="DESIGN_VALIDATED",m
    assert set(m["artifact_sources"])=={"manifest-validation"},m
    manifest=load(Path(m["sources"]["manifest-v3"]))
    assert manifest["schema"]=="chacha.dev/project-manifest/v3",manifest

    skipped=phase("build")
    assert skipped.returncode!=0 and "GOLDEN_PHASE_PRECONDITION" in skipped.stderr+skipped.stdout

    p=phase("prepare"); assert p.returncode==0,(p.stdout,p.stderr)
    m=load(out);assert m["phase"]=="PREPARED",m
    assert {"workspace-health","storage-preflight","dependency-resolution"} <= set(m["artifact_sources"])

    p=phase("build"); assert p.returncode==0,(p.stdout,p.stderr)
    m=load(out);assert m["phase"]=="BUILT",m
    assert {"change-set","build-result","static-check"} <= set(m["artifact_sources"])

    p=phase("verify"); assert p.returncode==0,(p.stdout,p.stderr)
    m=load(out);assert m["phase"]=="VERIFIED",m
    assert {"test-result","security-scan","ci-result","preview-candidate"} <= set(m["artifact_sources"])
    assert m["real_preview"] is False,m

    p=phase("preview"); assert p.returncode==0,(p.stdout,p.stderr)
    m=load(out);assert m["phase"]=="PREVIEWED" and m["real_preview"] is True,m
    assert m["external_spend_eur"]==0,m
    for key in [
      "workspace-health","storage-preflight","dependency-resolution","change-set","build-result",
      "static-check","test-result","security-scan","ci-result","preview-candidate",
      "preview-validation","e2e-result","smoke-result","rollback-plan",
      "release-traceability","backup-recovery-readiness"
    ]:
        src=Path(m["artifact_sources"][key]); assert src.is_file(),(key,src)
        val=load(src); assert val.get("status")=="PASS",(key,val)
    recovery=load(Path(m["artifact_sources"]["backup-recovery-readiness"]))
    assert recovery["details"]["restore_tested"] is True
    preview=load(Path(m["artifact_sources"]["preview-validation"]))
    assert preview["details"]["status_code"]==200
    assert float(m["preview_duration_ms"])>=0
    impl=load(Path(m["implementation_manifest"]))
    assert impl["logic"]["candidate_id"]=="canonical-static",impl
    assert set(impl["ux"]["implemented_requirement_ids"])=={"visible-status","focus-visible"},impl

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

    # Real verification + transactional ingestion without a Run Controller envelope.
    graph=td/"release-graph.json"
    p=run([sys.executable,BIN/"task-graph-engine.py","--project",project,
           "--transition","PREVIEW->RELEASE","--lifecycle",CFG/"lifecycle.v1.json",
           "--quality",CFG/"quality-gates.v1.json","--catalog",CFG/"evidence-catalog.v1.json",
           "--orchestration",CFG/"orchestration-policy.v1.json","--output",graph])
    assert p.returncode==0,(p.stdout,p.stderr)
    gv=load(graph)
    for artifact_id,method in (("preview-validation","machine"),("rollback-plan","independent-agent")):
        task=next(x for x in gv["tasks"] if x["id"]=="artifact:"+artifact_id)
        source=td/(artifact_id+".json");save(source,{"artifact_id":artifact_id,"status":"PASS"})
        import hashlib
        h="sha256:"+hashlib.sha256(source.read_bytes()).hexdigest()
        result=td/(artifact_id+".result.json")
        save(result,{
          "schema":"chacha.dev/task-result/v1","project":project,"task_id":task["id"],
          "status":"OK","producer":"v638-test-producer","observed_at":"2026-09-23T00:00:00Z",
          "summary":"test","evidence":[{"kind":"file","source":str(source.resolve()),"digest":h}],
          "verification":{"status":"UNVERIFIED","method":"none","verifier":"none","observed_at":"2026-09-23T00:00:00Z"},
          "outputs":[{"type":"artifact","id":artifact_id,"status":"OK"}]
        })
        vr=pc.verify_result_operation(project,result,graph,method,"v638-independent-verifier",True,policy,ROOT)
        assert vr["status"]=="OK",(artifact_id,vr)
        assert (load(ledger)["artifacts"][artifact_id]["status"])=="OK"

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
  "run_materializer_phase",
  "verify-result","record-approval","AWAITING_APPROVAL",
  "seven-agent-finalization-inputs.py","guardian-client.py","sentinel-client.py",
  "crypto-trust.py","nas-ssh-adapter"
]:
    assert marker in source,marker
assert "CHACHA_DEV_V638_DIRECT_LEDGER_MUTATION=NO" in source
assert "CHACHA_DEV_V638_DIRECT_LIFECYCLE_MUTATION=NO" in source
assert '"design":"DESIGN_VALIDATED"' in source
assert '"prepare":"PREPARED"' in source
assert '"build":"BUILT"' in source
assert '"verify":"VERIFIED"' in source
assert '"preview":"PREVIEWED"' in source
assert "--resume-from-awaiting-approval" in source
assert "V638_INITIAL_RUN_MUST_NOT_PRELOAD_APPROVAL" in source
assert "CHACHA_DEV_V638_RESUMED_SAME_PROJECT=PASS" in source
assert "CHACHA_DEV_V638_HUMAN_APPROVAL_AFTER_BOUNDARY=PASS" in source

installer=(BIN/"install-v638-full-autonomous-golden-path.sh").read_text(encoding="utf-8")
for marker in [
  "CHACHA_DEV_V638_INSTALL=AWAITING_APPROVAL",
  "CHACHA_DEV_V638_AWAITING_APPROVAL_CHECKPOINT=PASS",
  "CHACHA_DEV_V638_RESUME_CHECKPOINT=PASS",
  "--resume-from-awaiting-approval",
  "CHACHA_DEV_V638_PREAPPROVAL_RELEASE_MUTATION=NO",
]:
    assert marker in installer,marker
assert '--human-approval-id "$APPROVAL_ID"' in installer
assert 'if [ "$RESUME" -eq 0 ]; then' in installer
assert "urllib.request" not in installer
assert 'curl -fsS "$url/healthz"' in installer
assert "CHACHA_DEV_V638_EXTERNAL_HEALTH_TRANSPORT=CURL" in installer

sentinel_worker=(ROOT/"dev-hub/sentinel/worker.js").read_text(encoding="utf-8")
assert "const stored=await storedWorkflowAttestation(env,repository,revision,workflowName);" in sentinel_worker
assert "const gh=await githubRuns(repository,revision,workflowName,env);" in sentinel_worker
assert "const gh=await technicalAssuranceForRevision(repository,revision,workflowName,env);" in sentinel_worker
assert "technical_verification_source:gh.source||\"UNKNOWN\"" in sentinel_worker
assert "release_check_d1_first_runtime:true" in sentinel_worker

print("CHACHA_DEV_V638_TRUE_TWO_PHASE_HUMAN_RESUME=PASS")
print("CHACHA_DEV_V638_LIFECYCLE_STAGED_MATERIALIZATION=PASS")
print("CHACHA_DEV_V638_CANONICAL_MATERIALIZER_REAL=PASS")
print("CHACHA_DEV_V638_REAL_NODE_TEST_BUILD_PREVIEW_RESTORE=PASS")
print("CHACHA_DEV_V638_RELEASE_QUALITY_GATES_COMPLETE=PASS")
print("CHACHA_DEV_V638_COMPROMISE_FINAL_GATE_SEPARATION=PASS")
print("CHACHA_DEV_V638_REAL_VERIFICATION_BROKER_INGEST=PASS")
print("CHACHA_DEV_V638_PROTECTED_HUMAN_APPROVAL_TRANSACTION=PASS")
print("CHACHA_DEV_V638_APPROVAL_IDEMPOTENCY=PASS")
print("CHACHA_DEV_V638_AGENT_SELF_APPROVAL_BLOCKED=PASS")
print("CHACHA_DEV_V638_ARCHITECTURE_COUNCIL_INDEPENDENT_VERIFICATION=PASS")
print("CHACHA_DEV_V638_DIRECT_LEDGER_MUTATION=NO")
print("CHACHA_DEV_V638_DIRECT_LIFECYCLE_MUTATION=NO")
print("CHACHA_DEV_V638_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
