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
              "task_id":"design:"+agent_id,"role":agent_id,"artifact_kind":mod.expected_artifact_kind("design:"+agent_id,agent_id),"status":"PROPOSED",
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


def _fresh_watch()->dict[str,Any]:
    return {"eligible_provider_candidates":[{"id":"v653-zero-cost","external_spend_eur":0}],
      "branch_blueprints":[],"snapshot_freshness":"FRESH","targeted_refresh_performed":False,
      "source_snapshot_digest":"v653-benchmark-watch","zero_spend_candidate_available":True,
      "selection_rule":"ZERO_SPEND_FIRST","automatic_external_spend_eur":0}

def _foundry_memory_brief()->dict[str,Any]:
    return {"schema":"chacha.dev/central-memory-recall/v1","brief_digest":"v653-memory",
      "source_memory_snapshot_digest":"v653-memory-snapshot","trusted_memory_count":1,"caution_count":2,
      "memory_authority":"ADVISORY",
      "trusted_component_candidates":[{"component_kind":"agent","component_id":"graphics-agent","domain":"graphics",
        "confidence":0.97,"verified_success_count":6}],
      "caution_component_candidates":[
        {"component_kind":"agent","component_id":"graphics-old-agent","domain":"graphics","confidence":0.31},
        {"component_kind":"architecture","component_id":"graphics-old-architecture","domain":"graphics","confidence":0.25}],
      "current_best_reuse_candidates":[{"component_kind":"branch","component_id":"graphics-reusable-branch",
        "domain":"graphics","confidence":0.98,"verified_success_count":8}],
      "trusted_memory":[],"cautions":[]}

def _foundry_preplan()->dict[str,Any]:
    return {"schema":"chacha.dev/domain-plan/v1","mode":"implementation","implementation_allowed":True,
      "intent":{"summary":"graphics generation"},
      "packages":[{"id":"domain:graphics","domain":"graphics","kind":"primary",
        "roles":["graphics-old-agent","graphics-agent"],"capabilities":["image-generation"],"toolchain":[]}]}

def agent_foundry_architect(repo:Path)->dict[str,Any]:
    mod=loadmod("v653_agent_foundry",repo/"dev-hub/bin/agent-foundry-planner.py")
    old_consult=mod.tw.consult;mod.tw.consult=lambda *a,**k:_fresh_watch()
    try:
        cfg=load(repo/"dev-hub/config/agent-foundry.v1.json")
        routing={"roles":{"graphics-agent":{"capabilities":["image-generation"]},
                          "graphics-old-agent":{"capabilities":["image-generation"]}}}
        out=mod.build(_foundry_preplan(),cfg,routing,"v653-project",_foundry_memory_brief())
        d=out["decisions"][0]
        return {"agent_id":"agent-foundry-architect","adapter":"agent-foundry-memory-guided-planner","actual":{
          "decision":d.get("decision"),"agent_id":d.get("agent_id"),"memory_guided_decision":d.get("memory_guided_decision"),
          "excluded_roles":d.get("memory_excluded_roles") or [],"preferred_roles":d.get("memory_preferred_roles") or [],
          "technology_watch_consulted":out.get("technology_watch_consulted"),
          "central_memory_consumed":out.get("central_memory_recall_consumed"),
          "replan_required":out.get("replan_required"),"dispatch_allowed":out.get("dispatch_allowed"),
          "capabilities":d.get("capabilities") or [],
          "auto_spend":((d.get("technology_watch") or {}).get("automatic_external_spend_eur"))
        }}
    finally:mod.tw.consult=old_consult

