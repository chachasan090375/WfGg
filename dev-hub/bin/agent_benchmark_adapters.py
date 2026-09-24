#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
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

ADAPTERS={"guardian":guardian,"sentinel":sentinel,"bastion":bastion,"autonomous-recovery-agent":recovery}

def execute(agent_id:str,repo_root:Path)->dict[str,Any]:
    fn=ADAPTERS.get(agent_id)
    if fn is None:raise KeyError("NO_EXECUTABLE_ADAPTER:"+agent_id)
    return fn(repo_root.resolve())
