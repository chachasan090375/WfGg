#!/usr/bin/env python3
from __future__ import annotations
import contextlib,copy,importlib.util,io,json,subprocess,sys,tempfile
from pathlib import Path
from typing import Any

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def loadmod(name:str,path:Path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise RuntimeError("MODULE_LOAD_FAILED:"+str(path))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def guardian(repo:Path)->dict[str,Any]:
    sys.path.insert(0,str(repo/"dev-hub/bin"))
    import guardian_remediation_runtime as grr
    policy=load(repo/"dev-hub/config/guardian-runtime-policy.v1.json")
    with tempfile.TemporaryDirectory(prefix="v651-guardian-") as td:
        idx=Path(td)/"index.json"
        idx.write_text(json.dumps({"schema":"chacha.dev/guardian-remediation-index/v1","items":[
          {"directive_id":"warning","target_actor":"run-controller","target_role":"run-controller","project_id":"p1",
           "severity":"WARNING","required_action":"RELOAD_CONTRACT_AND_REPLAN","rule_codes":["X"],"status":"OPEN","created_at":"2026-09-24T00:00:00Z"},
          {"directive_id":"critical","target_actor":"agent:p1:x","target_role":"agent:p1:x","project_id":"p1",
           "severity":"CRITICAL","required_action":"REPLAN_WITHIN_AUTHORIZED_SCOPE","rule_codes":["CAPABILITY_OUTSIDE_AGENT_MISSION"],
           "status":"DELIVERED","created_at":"2026-09-24T00:01:00Z"}]},indent=2)+"\n",encoding="utf-8")
        d=grr.current_directive(actor="run-controller",subject_role="agent:p1:x",project_id="p1",index_path=idx)
        ctx=grr.inject_context({"resource_class":"light"},actor="run-controller",subject_role="agent:p1:x",project_id="p1",index_path=idx)
        none=grr.current_directive(actor="other",subject_role="other",project_id="p2",index_path=idx)
    ce=policy.get("corrective_enforcement") or {}
    return {"agent_id":"guardian","adapter":"guardian-remediation-runtime","actual":{
      "critical_precedence":(d or {}).get("directive_id"),
      "required_action":ctx.get("guardian_required_action"),
      "directive_injected":ctx.get("remediation_directive_id"),
      "no_match_is_none":none is None,
      "rewrite_architecture_allowed":ce.get("guardian_may_rewrite_architecture"),
      "expand_permissions_allowed":ce.get("guardian_may_expand_permissions"),
      "max_failed_attempts":ce.get("max_failed_correction_attempts"),
      "structured_directive":bool(d and d.get("directive_id") and d.get("required_action"))
    }}

def _git_init(root:Path)->None:
    subprocess.run(["git","init","-q"],cwd=root,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    subprocess.run(["git","config","user.email","benchmark@local"],cwd=root,check=True)
    subprocess.run(["git","config","user.name","V651 Benchmark"],cwd=root,check=True)

def sentinel(repo:Path)->dict[str,Any]:
    mod=loadmod("v651_sentinel",repo/"dev-hub/bin/sentinel-technical-audit.py")
    policy=load(repo/"dev-hub/config/sentinel-technical-policy.v1.json")
    with tempfile.TemporaryDirectory(prefix="v651-sentinel-") as td:
        base=Path(td)
        clean=base/"clean";clean.mkdir();_git_init(clean)
        (clean/"good.py").write_text("def ok():\n    return 1\n",encoding="utf-8")
        subprocess.run(["git","add","good.py"],cwd=clean,check=True)
        clean_result=mod.audit(clean,policy,None,"HEAD",False)
        bad=base/"bad";bad.mkdir();_git_init(bad)
        (bad/"bad.py").write_text("<<<<<<< ours\ndef broken(:\n=======\ndef ok():\n    return 1\n>>>>>>> theirs\n",encoding="utf-8")
        subprocess.run(["git","add","bad.py"],cwd=bad,check=True)
        bad_result=mod.audit(bad,policy,None,"HEAD",False)
    checks={str(x.get("check")) for x in bad_result.get("blocking_findings") or []}
    principles=policy.get("principles") or {}
    return {"agent_id":"sentinel","adapter":"sentinel-technical-audit","actual":{
      "clean_verdict":clean_result.get("verdict"),
      "bad_verdict":bad_result.get("verdict"),
      "bad_detects_conflict":"merge-conflict-markers" in checks,
      "bad_detects_syntax":"syntax" in checks,
      "clean_audit_digest":bool(clean_result.get("audit_digest")),
      "bad_findings_structured":all(isinstance(x,dict) and x.get("check") for x in bad_result.get("blocking_findings") or []),
      "observer_only":principles.get("observer_and_tester_only"),
      "direct_code_mutation":principles.get("direct_code_mutation"),
      "direct_application_mutation":principles.get("direct_application_mutation")
    }}

def bastion(repo:Path)->dict[str,Any]:
    mod=loadmod("v651_bastion",repo/"dev-hub/bin/bastion-incident-response-controller.py")
    policy=load(repo/"dev-hub/config/bastion-runtime-policy.v1.json")
    effects=[]
    mod.record_project_control=lambda kind,item: effects.append(("project-control",kind))
    mod.revoke_local_project_key=lambda project,directive_id: effects.append(("revoke",project)) or {"local_key_revoked":True}
    mod.survival=lambda item: effects.append(("survival",str(item.get("directive_id"))))
    mod.emergency=lambda item,path: effects.append(("emergency",str(item.get("directive_id"))))
    statuses={}
    for action in ["OBSERVE","CONTAIN","QUARANTINE","REVOKE","SURVIVAL","E_STOP"]:
        item={"directive_id":"d-"+action.lower(),"project_id":"p1","action":action}
        statuses[action]=mod.execute(item,Path("/nonexistent-benchmark-emergency")).get("status")
    failover_blocked=False
    try:mod.execute({"directive_id":"d-failover","project_id":"p1","action":"FAILOVER"},Path("/none"))
    except RuntimeError as exc:failover_blocked="FAILOVER_RESERVED_INACTIVE" in str(exc)
    unknown_blocked=False
    try:mod.execute({"directive_id":"d-unknown","project_id":"p1","action":"UNKNOWN"},Path("/none"))
    except RuntimeError as exc:unknown_blocked="UNKNOWN_BASTION_ACTION" in str(exc)
    principles=policy.get("principles") or {}
    return {"agent_id":"bastion","adapter":"bastion-incident-response","actual":{
      "statuses":statuses,"failover_blocked":failover_blocked,"unknown_blocked":unknown_blocked,
      "side_effect_calls":len(effects),"external_authority":principles.get("external_authority"),
      "direct_application_mutation":principles.get("no_direct_application_mutation") is False,
      "direct_architecture_mutation":principles.get("no_direct_architecture_mutation") is False,
      "structured_statuses":all(isinstance(v,str) and bool(v) for v in statuses.values())
    }}

def recovery(repo:Path)->dict[str,Any]:
    mod=loadmod("v651_recovery",repo/"dev-hub/bin/recovery-orchestrator.py")
    mod.aob=None
    policy=repo/"dev-hub/config/recovery-orchestrator.v1.json"
    scenarios={
      "destructive":{"destructive_restore_required":True},
      "data_loss":{"data_loss_possible":True},
      "security":{"security_boundary_change":True},
      "rollback":{"rollback_available":True},
      "restart":{"safe_service_restart_available":True},
      "none":{},
      "rollback_precedence":{"rollback_available":True,"safe_service_restart_available":True}
    }
    results={}
    old_argv=list(sys.argv)
    try:
      with tempfile.TemporaryDirectory(prefix="v651-recovery-") as td:
        td=Path(td)
        for name,incident in scenarios.items():
            incident={"incident_id":"v651-"+name,"project_id":"benchmark",**incident}
            ip=td/(name+"-incident.json");op=td/(name+"-out.json")
            ip.write_text(json.dumps(incident)+"\n",encoding="utf-8")
            sys.argv=["recovery-orchestrator.py","--incident",str(ip),"--policy",str(policy),"--output",str(op)]
            mod.main()
            results[name]=load(op)
    finally:sys.argv=old_argv
    return {"agent_id":"autonomous-recovery-agent","adapter":"recovery-orchestrator","actual":{
      "results":results,
      "structured_outputs":all(x.get("schema")=="chacha.dev/recovery-decision/v1" and x.get("action") for x in results.values())
    }}


def _architect_role_contract(repo:Path,agent_id:str,focus_key:str)->dict[str,Any]:
    mod=loadmod("v652_architect_"+agent_id.replace("-","_"),repo/"dev-hub/adapters/architecture-specialist-adapter.py")
    with tempfile.TemporaryDirectory(prefix="v652-"+agent_id+"-") as td:
        base=Path(td);old_plans=mod.PLANS_ROOT;old_results=mod.RESULT_ROOT
        try:
            mod.PLANS_ROOT=base/"plans";mod.RESULT_ROOT=base/"results"
            project="v652-"+agent_id;rid="REQ-"+agent_id
            root=mod.PLANS_ROOT/mod.safe_name(project)/"technical-design";root.mkdir(parents=True,exist_ok=True)
            requirement=root/"requirement.json";manifest=root/"manifest.json";plan=root/"plan.json"
            requirement.write_text(json.dumps({"schema":"chacha.dev/requirement/v1","project":project,"id":rid,"summary":"benchmark"})+"\n",encoding="utf-8")
            manifest_value={"schema":"chacha.dev/project-manifest/v1","identity":{"project":project},"ownership":{},
              "components":[{"id":"component-a"}],"dependencies":[],"security":{},"data":{},"observability":{},"recovery":{},"technology_policy":{}}
            manifest_value[focus_key]={"benchmark_focus":True}
            manifest.write_text(json.dumps(manifest_value)+"\n",encoding="utf-8")
            plan_value={"schema":"chacha.dev/technical-design-plan/v1","project":project,"requirement_id":rid,
              "specialist_assignments":[{"role":agent_id,"scope":["component-a"]}],
              "architecture_decisions":[{"id":"ADR-BENCH","owner_role":agent_id,"decision":"benchmark"}],
              "affected_components":["component-a"],"cross_reviews":[],"implementation_gate":{}}
            plan.write_text(json.dumps(plan_value)+"\n",encoding="utf-8")
            ctx={"requirement_path":str(requirement.resolve()),"manifest_path":str(manifest.resolve()),
                 "technical_design_plan_path":str(plan.resolve()),"requirement_id":rid}
            req={"schema":mod.INPUT_SCHEMA,"project":project,"run_id":"v652-run",
              "task":{"id":"design:"+agent_id,"owner_role":agent_id,"permission":"plan"},
              "bindings":[{"provider":mod.PROVIDER_ID,"adapter":mod.ADAPTER_ID,"health_state":"HEALTHY"}],
              "metadata":{"specialist_role":agent_id,"technical_design_context":ctx,"design_outputs":[]}}
            action,data,err=mod.validate_request(req)
            model_context,run_dir=mod.build_model_context(req,agent_id,ctx)
            prompt=mod.prompt_for(model_context)
            artifact={"schema":mod.SPECIALIST_SCHEMA,"project":project,"requirement_id":rid,
              "task_id":"design:"+agent_id,"role":agent_id,"artifact_kind":"design-fragment","status":"PROPOSED",
              "summary":"benchmark","decisions":[],"recommendations":[],"risks":[],"unresolved_questions":[],
              "acceptance_obligations":[],"implementation_constraints":[],"source_references":["benchmark:fixture"]}
            artifact_valid=True
            try:mod.validate_specialist_artifact(artifact,model_context)
            except Exception:artifact_valid=False
            identity_blocked=False
            wrong=dict(artifact);wrong["role"]="other-role"
            try:mod.validate_specialist_artifact(wrong,model_context)
            except ValueError as exc:identity_blocked="IDENTITY_MISMATCH:role" in str(exc)
            bad=copy.deepcopy(req);bad["task"]["permission"]="workspace-write"
            _a,_d,permission_error=mod.validate_request(bad)
            escape=copy.deepcopy(req);escape["metadata"]["technical_design_context"]["manifest_path"]="/etc/passwd"
            path_escape_blocked=False
            try:mod.build_model_context(escape,agent_id,escape["metadata"]["technical_design_context"])
            except ValueError as exc:path_escape_blocked="OUTSIDE_RUNTIME_PLAN_ROOT" in str(exc)
            agent_md=mod.custom_agent_markdown()
            return {"agent_id":agent_id,"adapter":"architecture-specialist-contract","actual":{
              "action":action,"validation_error":err,"role":model_context.get("role"),
              "assignment_role":((model_context.get("technical_design") or {}).get("assignment") or {}).get("role"),
              "focus_present":bool((model_context.get("manifest") or {}).get(focus_key)),
              "artifact_valid":artifact_valid,"identity_mismatch_blocked":identity_blocked,
              "permission_blocked":str(permission_error or "").startswith("ARCHITECT_DESIGN_PERMISSION_REQUIRED"),
              "path_escape_blocked":path_escape_blocked,"zero_tools":"tools: []" in agent_md and "Do not call tools" in agent_md,
              "prompt_bounded":len(prompt.encode("utf-8"))<=int(mod.MAX_PROMPT_BYTES),
              "run_dir_isolated":str(run_dir).startswith(str(base.resolve()))
            }}
        finally:
            mod.PLANS_ROOT=old_plans;mod.RESULT_ROOT=old_results

def security_reviewer(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"security-reviewer","security")

def data_architect(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"data-architect","data")

def recovery_engineer(repo:Path)->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="v652-recovery-engineer-") as td:
        base=Path(td);report_path=base/"report.json";work=base/"sandbox"
        proc=subprocess.run([sys.executable,str(repo/"dev-hub/bin/recovery-drill.py"),
          "--repo-root",str(repo),"--policy","dev-hub/config/recovery-drill.v1.json",
          "--work-root",str(work),"--output",str(report_path),"run","--scenario","all"],
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=120)
        report=load(report_path) if report_path.is_file() else {}
        scenarios=report.get("scenarios") or [];by={str(x.get("id")):x for x in scenarios if isinstance(x,dict)}
        return {"agent_id":"recovery-engineer","adapter":"recovery-drill","actual":{
          "returncode":proc.returncode,"report_status":report.get("status"),"scenario_count":len(scenarios),
          "passed_count":sum(1 for x in scenarios if x.get("status")=="PASS"),
          "all_structured":all(isinstance(x,dict) and x.get("id") and isinstance(x.get("checks"),list) for x in scenarios),
          "tamper_pass":(by.get("tampered-journal") or {}).get("status")=="PASS",
          "divergent_pass":(by.get("divergent-ledger") or {}).get("status")=="PASS",
          "prepared_pass":(by.get("prepared-before-authority") or {}).get("status")=="PASS",
          "sandbox_isolated":str(Path(str(report.get("work_root") or "")).resolve()).startswith(str(base.resolve())),
          "fatal_error":report.get("fatal_error"),"stderr_empty":not bool(proc.stderr.strip())
        }}

def _platform_selftest_invoke(mod,req:dict[str,Any])->tuple[int,dict[str,Any]]:
    old_stdin=sys.stdin;buf=io.StringIO();sys.stdin=io.StringIO(json.dumps(req))
    try:
        with contextlib.redirect_stdout(buf):code=int(mod.main())
    finally:sys.stdin=old_stdin
    lines=[x for x in buf.getvalue().splitlines() if x.strip()]
    return code,json.loads(lines[-1]) if lines else {}

def platform_cloud_engineer(repo:Path)->dict[str,Any]:
    mod=loadmod("v652_platform_selftest",repo/"dev-hub/adapters/platform-selftest-adapter.py")
    with tempfile.TemporaryDirectory(prefix="v652-platform-") as td:
        rev=Path(td)/".revision";rev.write_text("v652-platform-revision\n",encoding="utf-8")
        old_revision=mod.REVISION;mod.REVISION=rev
        try:
            req={"schema":mod.INPUT_SCHEMA,"project":"benchmark","task":{"id":"platform-selftest","permission":"read",
                 "outputs":[{"type":"report","id":"revision-proof"}]},
                 "bindings":[{"provider":mod.PROVIDER_ID,"adapter":mod.ADAPTER_ID}],
                 "metadata":{"platform_selftest":{"action":"revision-proof"}}}
            ok_code,ok=_platform_selftest_invoke(mod,req)
            bad_perm=copy.deepcopy(req);bad_perm["task"]["permission"]="workspace-write"
            perm_code,perm=_platform_selftest_invoke(mod,bad_perm)
            bad_bind=copy.deepcopy(req);bad_bind["bindings"]=[]
            bind_code,bind=_platform_selftest_invoke(mod,bad_bind)
            bad_action=copy.deepcopy(req);bad_action["metadata"]["platform_selftest"]["action"]="production-mutate"
            act_code,act=_platform_selftest_invoke(mod,bad_action)
        finally:mod.REVISION=old_revision
    ev=(ok.get("evidence") or [{}])[0] if ok.get("evidence") else {}
    details=ev.get("details") or {}
    return {"agent_id":"platform-cloud-engineer","adapter":"platform-selftest-readonly","actual":{
      "valid_code":ok_code,"valid_status":ok.get("status"),"valid_summary":ok.get("summary"),
      "permission_code":perm_code,"permission_status":perm.get("status"),"permission_summary":perm.get("summary"),
      "binding_code":bind_code,"binding_status":bind.get("status"),"binding_summary":bind.get("summary"),
      "action_code":act_code,"action_status":act.get("status"),"action_summary":act.get("summary"),
      "evidence_digest":ev.get("digest"),"read_only":details.get("read_only"),
      "application_mutation":details.get("application_mutation"),"external_spend_eur":details.get("external_spend_eur"),
      "verification_status":((ok.get("verification") or {}).get("status"))
    }}

def release_engineer(repo:Path)->dict[str,Any]:
    mod=loadmod("v652_external_release_gate",repo/"dev-hub/bin/external-assurance-release-gate.py")
    project="benchmark";revision="rev-v652"
    functional={"schema":"chacha.dev/guardian-functional-acceptance-receipt/v1","project_id":project,
      "revision":revision,"verdict":"PASS","receipt_id":"guardian-pass"}
    technical={"schema":"chacha.dev/sentinel-technical-receipt/v1","project_id":project,
      "revision":revision,"verdict":"PASS","receipt_id":"sentinel-pass"}
    good=mod.combine(functional,technical,project,revision)
    mismatch=mod.combine(functional,{**technical,"revision":"wrong"},project,revision)
    blocked=mod.combine({**functional,"verdict":"BLOCK"},technical,project,revision)
    return {"agent_id":"release-engineer","adapter":"external-assurance-release-gate","actual":{
      "good_allowed":good.get("production_allowed"),"good_reasons":good.get("reason_codes"),
      "mismatch_blocked":mismatch.get("production_allowed") is False,
      "mismatch_reason":"SENTINEL_REVISION_MISMATCH" in (mismatch.get("reason_codes") or []),
      "guardian_blocked":blocked.get("production_allowed") is False,
      "guardian_reason":"GUARDIAN_FUNCTIONAL_NOT_PASS" in (blocked.get("reason_codes") or []),
      "remediation_owner":good.get("remediation_owner"),
      "guardian_direct_mutation":good.get("guardian_direct_mutation"),
      "sentinel_direct_mutation":good.get("sentinel_direct_mutation"),
      "automatic_external_spend_eur":good.get("automatic_external_spend_eur")
    }}

ADAPTERS={"guardian":guardian,"sentinel":sentinel,"bastion":bastion,"autonomous-recovery-agent":recovery,
          "security-reviewer":security_reviewer,"recovery-engineer":recovery_engineer,
          "platform-cloud-engineer":platform_cloud_engineer,"data-architect":data_architect,
          "release-engineer":release_engineer}

def execute(agent_id:str,repo_root:Path)->dict[str,Any]:
    fn=ADAPTERS.get(agent_id)
    if fn is None:raise KeyError("NO_EXECUTABLE_ADAPTER:"+agent_id)
    return fn(repo_root.resolve())