def branch_foundry_architect(repo:Path)->dict[str,Any]:
    agent=loadmod("v653_agent_for_branch",repo/"dev-hub/bin/agent-foundry-planner.py")
    mod=loadmod("v653_branch_foundry",repo/"dev-hub/bin/branch-foundry-planner.py")
    old_a=agent.tw.consult;old_b=mod.tw.consult
    agent.tw.consult=lambda *a,**k:_fresh_watch();mod.tw.consult=lambda *a,**k:_fresh_watch()
    try:
        pre=_foundry_preplan();brief=_foundry_memory_brief()
        routing={"roles":{"graphics-agent":{"capabilities":["image-generation"]},
                          "graphics-old-agent":{"capabilities":["image-generation"]}}}
        atop=agent.build(pre,load(repo/"dev-hub/config/agent-foundry.v1.json"),routing,"v653-project",brief)
        out=mod.build(pre,load(repo/"dev-hub/config/branch-foundry.v1.json"),"v653-project",atop,brief)
        d=out["decisions"][0]
        return {"agent_id":"branch-foundry-architect","adapter":"branch-foundry-memory-guided-planner","actual":{
          "dispatch_allowed":out.get("dispatch_allowed"),"decision":d.get("decision"),
          "memory_reuse_candidates_considered":d.get("memory_reuse_candidates_considered"),
          "negative_fast_reuse_block":d.get("memory_negative_fast_reuse_block"),
          "memory_guided_decision":d.get("memory_guided_decision"),
          "technology_watch_consulted":out.get("technology_watch_consulted"),
          "central_memory_consumed":out.get("central_memory_recall_consumed"),
          "external_spend_eur":(out.get("summary") or {}).get("external_spend_eur"),
          "resource_budget":d.get("resource_budget"),"reason":d.get("reason")
        }}
    finally:agent.tw.consult=old_a;mod.tw.consult=old_b

def capability_foundry_architect(repo:Path)->dict[str,Any]:
    mod=loadmod("v653_capability_foundry",repo/"dev-hub/bin/capability-foundry.py")
    old_consult=mod.tw.consult;mod.tw.consult=lambda *a,**k:_fresh_watch()
    with tempfile.TemporaryDirectory(prefix="v653-capability-foundry-") as td:
        t=Path(td);req=t/"request.json";domains=t/"domains.json";caps=t/"caps.json";mem=t/"memory.json"
        out=t/"out.json";do=t/"domains-out.json";co=t/"caps-out.json";ro=t/"routing-out.json"
        req.write_text(json.dumps({"project_id":"v653-project","missing_capabilities":[{
          "id":"image-generation","domain":"graphics",
          "architecture_candidates":[{"id":"graphics-old-agent"},{"id":"fresh-design"}]}]})+"\n")
        domains.write_text(json.dumps({"domains":{"graphics":{"orchestrator":"graphics-orchestrator"}}})+"\n")
        caps.write_text(json.dumps({"capabilities":{}})+"\n")
        mem.write_text(json.dumps(_foundry_memory_brief())+"\n")
        oldargv=sys.argv
        try:
            sys.argv=["capability-foundry.py","--request",str(req),"--policy",str(repo/"dev-hub/config/capability-foundry.v1.json"),
              "--domains",str(domains),"--capabilities",str(caps),"--memory-brief",str(mem),"--output",str(out),
              "--domain-overlay",str(do),"--capability-overlay",str(co),"--routing-overlay",str(ro)]
            with contextlib.redirect_stdout(io.StringIO()):mod.main()
        finally:sys.argv=oldargv;mod.tw.consult=old_consult
        x=load(out);p=x["plans"][0]
        return {"agent_id":"capability-foundry-architect","adapter":"capability-foundry-memory-guided-planner","actual":{
          "central_memory_consumed":x.get("central_memory_recall_consumed"),"memory_guided_plans":x.get("memory_guided_plans"),
          "old_candidate_excluded":all(str(c.get("id") or "")!="graphics-old-agent" for c in p.get("architecture_candidates") or []),
          "fresh_candidate_present":any(str(c.get("id") or "")=="fresh-design" for c in p.get("architecture_candidates") or []),
          "technology_watch_consulted":p.get("technology_watch",{}).get("consulted"),
          "created_capability_count":x.get("created_capability_count"),"created_domain_count":x.get("created_domain_count"),
          "promotion_requires_qualification":x.get("promotion_requires_qualification"),
          "sandbox_required":p.get("sandbox_required"),"rollback_required":p.get("rollback_required"),
          "capability":p.get("capability")
        }}

def logician_agent(repo:Path)->dict[str,Any]:
    mod=loadmod("v653_logician",repo/"dev-hub/bin/agent_evolution_logician.py")
    sc={"dimensions":{"accuracy":45.0,"learning_quality":40.0,"robustness":70.0},
        "unmeasured_dimensions":["coverage","calibration","handoff_quality"],"measurement_coverage_pct":30.0}
    out=mod.build("v653-subject",sc);paths=out.get("falsification_paths") or []
    return {"agent_id":"logician","adapter":"agent-evolution-logician","actual":{
      "decision_authority":out.get("decision_authority"),"direct_agent_mutation":out.get("direct_agent_mutation"),
      "automatic_external_spend_eur":out.get("automatic_external_spend_eur"),"path_count":len(paths),
      "high_accuracy_routes":[x.get("route") for x in paths if x.get("dimension")=="accuracy" and x.get("priority")=="HIGH"],
      "learning_routes":[x.get("route") for x in paths if x.get("dimension")=="learning_quality"],
      "gap_routes":[x.get("dimension") for x in paths if x.get("route")=="EVIDENCE_GAP_INSTRUMENTATION"],
      "shadow_route_present":any(x.get("route")=="INCUMBENT_VS_CANDIDATE_SHADOW_COMPARISON" for x in paths)
    }}

def technology_watch_agent(repo:Path)->dict[str,Any]:
    tts=loadmod("v653_truth_scoring",repo/"dev-hub/bin/technology_truth_scoring.py")
    tsr=loadmod("v653_source_reputation",repo/"dev-hub/bin/technology_source_reputation.py")
    policy=load(repo/"dev-hub/config/technology-truth-scoring.v1.json")
    rep=load(repo/"dev-hub/config/technology-source-reputation.v1.json")
    def dossier(version="1.8.4",release="2026-06-01"):
        return {"schema":"chacha.dev/technology-candidate-dossier/v1","technology_id":"v653-runtime","publisher":"V653Vendor",
          "version":version,"release_date":release,"as_of":"2026-09-24T00:00:00Z","blast_radius":"medium",
          "claims":[{"id":"claim-core","class":"runtime","required":True}],
          "evidence":[
            {"id":"doc","claim_id":"claim-core","type":"official_technical","origin":"vendor-doc","independence_group":"vendor","verified":True,"stance":"SUPPORT"},
            {"id":"ind","claim_id":"claim-core","type":"independent_technical","origin":"independent-lab","independence_group":"independent","verified":True,"stance":"SUPPORT"},
            {"id":"exec","claim_id":"claim-core","type":"executable_reproduction","origin":"chacha-lab","independence_group":"exec","verified":True,"reproducible":True,"stance":"SUPPORT"},
            {"id":"pilot","claim_id":"claim-core","type":"project_pilot","origin":"chacha-pilot","independence_group":"pilot","verified":True,"reproducible":True,"stance":"SUPPORT"}],
          "operational":{"maintenance_health":95,"security_health":95,"unresolved_critical_issues":0,"unresolved_high_impact_issues":0,
            "unresolved_medium_issues":0,"regression_rate_pct":1,"rollback_tested":True,"shadow_passed":True,"pilot_passed":True},
          "architecture_fit":{"compatibility":92,"security_fit":92,"resource_efficiency":90,"observability":90,
            "rollback_readiness":95,"integration_fit":92,"cost_fit":100,"migration_safety":92},"outcomes":[]}
    good=dossier()
    marketing=copy.deepcopy(good);marketing["evidence"]=[{"id":"m","claim_id":"claim-core","type":"marketing","origin":"vendor-marketing",
      "independence_group":"vendor","verified":True,"stance":"SUPPORT"}]
    contradictory=copy.deepcopy(good);contradictory["evidence"].append({"id":"neg","claim_id":"claim-core","type":"independent_technical",
      "origin":"failure-lab","independence_group":"negative","verified":True,"stance":"CONTRADICT"})
    gr=tts.evaluate(good,policy,rep,{})
    mr=tts.evaluate(marketing,policy,rep,{})
    cr=tts.evaluate(contradictory,policy,rep,{})
    before=tsr.profile_confidence(rep,"V653Vendor")
    rep_bad=tsr.apply_event(rep,{"publisher":"V653Vendor","outcome":"CONTRADICTED","claim_class":"runtime","evidence_ref":"v653:negative"})
    after_bad=tsr.profile_confidence(rep_bad,"V653Vendor")
    rep_good=tsr.apply_event(rep_bad,{"publisher":"V653Vendor","outcome":"CONFIRMED_EXECUTABLE","claim_class":"runtime","evidence_ref":"v653:positive"})
    after_good=tsr.profile_confidence(rep_good,"V653Vendor")
    new=dossier("2.0.0","2026-09-23");new["operational"].update({"rollback_tested":False,"shadow_passed":False,"pilot_passed":False})
    nr=tts.evaluate(new,policy,rep,{})
    selected=tts.select_verified_safe([nr,gr])
    return {"agent_id":"technology-watch-agent","adapter":"technology-truth-scoring-and-reputation","actual":{
      "good_recommendation":gr.get("recommendation_class"),"good_truth":gr.get("technical_truth_score"),
      "marketing_only":mr.get("marketing_only"),"marketing_recommendation":mr.get("recommendation_class"),
      "contradiction_detected":cr.get("contradictory_evidence"),"additional_verification":cr.get("additional_verification_required"),
      "selected_version":((selected.get("selected") or {}).get("version")),"latest_version_priority":selected.get("latest_version_priority"),
      "confidence_before":before,"confidence_after_contradiction":after_bad,"confidence_after_confirmation":after_good,
      "evidence_graph_present":bool((gr.get("evidence_graph") or {}).get("nodes")) and bool((gr.get("evidence_graph") or {}).get("edges")),"permission_escalation":gr.get("permission_escalation"),"automatic_external_spend_eur":gr.get("automatic_external_spend_eur")
    }}

def acceptance_engineer(repo:Path)->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="v654-acceptance-") as td:
        t=Path(td);contract=t/"contract.json";good_e=t/"good.json";bad_e=t/"bad.json";good_o=t/"good-out.json";bad_o=t/"bad-out.json"
        contract.write_text(json.dumps({"criteria":[
          {"criterion_id":"functional-1","dimension":"functional","required":True,"owner":"acceptance-engineer"},
          {"criterion_id":"security-1","dimension":"security","required":True,"owner":"security-reviewer"}]})+"\n",encoding="utf-8")
        good_e.write_text(json.dumps({"criteria":[{"criterion_id":"functional-1","state":"PASS","evidence":["fixture:functional"]},{"criterion_id":"security-1","state":"PASS","evidence":["fixture:security"]}]})+"\n",encoding="utf-8")
        bad_e.write_text(json.dumps({"criteria":[{"criterion_id":"functional-1","state":"PASS","evidence":["fixture:functional"]},{"criterion_id":"security-1","state":"FAIL","evidence":["fixture:negative"]}]})+"\n",encoding="utf-8")
        def run(ev,out):
            p=subprocess.run([sys.executable,str(repo/"dev-hub/bin/acceptance-engine.py"),"--contract",str(contract),"--evidence",str(ev),"--output",str(out)],
              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
            return p,load(out) if out.is_file() else {}
        gp,g=run(good_e,good_o);bp,b=run(bad_e,bad_o)
        return {"agent_id":"acceptance-engineer","adapter":"acceptance-engine","actual":{
          "good_code":gp.returncode,"good_accepted":g.get("accepted"),"good_delivery":g.get("delivery_allowed"),
          "good_final_delivery":g.get("final_delivery_allowed"),"good_final_gate":g.get("final_delivery_gate"),
          "good_rows":g.get("criteria") or [],"bad_code":bp.returncode,"bad_accepted":b.get("accepted"),
          "bad_delivery":b.get("delivery_allowed"),"bad_routes":b.get("return_to_factories") or {},
          "bad_final_delivery":b.get("final_delivery_allowed"),"schema":g.get("schema")
        }}

def contract_integrator(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"contract-integrator","dependencies")

def integration_architect(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"integration-architect","dependencies")

def ergonomist_agent(repo:Path)->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="v654-ergonomist-") as td:
        t=Path(td);policy=repo/"dev-hub/config/ux-planning.v1.json"
        def run(case,n,user):
            intent=t/(case+"-intent.json");contract=t/(case+"-contract.json");pre=t/(case+"-pre.json");out=t/(case+"-out.json")
            intent.write_text(json.dumps({"text":"web app dashboard" if user else "database maintenance task"})+"\n",encoding="utf-8")
            contract.write_text(json.dumps({"contract_id":case,"functional_intent":"web app dashboard" if user else "database maintenance task",
              "audiences":["operator"] if user else [],"styles":[]})+"\n",encoding="utf-8")
            packages=[{"id":f"p{i}","domain":"frontend" if user else "backend","kind":"primary","capabilities":["web"] if user else ["database-migrate"]} for i in range(n)]
            pre.write_text(json.dumps({"packages":packages,"primary_domains":["frontend"] if user else ["backend"]})+"\n",encoding="utf-8")
            p=subprocess.run([sys.executable,str(repo/"dev-hub/bin/ux-planning-engine.py"),"--intent",str(intent),"--contract",str(contract),"--preplan",str(pre),"--policy",str(policy),"--output",str(out)],
              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
            return p,load(out) if out.is_file() else {}
        np,n=run("non-user",1,False);kp,k=run("simple",1,True);rp,r=run("reconsider",3,True);xp,x=run("replan",6,True)
        return {"agent_id":"ergonomist","adapter":"ux-planning-engine","actual":{
          "non_user_code":np.returncode,"non_user_status":n.get("challenge_status"),"non_user_facing":n.get("user_facing"),
          "simple_code":kp.returncode,"simple_status":k.get("challenge_status"),"simple_handoff":((k.get("ux_contract") or {}).get("curator_handoff_required")),
          "reconsider_code":rp.returncode,"reconsider_status":r.get("challenge_status"),"reconsider_brain":r.get("central_brain_response_required"),
          "replan_code":xp.returncode,"replan_status":x.get("challenge_status"),"replan_next":x.get("recommended_next_action"),
          "direct_mutation":x.get("direct_mutation"),"architecture_council":x.get("architecture_council_final_authority"),
          "recommendation_count":len((k.get("ux_contract") or {}).get("recommendations") or []),
          "digest_present":str(x.get("report_digest") or "").startswith("sha256:"),"automatic_external_spend_eur":x.get("automatic_external_spend_eur")
        }}


def backend_api_architect(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"backend-api-architect","backend_api")

def frontend_architect(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"frontend-architect","frontend")

def product_domain_architect(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"product-domain-architect","product_domain")

def documentation_adr_agent(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"documentation-adr-agent","documentation")


def test_engineer(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"test-engineer","testing")

def performance_engineer(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"performance-engineer","performance")

def sre_observability_engineer(repo:Path)->dict[str,Any]:
    return _architect_role_contract(repo,"sre-observability-engineer","observability")

ADAPTERS={"guardian":guardian,"sentinel":sentinel,"bastion":bastion,"autonomous-recovery-agent":recovery,
          "security-reviewer":security_reviewer,"recovery-engineer":recovery_engineer,
          "platform-cloud-engineer":platform_cloud_engineer,"data-architect":data_architect,
          "release-engineer":release_engineer,"backend-api-architect":backend_api_architect,
          "frontend-architect":frontend_architect,"product-domain-architect":product_domain_architect,
          "documentation-adr-agent":documentation_adr_agent,"test-engineer":test_engineer,
          "performance-engineer":performance_engineer,"sre-observability-engineer":sre_observability_engineer,
          "agent-foundry-architect":agent_foundry_architect,"branch-foundry-architect":branch_foundry_architect,"capability-foundry-architect":capability_foundry_architect,"logician":logician_agent,"technology-watch-agent":technology_watch_agent,"acceptance-engineer":acceptance_engineer,"contract-integrator":contract_integrator,"integration-architect":integration_architect,"ergonomist":ergonomist_agent}

def execute(agent_id:str,repo_root:Path)->dict[str,Any]:
    fn=ADAPTERS.get(agent_id)
    if fn is None:raise KeyError("NO_EXECUTABLE_ADAPTER:"+agent_id)
    return fn(repo_root.resolve())
