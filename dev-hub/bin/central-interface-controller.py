#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, re, shutil, subprocess, sys, time, uuid
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA="chacha.dev/central-interface-receipt/v1"
HUMAN_INTENT_SCHEMA="chacha.dev/human-interface-intent/v1"
HUMAN_RESPONSE_SCHEMA="chacha.dev/human-interface-response/v1"
BOOTSTRAP_SCHEMA="chacha.dev/autonomous-project-bootstrap/v1"
PROJECT_CONTROL_SCHEMA="chacha.dev/project-control-response/v1"

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def file_digest(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def runtime_revision(repo_root:Path)->str:
    p=repo_root/".revision"
    return p.read_text(encoding="utf-8").strip() if p.is_file() else "UNKNOWN"

def runtime_version(repo_root:Path)->str:
    p=repo_root/"dev-hub/bin/autonomous-project-orchestrator.py"
    if not p.is_file():return "UNKNOWN"
    m=re.search(r'"version"\s*:\s*"([^"]+)"',p.read_text(encoding="utf-8",errors="ignore"))
    return m.group(1) if m else "UNKNOWN"

def workspace_tree_digest(root:Path)->str:
    h=hashlib.sha256()
    if not root.is_dir():return "sha256:"+h.hexdigest()
    for q in sorted((x for x in root.rglob("*") if x.is_file() and ".git" not in x.parts),key=lambda x:x.as_posix()):
        rel=q.relative_to(root).as_posix().encode();data=q.read_bytes();h.update(len(rel).to_bytes(8,"big"));h.update(rel);h.update(len(data).to_bytes(8,"big"));h.update(data)
    return "sha256:"+h.hexdigest()

def materialize_development_workspaces(repo_root:Path,runtime_root:Path,session_project:str,graph:dict[str,Any],receipt:Path)->dict[str,Any]:
    rows=[];project_root=(runtime_root/"projects").resolve()
    if session_project!="chacha-dev-platform":
        out={"schema":"chacha.dev/development-workspace-materialization/v1","status":"NOT_APPLICABLE","session_project":session_project,"rows":[],"automatic_external_spend_eur":0};save(receipt,out);return out
    ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc','.revision','.tree','.release-preparation.json','.env','.env.*')
    for task in graph.get("tasks") or []:
        if not isinstance(task,dict):continue
        caps={str(x) for x in task.get("capabilities") or []};meta=task.get("metadata") if isinstance(task.get("metadata"),dict) else {}
        if "code-edit" not in caps or str(task.get("permission") or "")!="workspace-write":continue
        raw=str(meta.get("branch_workspace") or "").strip()
        if not raw:
            rows.append({"task_id":task.get("id"),"status":"BLOCKED","reason":"BRANCH_WORKSPACE_MISSING"});continue
        ws=Path(raw).resolve(strict=False)
        try:ws.relative_to(project_root)
        except Exception:
            rows.append({"task_id":task.get("id"),"status":"BLOCKED","reason":"BRANCH_WORKSPACE_OUTSIDE_GOVERNED_ROOT","workspace":str(ws)});continue
        if ws.exists() and any(ws.iterdir()):
            rows.append({"task_id":task.get("id"),"status":"REUSED_EXISTING","workspace":str(ws),"tree_digest":workspace_tree_digest(ws)});continue
        ws.mkdir(parents=True,exist_ok=True)
        for src in repo_root.iterdir():
            if src.name in {'.git','__pycache__','.revision','.tree','.release-preparation.json'} or src.name=='.env' or src.name.startswith('.env.'):continue
            dst=ws/src.name
            if src.is_dir():shutil.copytree(src,dst,dirs_exist_ok=True,ignore=ignore)
            elif src.is_file():shutil.copy2(src,dst)
        git_info={"initialized":False,"baseline_commit":None,"remote_count":0}
        try:
            init=subprocess.run(["git","-C",str(ws),"init","-q"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
            add=subprocess.run(["git","-C",str(ws),"add","-A"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60) if init.returncode==0 else init
            commit=subprocess.run(["git","-C",str(ws),"-c","user.name=ChaCha DEV","-c","user.email=chacha-dev@local.invalid","commit","-qm","ChaCha DEV governed baseline"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60) if add.returncode==0 else add
            if commit.returncode!=0:raise RuntimeError("WORKSPACE_BASELINE_GIT_COMMIT_FAILED:"+(commit.stderr or commit.stdout)[-300:])
            rev=subprocess.run(["git","-C",str(ws),"rev-parse","HEAD"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=15)
            rem=subprocess.run(["git","-C",str(ws),"remote"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=15)
            if rev.returncode!=0 or rem.returncode!=0:raise RuntimeError("WORKSPACE_BASELINE_GIT_VERIFY_FAILED")
            git_info={"initialized":True,"baseline_commit":rev.stdout.strip(),"remote_count":len([x for x in rem.stdout.splitlines() if x.strip()])}
            if git_info["remote_count"]!=0:raise RuntimeError("WORKSPACE_BASELINE_REMOTE_FORBIDDEN")
        except Exception as exc:
            rows.append({"task_id":task.get("id"),"status":"BLOCKED","reason":str(exc)[:500],"workspace":str(ws)});continue
        rows.append({"task_id":task.get("id"),"status":"MATERIALIZED","workspace":str(ws),"source_revision":runtime_revision(repo_root),"source_tree_digest":workspace_tree_digest(repo_root),"workspace_tree_digest":workspace_tree_digest(ws),"isolated_git":git_info})
    blocked=[r for r in rows if r.get("status")=="BLOCKED"]
    out={"schema":"chacha.dev/development-workspace-materialization/v1","status":"BLOCKED" if blocked else "PASS","session_project":session_project,"rows":rows,"automatic_external_spend_eur":0};save(receipt,out);return out

TARGET_REQUEST_RX=re.compile(r"\bdor-[0-9a-f]{32}\b",re.I)
RECOVERY_CUES=(
    "reprise","reprendre","repris","resume","recover","recovery",
    "répar","repair","blocage","blocked","continuation","continue",
    "adapter_enablement_required","provider_health_probe_required",
    "provider_probe_definition_required","provider_binding_required",
    "task_graph_decomposition_required","domain_execution_verification_required"
)

def targeted_recovery_request_id(intent:dict[str,Any],runtime_root:Path)->str|None:
    if str(intent.get("project_id") or "")!="chacha-dev-platform":return None
    if str(intent.get("target_scope") or "PLATFORM").upper()!="PLATFORM":return None
    text=str(intent.get("user_text") or "")
    folded=text.casefold()
    if not any(cue in folded for cue in RECOVERY_CUES):return None
    for match in TARGET_REQUEST_RX.finditer(text):
        request_id=match.group(0).lower()
        prior=runtime_root/"direct-operator"/"responses"/(request_id+".json")
        if not prior.is_file():continue
        try:payload=load(prior)
        except Exception:continue
        if payload.get("schema")!=HUMAN_RESPONSE_SCHEMA:continue
        if str(payload.get("project_id") or "")!="chacha-dev-platform":continue
        return request_id
    return None

def handle_targeted_recovery(a,target_request_id:str)->dict[str,Any]:
    prior=a.runtime_root/"direct-operator"/"responses"/(target_request_id+".json")
    if not prior.is_file():
        return make_receipt("CONTINUE","chacha-dev-platform","BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",[],
          {"reason":"TARGET_RECOVERY_PRIOR_RESPONSE_MISSING","target_request_id":target_request_id})
    resume=argparse.Namespace(**vars(a))
    resume.project="chacha-dev-platform"
    resume.prior_response=prior
    resume.expected_response_digest=file_digest(prior)
    receipt=handle_continue(resume)
    receipt.setdefault("decision",{})["targeted_platform_recovery"]={
      "target_request_id":target_request_id,
      "generic_bootstrap_replayed":False,
      "functional_translator_replayed":False,
      "guardian_bypass":False,
      "automatic_external_spend_eur":0
    }
    return receipt


def run_json(cmd:list[str],timeout:int=300)->tuple[int,dict[str,Any]|None,str,str]:
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124,None,"","TIMEOUT"
    payload=None
    if p.stdout.strip():
        try:payload=json.loads(p.stdout)
        except Exception:
            try:
                s=p.stdout.index("{");e=p.stdout.rindex("}")+1;payload=json.loads(p.stdout[s:e])
            except Exception:payload=None
    return p.returncode,payload,p.stdout,p.stderr

def project_control(repo_root:Path,tool:Path,project:str,operation:str,*extra:str)->tuple[int,dict[str,Any]|None,str,str]:
    return run_json([sys.executable,str(tool),"--repo-root",str(repo_root),"--json",operation,"--project",project,*extra],3700)

def verify_domain_run_results(a,execution_project:str,record:dict[str,Any],bound_graph:Path,adapter_registry:Path)->dict[str,Any]:
    if not bound_graph.is_file():
        return {"status":"BLOCKED","blockers":["BOUND_TASK_GRAPH_MISSING"],"rows":[],"evidence_refs":[]}
    graph=load(bound_graph)
    tasks={str(t.get("id") or ""):t for t in (graph.get("tasks") or []) if isinstance(t,dict)}
    rows=[];blockers=[];refs=[]
    for wave in record.get("waves") or []:
        for task_rec in (wave.get("tasks") or [] if isinstance(wave,dict) else []):
            if not isinstance(task_rec,dict) or task_rec.get("status")!="SUCCEEDED":continue
            task_id=str(task_rec.get("task_id") or "")
            source=tasks.get(task_id) or {}
            mode=str(((source.get("verification") or {}).get("mode")) or "machine")
            result_path=Path(str(task_rec.get("task_result") or ""))
            if not result_path.is_file():
                blockers.append("TASK_RESULT_MISSING:"+task_id);rows.append({"task_id":task_id,"status":"BLOCKED","reason":"TASK_RESULT_MISSING"});continue
            if mode=="human":
                blockers.append("HUMAN_VERIFICATION_REQUIRED:"+task_id);rows.append({"task_id":task_id,"status":"BLOCKED","reason":"HUMAN_VERIFICATION_REQUIRED"});continue
            method="independent-agent" if mode=="independent-agent" else "machine"
            rc,payload,stdout,stderr=project_control(a.repo_root,a.project_control,execution_project,"verify-result",
                "--result",str(result_path),"--graph",str(bound_graph),"--adapters",str(adapter_registry),
                "--method",method,"--verifier","verification-broker","--ingest")
            details=(payload.get("details") or {}) if isinstance(payload,dict) else {}
            lineage_ok=bool(details.get("trusted_learning_context") is True and details.get("learning_context_status")=="TRUSTED_DISPATCH_CONTEXT")
            ok=bool(rc==0 and isinstance(payload,dict) and payload.get("status")=="OK" and str(details.get("verification_status") or "")=="VERIFIED" and lineage_ok)
            row={"task_id":task_id,"status":"VERIFIED" if ok else "BLOCKED","method":method,"project_control":payload,"returncode":rc}
            if not ok:
                row["stdout"]=stdout[-1200:];row["stderr"]=stderr[-1200:];blockers.append("TASK_VERIFICATION_FAILED:"+task_id)
            else:
                for art in payload.get("artifacts") or []:
                    ap=Path(str((art or {}).get("path") or ""))
                    if ap.is_file():refs.append(str(ap)+"#"+file_digest(ap))
            rows.append(row)
    expected=sum(
        1
        for wave in (record.get("waves") or []) if isinstance(wave,dict)
        for task in (wave.get("tasks") or []) if isinstance(task,dict) and task.get("status")=="SUCCEEDED"
    )
    verified=sum(1 for r in rows if r.get("status")=="VERIFIED")
    return {"status":"PASS" if not blockers and verified==expected else "BLOCKED","verified_count":verified,"expected_count":expected,"blockers":sorted(set(blockers)),"rows":rows,"evidence_refs":refs,"automatic_external_spend_eur":0}

def platform_status(repo_root:Path,runtime_root:Path)->dict[str,Any]:
    out={
      "platform_revision":runtime_revision(repo_root),
      "platform_version":runtime_version(repo_root),
      "emergency_stop_active":False,
      "guardian_all_hooks_active":None,
      "agent_count":None,
      "evidence_labels":{},
      "hygiene":None,
      "physical_release_count":None
    }
    try:
        ext=load(repo_root/"dev-hub/config/platform-extension.v1.json")
        out["platform_extension"]={
          "version":ext.get("version"),"name":ext.get("name"),
          "core_platform_compatibility":ext.get("core_platform_compatibility"),
          "components":ext.get("components") or []
        }
    except Exception:out["platform_extension"]=None
    try:out["emergency_stop_active"]=bool(load(runtime_root/"control/emergency-stop.json").get("active"))
    except Exception:pass
    try:out["guardian_all_hooks_active"]=load(runtime_root/"guardian/coverage-latest.json").get("all_hooks_active")
    except Exception:pass
    try:
        f=load(runtime_root/"agent-evolution/fleet-observatory-latest.json")
        out["agent_count"]=f.get("agent_count")
        labels={}
        for a in f.get("agents") or []:
            label=((a.get("scorecard") or {}).get("evidence_maturity_label"))
            if label:labels[label]=labels.get(label,0)+1
        out["evidence_labels"]=labels
    except Exception:pass
    try:
        h=load(runtime_root/"intendant/hygiene-latest.json")
        out["hygiene"]={k:h.get(k) for k in ("platform_revision","platform_version","threshold_reasons","metrics")}
    except Exception:pass
    try:
        releases=repo_root.resolve().parent.parent/"releases"
        out["physical_release_count"]=sum(1 for p in releases.iterdir() if p.is_dir())
    except Exception:pass
    return out

def make_receipt(command:str,project:str,status:str,next_action:str,evidence_refs:list[str],decision:dict[str,Any]|None=None)->dict[str,Any]:
    return {
      "schema":RECEIPT_SCHEMA,
      "receipt_id":"cirec-"+uuid.uuid4().hex,
      "observed_at":now_iso(),
      "command":command,
      "project_id":project,
      "status":status,
      "authority":"central-orchestrator",
      "brain_decision_obtained":True,
      "next_action":next_action,
      "evidence_refs":evidence_refs,
      "decision":decision or {},
      "automatic_external_spend_eur":0
    }

def classify_orchestrator_failure(stdout:str,stderr:str)->tuple[str,str,dict[str,Any]]:
    text=(str(stdout or "")+"\n"+str(stderr or ""))
    upper=text.upper()
    if "D1_ACCOUNT_QUOTA_CIRCUIT_OPEN" in upper or "D1_READ_QUOTA_EXHAUSTED" in upper or "D1_WRITE_QUOTA_EXHAUSTED" in upper or "DAILY ROW READ LIMIT" in upper:
        return (
          "AWAITING_EXTERNAL_CONDITION",
          "RETRY_WHEN_D1_AVAILABLE",
          {
            "human_message":"Le cerveau central a bien reçu la demande, mais le quota quotidien de la base D1 est temporairement atteint. J’ai arrêté l’exécution sans dépense externe.",
            "reason":"D1_ACCOUNT_QUOTA_CIRCUIT_OPEN",
            "external_dependency":"D1_DATABASE",
            "external_condition":"D1_QUOTA_RESET",
            "retryable":True,
            "authority_bypass":False,
            "stdout":str(stdout or "")[-1200:],
            "stderr":str(stderr or "")[-1200:]
          }
        )
    if "GUARDIAN_STAGE_UNAVAILABLE" in upper or "GUARDIAN_UNAVAILABLE_FAIL_CLOSED" in upper:
        return (
          "AWAITING_EXTERNAL_CONDITION",
          "RETRY_WHEN_GUARDIAN_AVAILABLE",
          {
            "human_message":"Le cerveau central a bien reçu la demande, mais le contrôle de sécurité Guardian est temporairement indisponible. J’ai arrêté l’exécution sans contourner ce contrôle.",
            "reason":"GUARDIAN_UNAVAILABLE_FAIL_CLOSED",
            "external_dependency":"GUARDIAN",
            "external_condition":"GUARDIAN_RUNTIME_AVAILABLE",
            "retryable":True,
            "authority_bypass":False,
            "stdout":str(stdout or "")[-1200:],
            "stderr":str(stderr or "")[-1200:]
          }
        )
    return (
      "BRAIN_UNAVAILABLE",
      "RETRY_WHEN_BRAIN_AVAILABLE",
      {"stdout":str(stdout or "")[-1200:],"stderr":str(stderr or "")[-1200:]}
    )

def orchestrate(repo_root:Path,orchestrator:Path,human_intent:dict[str,Any],out_dir:Path,continuation_of:str|None=None)->dict[str,Any]:
    request_id=str(human_intent.get("request_id") or uuid.uuid4().hex)
    central={
      "name":str(human_intent.get("title") or ("Human Interface Request "+request_id[:12])),
      "text":str(human_intent.get("user_text") or ""),
      "source":"central-interface-controller",
      "request_id":request_id,
      "target_scope":human_intent.get("target_scope") or "PLATFORM",
      "requested_project_id":human_intent.get("project_id") or "chacha-dev-platform",
      "domains":list(human_intent.get("domains") or []),
      "constraints":{
        "automatic_external_spend_eur":0,
        "interface_has_no_technical_decision_authority":True,
        "central_orchestrator_required":True
      }
    }
    if continuation_of:
        central["continuation"]={
          "command":"CONTINUE",
          "continuation_of_request_id":continuation_of,
          "fresh_central_revalidation_required":True
        }
    out_dir.mkdir(parents=True,exist_ok=True)
    central_path=out_dir/"central-intent.json";save(central_path,central)
    planning=out_dir/"planning";planning.mkdir(parents=True,exist_ok=True)
    p=subprocess.run([sys.executable,str(orchestrator),"--repo-root",str(repo_root),"--intent",str(central_path),"--output-dir",str(planning)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=300)
    bootstrap=planning/"bootstrap-result.json"
    if p.returncode!=0 or not bootstrap.is_file():
        status,next_action,decision=classify_orchestrator_failure(p.stdout,p.stderr)
        return make_receipt("CONTINUE" if continuation_of else "INSTRUCTION",
                            str(human_intent.get("project_id") or "chacha-dev-platform"),
                            status,next_action,[],decision)
    b=load(bootstrap)
    if b.get("schema")!=BOOTSTRAP_SCHEMA or not b.get("project_id"):
        return make_receipt("CONTINUE" if continuation_of else "INSTRUCTION",
                            str(human_intent.get("project_id") or "chacha-dev-platform"),
                            "BRAIN_RECEIPT_INVALID","RETRY_AFTER_RECEIPT_REPAIR",[str(bootstrap)],
                            {"bootstrap":b})
    refs=[str(bootstrap)+"#"+file_digest(bootstrap)]
    council=Path(str(b.get("architecture_decision_council") or ""))
    if council.is_file():refs.append(str(council)+"#"+file_digest(council))
    resume_ready=b.get("existing_candidate_resume_ready") is True
    allowed=resume_ready or (b.get("architecture_decision_allowed") is True and b.get("domain_dispatch_allowed") is True)
    status=("CONTINUED_PLAN_READY" if continuation_of else "PLAN_READY") if allowed else "BLOCKED"
    nxt=str(b.get("next_stage") or ("AWAIT_REPLAN" if not allowed else "AWAIT_CENTRAL_CONTINUATION"))
    decision={
      "schema":b.get("schema"),"version":b.get("version"),"project_id":b.get("project_id"),
      "architecture_decision_allowed":b.get("architecture_decision_allowed"),
      "domain_dispatch_allowed":b.get("domain_dispatch_allowed"),
      "runtime_schedulable":b.get("runtime_schedulable"),
      "central_compromise_found":b.get("central_compromise_found"),
      "next_stage":b.get("next_stage"),"external_spend_eur":b.get("external_spend_eur"),
      "bootstrap_result":str(bootstrap),"central_intent":str(central_path),
      "existing_candidate_resume_ready":resume_ready,
      "existing_candidate_resume":b.get("existing_candidate_resume"),
      "domain_factories_required":b.get("domain_factories_required"),
      "synthetic_project_created":b.get("synthetic_project_created")
    }
    if continuation_of:
        decision["continuation_of_request_id"]=continuation_of
        decision["fresh_central_brain_call"]=True
    r=make_receipt("CONTINUE" if continuation_of else "INSTRUCTION",str(b["project_id"]),status,nxt,refs,decision)
    return r

def handle_status(a)->dict[str,Any]:
    project=a.project
    if project!="chacha-dev-platform":
        rc,payload,stdout,stderr=project_control(a.repo_root,a.project_control,project,"status")
        if isinstance(payload,dict) and payload.get("schema")==PROJECT_CONTROL_SCHEMA:
            refs=[]
            for art in payload.get("artifacts") or []:
                p=Path(str(art.get("path") or ""))
                if p.is_file():refs.append(str(p)+"#"+file_digest(p))
            nxt=(payload.get("next_actions") or ["AWAIT_USER_DIRECTIVE"])[0]
            return make_receipt("STATUS",project,"OK" if rc==0 else str(payload.get("status") or "BLOCKED"),str(nxt),refs,{"project_control":payload})
    status=platform_status(a.repo_root,a.runtime_root)
    return make_receipt("STATUS","chacha-dev-platform","OK","AWAIT_USER_DIRECTIVE",[],{"platform_status":status})

def handle_instruction(a)->dict[str,Any]:
    hi=load(a.intent)
    if hi.get("schema")!=HUMAN_INTENT_SCHEMA:raise SystemExit("HUMAN_INTENT_SCHEMA_INVALID")
    recovery_target=targeted_recovery_request_id(hi,a.runtime_root)
    if recovery_target:
        return handle_targeted_recovery(a,recovery_target)
    return orchestrate(a.repo_root,a.orchestrator,hi,a.output_dir)


def external_condition_from_run(record:dict[str,Any])->dict[str,Any]|None:
    for wave in record.get("waves") or []:
        if not isinstance(wave,dict):continue
        for task in wave.get("tasks") or []:
            if not isinstance(task,dict):continue
            raw=str(task.get("task_result") or "")
            if not raw:continue
            path=Path(raw)
            if not path.is_file():continue
            try:result=load(path)
            except Exception:continue
            if str(result.get("summary") or "")!="PROVIDER_MODEL_QUOTA_EXHAUSTED":continue
            details={}
            for ev in result.get("evidence") or []:
                if isinstance(ev,dict) and isinstance(ev.get("details"),dict):details.update(ev["details"])
            return {
              "reason":"PROVIDER_MODEL_QUOTA_EXHAUSTED",
              "external_dependency":"AI_PROVIDER_MODEL",
              "external_condition":"PROVIDER_MODEL_QUOTA_RESET",
              "provider":details.get("provider") or "antigravity",
              "model":details.get("model") or "gemini-3.8-flash-medium",
              "resume_at":details.get("resume_at"),
              "retryable":True,
              "automatic_paid_upgrade":False,
              "automatic_external_spend_eur":0,
              "task_result":str(path),
              "human_message":("Le cerveau central a bien reçu la demande, mais le quota gratuit du modèle IA requis est temporairement épuisé. J’ai arrêté l’exécution sans achat ni dépense externe."+(" Reprise possible après le reset annoncé : "+str(details.get("resume_at"))+"." if details.get("resume_at") else ""))
            }
    return None

def domain_scheduler_run_controller(a,project:str,prior:dict[str,Any],df:dict[str,Any],readiness:dict[str,Any])->dict[str,Any]:
    graph=Path(str(df.get("domain_execution_graph") or ""))
    health=Path(str(readiness.get("provider_health_snapshot") or ""))
    refs=list(prior.get("evidence_refs") or [])
    if not graph.is_file():
        return make_receipt("CONTINUE",project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",refs,{"reason":"DOMAIN_EXECUTION_GRAPH_MISSING"})
    graph_payload=load(graph)
    execution_project=str(graph_payload.get("project") or project)
    handoff=a.output_dir/"domain-execution-handoff";handoff.mkdir(parents=True,exist_ok=True)
    materialization_path=handoff/"workspace-materialization.json"
    materialization=materialize_development_workspaces(a.repo_root,a.runtime_root,project,graph_payload,materialization_path)
    refs.append(str(materialization_path)+"#"+file_digest(materialization_path))
    if materialization.get("status")=="BLOCKED":
        return make_receipt("CONTINUE",project,"BLOCKED","DEVELOPMENT_WORKSPACE_MATERIALIZATION_REQUIRED",refs,{"workspace_materialization":materialization,"execution_project_id":execution_project})
    ledger=a.runtime_root/"evidence"/execution_project/"ledger.json"
    if not health.is_file():
        return make_receipt("CONTINUE",project,"BLOCKED","PROVIDER_HEALTH_PROBE_REQUIRED",refs,
                            {"reason":"PROVIDER_HEALTH_SNAPSHOT_MISSING","domain_factories":df,
                             "domain_toolchain_readiness":readiness,
                             "continuation_mode":"DOMAIN_EXECUTION_HANDOFF"})
    if not ledger.is_file():
        bootstrap=subprocess.run([sys.executable,str(a.project_control),"--repo-root",str(a.repo_root),"--json",
                                  "bootstrap-control-plane","--project",execution_project,
                                  "--actor","central-orchestrator","--profile","project"],
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=120)
        if bootstrap.returncode!=0 or not ledger.is_file():
            return make_receipt("CONTINUE",project,"BLOCKED","EVIDENCE_LEDGER_REQUIRED",refs,
                                {"reason":"EXECUTION_PROJECT_CONTROL_BOOTSTRAP_FAILED","ledger":str(ledger),
                                 "execution_project_id":execution_project,"stdout":bootstrap.stdout[-1600:],
                                 "stderr":bootstrap.stderr[-1600:],"continuation_mode":"DOMAIN_EXECUTION_HANDOFF"})
        refs.append(str(ledger)+"#"+file_digest(ledger))

    plan_path=handoff/"execution-plan.json"
    scheduler=a.repo_root/"dev-hub/bin/execution-scheduler.py"
    agent_contracts=Path(str((df.get("agent_contracts") or (Path(str(df.get("planning_dir") or ""))/"agent-role-contracts.json"))))
    component_contracts=Path(str((df.get("component_contracts") or (Path(str(df.get("planning_dir") or ""))/"component-role-contracts.json"))))
    role_contracts=a.repo_root/"dev-hub/config/guardian-role-contracts.v1.json"
    bound_graph=handoff/"bound-domain-execution-graph.json"
    if not agent_contracts.is_file() or not component_contracts.is_file() or not role_contracts.is_file():
        return make_receipt("CONTINUE",project,"BLOCKED","TASK_GUARDIAN_BINDING_REQUIRED",refs,
                            {"reason":"TASK_CONTRACT_BINDING_INPUTS_MISSING","agent_contracts":str(agent_contracts),
                             "component_contracts":str(component_contracts),"role_contracts":str(role_contracts),
                             "guardian_bypass":False})
    sched=subprocess.run([
        sys.executable,str(scheduler),
        "--graph",str(graph),
        "--registry",str(a.repo_root/"dev-hub/config/capability-registry.v1.json"),
        "--health",str(health),
        "--policy",str(a.repo_root/"dev-hub/config/execution-scheduler.v1.json"),
        "--agent-contracts",str(agent_contracts),
        "--component-contracts",str(component_contracts),
        "--role-contracts",str(role_contracts),
        "--bound-graph-output",str(bound_graph),
        "--require-guardian-binding",
        "--output",str(plan_path)
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=120)
    if not plan_path.is_file():
        return make_receipt("CONTINUE",project,"BLOCKED","SCHEDULER_FAILED",refs,
                            {"reason":"EXECUTION_PLAN_MISSING","stdout":sched.stdout[-1600:],
                             "stderr":sched.stderr[-1600:],"continuation_mode":"DOMAIN_EXECUTION_HANDOFF"})
    plan=load(plan_path)
    refs.append(str(plan_path)+"#"+file_digest(plan_path))
    blocked=int(((plan.get("summary") or {}).get("blocked_count") or 0))
    if blocked:
        return make_receipt("CONTINUE",project,"BLOCKED","SCHEDULER_BLOCKED",refs,
                            {"execution_plan":plan,"domain_factories":df,
                             "domain_toolchain_readiness":readiness,
                             "continuation_mode":"DOMAIN_EXECUTION_HANDOFF",
                             "run_controller_started":False})

    adapter_registry=Path(str(readiness.get("provider_adapter_registry") or (a.repo_root/"dev-hub/config/provider-adapters.v1.json")))
    if not adapter_registry.is_file():
        return make_receipt("CONTINUE",project,"BLOCKED","ADAPTER_REGISTRY_UNAVAILABLE",refs,
                            {"reason":"EFFECTIVE_ADAPTER_REGISTRY_MISSING","adapter_registry":str(adapter_registry),
                             "continuation_mode":"DOMAIN_EXECUTION_HANDOFF"})
    run_root=handoff/"runs"
    before=set(run_root.glob("run-*/run-record.json")) if run_root.exists() else set()
    controller=a.repo_root/"dev-hub/bin/run-controller.py"
    run=subprocess.run([
        sys.executable,str(controller),
        "--plan",str(plan_path),
        "--graph",str(bound_graph),
        "--ledger",str(ledger),
        "--policy",str(a.repo_root/"dev-hub/config/run-controller.v1.json"),
        "--adapters",str(adapter_registry),
        "--output-dir",str(run_root),
        "--execute"
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=3700)
    after=set(run_root.glob("run-*/run-record.json")) if run_root.exists() else set()
    created=sorted(after-before,key=lambda x:x.stat().st_mtime)
    if not created:
        created=sorted(after,key=lambda x:x.stat().st_mtime)
    if not created:
        return make_receipt("CONTINUE",project,"BLOCKED","RUN_CONTROLLER_FAILED",refs,
                            {"reason":"RUN_RECORD_MISSING","returncode":run.returncode,
                             "stdout":run.stdout[-1600:],"stderr":run.stderr[-1600:],
                             "continuation_mode":"DOMAIN_EXECUTION_HANDOFF"})
    run_record=created[-1]
    record=load(run_record)
    refs.append(str(run_record)+"#"+file_digest(run_record))
    summary=record.get("summary") or {}
    failed=int(summary.get("failed") or 0)
    run_blocked=int(summary.get("blocked") or 0)
    scheduled=int(((plan.get("summary") or {}).get("scheduled_count") or 0))
    succeeded=int(summary.get("succeeded") or 0)
    verification=None
    external_condition=external_condition_from_run(record)
    if external_condition is not None:
        status="AWAITING_EXTERNAL_CONDITION";next_action="RETRY_WHEN_PROVIDER_QUOTA_AVAILABLE"
    elif failed:
        status="BLOCKED";next_action="RUN_CONTROLLER_TASK_FAILED"
    elif run_blocked:
        status="BLOCKED";next_action="RUN_CONTROLLER_BLOCKED"
    elif succeeded==scheduled:
        verification=verify_domain_run_results(a,execution_project,record,bound_graph,adapter_registry)
        refs.extend(verification.get("evidence_refs") or [])
        if verification.get("status")=="PASS":
            status="COMPLETE";next_action="AWAIT_NEW_INSTRUCTION"
        else:
            status="BLOCKED";next_action="DOMAIN_EXECUTION_VERIFICATION_REQUIRED"
    else:
        status="CONTINUED";next_action="RUN_CONTROLLER_COMPLETE"
    receipt=make_receipt("CONTINUE",project,status,next_action,refs,{
        "domain_factories":df,
        "domain_toolchain_readiness":readiness,
        "execution_plan":str(plan_path),
        "run_record":str(run_record),
        "run_summary":summary,
        "independent_verification":verification,
        "domain_execution_verified":bool(isinstance(verification,dict) and verification.get("status")=="PASS"),
        "continuation_mode":"DOMAIN_EXECUTION_HANDOFF",
        "scheduler_started":True,
        "run_controller_started":True,
        "run_controller_execute_requested":True,
        "execution_project_id":execution_project,
        "provider_adapter_registry":str(adapter_registry),
        "production_approval_bypass":False,
        **(external_condition or {})
    })
    receipt["continuation_of_request_id"]=prior.get("request_id")
    return receipt


def provider_quota_condition_from_remediation(remediation:dict[str,Any]|None)->dict[str,Any]|None:
    if not isinstance(remediation,dict):return None
    for row in remediation.get("remediations") or []:
        if not isinstance(row,dict):continue
        refresh=row.get("economics_attestation_refresh") if isinstance(row.get("economics_attestation_refresh"),dict) else {}
        blockers={str(x) for x in row.get("blockers") or []}
        reasons={str(x) for x in refresh.get("reason_codes") or []}
        if "PROVIDER_MODEL_QUOTA_EXHAUSTED" not in blockers|reasons:continue
        return {
          "reason":"PROVIDER_MODEL_QUOTA_EXHAUSTED",
          "external_dependency":"AI_PROVIDER_MODEL",
          "external_condition":"PROVIDER_MODEL_QUOTA_RESET",
          "provider":row.get("provider") or "antigravity",
          "model":refresh.get("model") or "gemini-3.8-flash-medium",
          "resume_at":refresh.get("resume_at"),
          "retryable":True,
          "provider_execution_started":False,
          "adapter_invocation_started":False,
          "automatic_paid_upgrade":False,
          "automatic_external_spend_eur":0,
          "human_message":("Le cerveau central a bien reçu la demande, mais le quota gratuit du modèle IA requis est temporairement épuisé. J’ai arrêté l’exécution sans achat ni dépense externe."+(" Reprise possible après le reset annoncé : "+str(refresh.get("resume_at"))+"." if refresh.get("resume_at") else ""))
        }
    return None

def continue_domain_readiness(a,project:str,prior:dict[str,Any],df:dict[str,Any])->dict[str,Any]:
    planning=Path(str(df.get("planning_dir") or ""))
    if not planning.is_dir():
        return make_receipt("CONTINUE",project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",
                            list(prior.get("evidence_refs") or []),{"reason":"DOMAIN_FACTORY_PLANNING_CONTEXT_MISSING"})
    factory_runner=a.repo_root/"dev-hub/bin/domain-factory-runner.py"
    reconciled_factory_dir=a.output_dir/"domain-factories-reconciled"
    reconciled_result=reconciled_factory_dir/"domain-factory-result.json"
    fproc=subprocess.run([sys.executable,str(factory_runner),"--repo-root",str(a.repo_root),
                          "--planning-dir",str(planning),"--output-dir",str(reconciled_factory_dir)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=90)
    if not reconciled_result.is_file():
        return make_receipt("CONTINUE",project,"BLOCKED","DOMAIN_FACTORY_RECONCILIATION_REQUIRED",
                            list(prior.get("evidence_refs") or []),{"reason":"DOMAIN_FACTORY_RECONCILIATION_RESULT_MISSING"})
    reconciled=load(reconciled_result)
    if reconciled.get("status")!="READY":
        return make_receipt("CONTINUE",project,"BLOCKED",str(reconciled.get("next_stage") or "DOMAIN_FACTORY_RECONCILIATION_REQUIRED"),
                            [str(reconciled_result)+"#"+file_digest(reconciled_result)],{"domain_factories":reconciled,"continuation_mode":"DOMAIN_FACTORY_RECONCILIATION"})
    df=dict(df);df.update(reconciled)
    graph=Path(str(df.get("domain_execution_graph") or ""))
    factory_dir=graph.parent if graph.is_file() else Path("")
    if not planning.is_dir() or not graph.is_file() or not factory_dir.is_dir():
        return make_receipt("CONTINUE",project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",
                            list(prior.get("evidence_refs") or []),{"reason":"DOMAIN_FACTORY_CONTEXT_MISSING"})
    runner=a.repo_root/"dev-hub/bin/domain-toolchain-readiness.py"
    readiness_dir=a.output_dir/"domain-toolchain-readiness"
    readiness_path=readiness_dir/"domain-toolchain-readiness.json"
    readiness_dir.mkdir(parents=True,exist_ok=True)
    health=a.runtime_root/"health"/project/"providers.json"
    effective_adapters=readiness_dir/"effective-provider-adapters.v1.json"
    adapter_reconciliation=readiness_dir/"runtime-adapter-reconciliation.json"
    adapter_state=a.runtime_root/"registries/provider-adapter-runtime-state.v1.json"
    registry_tool=a.repo_root/"dev-hub/bin/runtime-adapter-registry.py"
    regproc=subprocess.run([sys.executable,str(registry_tool),"effective",
                            "--base",str(a.repo_root/"dev-hub/config/provider-adapters.v1.json"),
                            "--state",str(adapter_state),"--output",str(effective_adapters),
                            "--report",str(adapter_reconciliation)],
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if regproc.returncode!=0 or not effective_adapters.is_file():
        return make_receipt("CONTINUE",project,"BLOCKED","ADAPTER_RUNTIME_RECONCILIATION_REQUIRED",
                            list(prior.get("evidence_refs") or []),
                            {"reason":"EFFECTIVE_ADAPTER_REGISTRY_BUILD_FAILED","stdout":regproc.stdout[-1200:],
                             "stderr":regproc.stderr[-1200:],"adapter_state":str(adapter_state)})
    argv=[sys.executable,str(runner),"--repo-root",str(a.repo_root),
          "--planning-dir",str(planning),"--factory-dir",str(factory_dir),
          "--adapters",str(effective_adapters),"--output",str(readiness_path)]
    if health.is_file():
        argv += ["--health",str(health)]
    proc=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=90)
    if not readiness_path.is_file():
        return make_receipt("CONTINUE",project,"BLOCKED","DOMAIN_TOOLCHAIN_READINESS_FAILED",
                            list(prior.get("evidence_refs") or []),
                            {"reason":"DOMAIN_TOOLCHAIN_RESULT_MISSING",
                             "stdout":proc.stdout[-1600:],"stderr":proc.stderr[-1600:]})
    readiness=load(readiness_path)
    readiness["provider_adapter_registry"]=str(effective_adapters)
    save(readiness_path,readiness)
    refs=list(prior.get("evidence_refs") or [])
    refs.append(str(readiness_path)+"#"+file_digest(readiness_path))
    if adapter_reconciliation.is_file():refs.append(str(adapter_reconciliation)+"#"+file_digest(adapter_reconciliation))
    if readiness.get("status")=="READY":
        chained_prior=dict(prior);chained_prior["evidence_refs"]=refs
        return domain_scheduler_run_controller(a,project,chained_prior,df,readiness)

    remediation=None
    if readiness.get("next_stage") in {"ADAPTER_ENABLEMENT_REQUIRED","PROVIDER_HEALTH_PROBE_REQUIRED"}:
        remediation_path=readiness_dir/"governed-auto-remediation.json"
        remediator=a.repo_root/"dev-hub/bin/domain-readiness-auto-remediator.py"
        remproc=subprocess.run([sys.executable,str(remediator),"--repo-root",str(a.repo_root),
                                "--runtime-root",str(a.runtime_root),"--readiness",str(readiness_path),
                                "--output",str(remediation_path)],
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=420)
        if remediation_path.is_file():
            remediation=load(remediation_path);refs.append(str(remediation_path)+"#"+file_digest(remediation_path))
        if isinstance(remediation,dict) and remediation.get("changed") is True:
            regproc=subprocess.run([sys.executable,str(registry_tool),"effective",
                                    "--base",str(a.repo_root/"dev-hub/config/provider-adapters.v1.json"),
                                    "--state",str(adapter_state),"--output",str(effective_adapters),
                                    "--report",str(adapter_reconciliation)],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
            proc=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=90)
            if readiness_path.is_file():
                readiness=load(readiness_path);readiness["provider_adapter_registry"]=str(effective_adapters);save(readiness_path,readiness);refs.append(str(readiness_path)+"#"+file_digest(readiness_path))
                if readiness.get("status")=="READY":
                    chained_prior=dict(prior);chained_prior["evidence_refs"]=refs
                    return domain_scheduler_run_controller(a,project,chained_prior,df,readiness)

    provider_quota=provider_quota_condition_from_remediation(remediation)
    receipt=make_receipt("CONTINUE",project,
                         "AWAITING_EXTERNAL_CONDITION" if provider_quota is not None else "BLOCKED",
                         "RETRY_WHEN_PROVIDER_QUOTA_AVAILABLE" if provider_quota is not None else str(readiness.get("next_stage") or "DOMAIN_TOOLCHAIN_READINESS_FAILED"),
                         refs,{"domain_toolchain_readiness":readiness,
                               "domain_factories":df,
                               "governed_auto_remediation":remediation,
                               "continuation_mode":"DOMAIN_TOOLCHAIN_READINESS",
                               "provider_execution_started":False,
                               "adapter_invocation_started":False,
                               **(provider_quota or {})})
    receipt["continuation_of_request_id"]=prior.get("request_id")
    return receipt

def handle_continue(a)->dict[str,Any]:
    prior=load(a.prior_response)
    if prior.get("schema")!=HUMAN_RESPONSE_SCHEMA:
        return make_receipt("CONTINUE",a.project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",[],{"reason":"PRIOR_RESPONSE_SCHEMA_INVALID"})
    if a.expected_response_digest and file_digest(a.prior_response)!=a.expected_response_digest:
        return make_receipt("CONTINUE",a.project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",[],{"reason":"PRIOR_RESPONSE_DIGEST_MISMATCH"})
    if prior.get("brain_decision_obtained") is not True:
        return make_receipt("CONTINUE",a.project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",list(prior.get("evidence_refs") or []),{"reason":"NO_PRIOR_BRAIN_DECISION"})
    project=str(prior.get("project_id") or a.project or "chacha-dev-platform")
    brain=prior.get("brain_receipt") or {}
    brain_decision=(brain.get("decision") or {}) if isinstance(brain,dict) else {}
    prior_next=str(brain.get("next_action") or prior.get("next_action") or brain_decision.get("next_stage") or "")

    # Verified existing candidates continue their release lifecycle directly.
    # Never manufacture a new domain graph merely to publish/qualify an immutable candidate.
    if project=="chacha-dev-platform" and prior_next=="EXISTING_CANDIDATE_RELEASE":
        resume=brain_decision.get("existing_candidate_resume") if isinstance(brain_decision.get("existing_candidate_resume"),dict) else {}
        refs=list(prior.get("evidence_refs") or [])
        if resume.get("status")!="READY":
            return make_receipt("CONTINUE",project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",refs,
                                {"reason":"EXISTING_CANDIDATE_RESUME_RECEIPT_INVALID","existing_candidate_resume":resume})
        receipt=make_receipt("CONTINUE",project,"BLOCKED","CANDIDATE_PUBLICATION_REQUIRED",refs,{
          "existing_candidate_resume":resume,
          "continuation_mode":"EXISTING_CANDIDATE_RELEASE",
          "domain_factories_called":False,
          "synthetic_project_created":False,
          "required_transport":"GIT_REPOSITORY_PUBLICATION",
          "candidate_revision":resume.get("candidate_revision"),
          "candidate_tree":resume.get("candidate_tree"),
          "candidate_branch":resume.get("branch"),
          "guardian_preserved":True,
          "sentinel_preserved":True,
          "human_production_approval_preserved":True,
          "automatic_external_spend_eur":0
        })
        receipt["continuation_of_request_id"]=prior.get("request_id")
        return receipt

    # V8.0.18: DOMAIN_FACTORIES is an executable platform handoff, not a reason
    # to replay the whole central bootstrap. Materialize the already-approved
    # dynamic branch packages under their Guardian contracts and expose the
    # next real gate (provider health) with evidence.
    if project=="chacha-dev-platform" and prior_next=="DOMAIN_FACTORIES":
        bootstrap=Path(str(brain_decision.get("bootstrap_result") or brain.get("bootstrap_result") or ""))
        if not bootstrap.is_file():
            return make_receipt("CONTINUE",project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",
                                list(prior.get("evidence_refs") or []),{"reason":"DOMAIN_FACTORY_BOOTSTRAP_MISSING"})
        planning=bootstrap.parent
        runner=a.repo_root/"dev-hub/bin/domain-factory-runner.py"
        factory_dir=a.output_dir/"domain-factories"
        result_path=factory_dir/"domain-factory-result.json"
        proc=subprocess.run([sys.executable,str(runner),"--repo-root",str(a.repo_root),
                             "--planning-dir",str(planning),"--output-dir",str(factory_dir)],
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=90)
        if not result_path.is_file():
            return make_receipt("CONTINUE",project,"BLOCKED","DOMAIN_FACTORY_REPAIR_REQUIRED",
                                list(prior.get("evidence_refs") or []),
                                {"reason":"DOMAIN_FACTORY_RESULT_MISSING","stdout":proc.stdout[-1600:],"stderr":proc.stderr[-1600:]})
        result=load(result_path)
        refs=[str(result_path)+"#"+file_digest(result_path)]
        for key in ("contract_reconciliation","domain_execution_graph","provider_health_requirements"):
            p=Path(str(result.get(key) or ""))
            if p.is_file():refs.append(str(p)+"#"+file_digest(p))
        if result.get("status")!="READY":
            receipt=make_receipt("CONTINUE",project,"BLOCKED",str(result.get("next_stage") or "DOMAIN_FACTORY_REPAIR_REQUIRED"),refs,
                                 {"domain_factories":result,"continuation_mode":"DOMAIN_FACTORY_HANDOFF"})
        else:
            # V8.0.28: once Domain Factory has emitted the canonical Task Graph,
            # continue in the same central action until the first real fail-closed
            # provider gate, or through Scheduler -> Run Controller when all gates pass.
            chained_prior=dict(prior);chained_prior["evidence_refs"]=refs
            receipt=continue_domain_readiness(a,project,chained_prior,result)
            receipt.setdefault("decision",{})["domain_factories_completed"]=True
        receipt["continuation_of_request_id"]=prior.get("request_id")
        return receipt

    # V8.0.28: every fail-closed domain readiness gate is resumable without
    # replaying central bootstrap. Re-evaluate the same Task Graph against the
    # latest provider/adapter/health evidence; if READY, chain automatically
    # into Scheduler and Run Controller.
    if project=="chacha-dev-platform" and prior_next in {
        "PROVIDER_HEALTH_REQUIRED","PROVIDER_BINDING_REQUIRED","ADAPTER_ENABLEMENT_REQUIRED",
        "PROVIDER_PROBE_DEFINITION_REQUIRED","PROVIDER_HEALTH_PROBE_REQUIRED",
        "ENCAPSULATED_PROVIDER_EVIDENCE_REQUIRED","TASK_GRAPH_DECOMPOSITION_REQUIRED"
    }:
        df=brain_decision.get("domain_factories") if isinstance(brain_decision.get("domain_factories"),dict) else {}
        return continue_domain_readiness(a,project,prior,df)

    if project=="chacha-dev-platform" and prior_next=="DOMAIN_EXECUTION_VERIFICATION_REQUIRED":
        run_record=Path(str(brain_decision.get("run_record") or ""))
        plan_path=Path(str(brain_decision.get("execution_plan") or ""))
        bound_graph=plan_path.parent/"bound-domain-execution-graph.json" if plan_path.is_file() else Path("")
        execution_project=str(brain_decision.get("execution_project_id") or "")
        adapter_registry=Path(str(brain_decision.get("provider_adapter_registry") or ""))
        if not run_record.is_file() or not bound_graph.is_file() or not execution_project or not adapter_registry.is_file():
            return make_receipt("CONTINUE",project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",list(prior.get("evidence_refs") or []),
                                {"reason":"DOMAIN_EXECUTION_VERIFICATION_CONTEXT_MISSING"})
        record=load(run_record);verification=verify_domain_run_results(a,execution_project,record,bound_graph,adapter_registry)
        refs=list(prior.get("evidence_refs") or []);refs.extend(verification.get("evidence_refs") or [])
        receipt=make_receipt("CONTINUE",project,"COMPLETE" if verification.get("status")=="PASS" else "BLOCKED",
                             "AWAIT_NEW_INSTRUCTION" if verification.get("status")=="PASS" else "DOMAIN_EXECUTION_VERIFICATION_REQUIRED",refs,{
                               "run_record":str(run_record),"execution_plan":str(plan_path),"execution_project_id":execution_project,
                               "provider_adapter_registry":str(adapter_registry),
                               "independent_verification":verification,"domain_execution_verified":verification.get("status")=="PASS",
                               "continuation_mode":"DOMAIN_EXECUTION_VERIFICATION_RESUME"})
        receipt["continuation_of_request_id"]=prior.get("request_id")
        return receipt

    if project=="chacha-dev-platform" and prior_next in {"SCHEDULER_READY","RUN_CONTROLLER_COMPLETE"}:
        df=brain_decision.get("domain_factories") if isinstance(brain_decision.get("domain_factories"),dict) else {}
        readiness=brain_decision.get("domain_toolchain_readiness") if isinstance(brain_decision.get("domain_toolchain_readiness"),dict) else {}
        if readiness.get("status")!="READY":
            return continue_domain_readiness(a,project,prior,df)
        return domain_scheduler_run_controller(a,project,prior,df,readiness)

    # First ask canonical Project Control. If it has a real initialized lifecycle and
    # says READY, CONTINUE performs the transactional advance under central authority.
    if project!="chacha-dev-platform":
        rc,status,stdout,stderr=project_control(a.repo_root,a.project_control,project,"status")
        if isinstance(status,dict) and status.get("schema")==PROJECT_CONTROL_SCHEMA:
            state=str(status.get("status") or "UNKNOWN")
            if state=="READY":
                target=str(((status.get("details") or {}).get("next_stage") or ""))
                extra=["--actor","human-via-interface-gateway"]
                if target:extra+=["--target",target]
                rc2,advanced,out2,err2=project_control(a.repo_root,a.project_control,project,"advance",*extra)
                if isinstance(advanced,dict) and advanced.get("schema")==PROJECT_CONTROL_SCHEMA:
                    refs=[]
                    for art in advanced.get("artifacts") or []:
                        p=Path(str(art.get("path") or ""))
                        if p.is_file():refs.append(str(p)+"#"+file_digest(p))
                    nxt=(advanced.get("next_actions") or ["REQUEST_STATUS"])[0]
                    receipt=make_receipt("CONTINUE",project,"CONTINUED" if rc2==0 else str(advanced.get("status") or "BLOCKED"),str(nxt),refs,
                                         {"project_control_before":status,"project_control_after":advanced,"continuation_mode":"TRANSACTIONAL_ADVANCE"})
                    receipt["continuation_of_request_id"]=prior.get("request_id")
                    return receipt
            if state not in {"UNKNOWN"}:
                nxt=(status.get("next_actions") or ["AWAIT_NEW_INSTRUCTION"])[0]
                receipt=make_receipt("CONTINUE",project,str(status.get("status") or "BLOCKED"),str(nxt),[],{"project_control":status,"continuation_mode":"CONTROL_PLANE_STATUS"})
                receipt["continuation_of_request_id"]=prior.get("request_id")
                return receipt
    # No initialized lifecycle: make a fresh central-brain call from the exact original
    # central intent. This is a real continuation/revalidation, never an interface copy.
    central_intent=Path(str(brain_decision.get("central_intent") or brain.get("central_intent") or ""))
    if not central_intent.is_file():
        bootstrap=Path(str(brain_decision.get("bootstrap_result") or brain.get("bootstrap_result") or ""))
        if bootstrap.is_file():
            candidate=bootstrap.parent.parent/"central-intent.json"
            if candidate.is_file():central_intent=candidate
    if not central_intent.is_file():
        return make_receipt("CONTINUE",project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",list(prior.get("evidence_refs") or []),{"reason":"ORIGINAL_CENTRAL_INTENT_MISSING"})
    ci=load(central_intent)
    human_intent={
      "schema":HUMAN_INTENT_SCHEMA,
      "request_id":"cont-"+uuid.uuid4().hex,
      "received_at":now_iso(),
      "source":"central-interface-controller-continuation",
      "route":"CHACHA_DEV","command":"CONTINUE",
      "user_text":str(ci.get("text") or ""),
      "domains":list(ci.get("domains") or []),
      "project_id":project,
      "target_scope":ci.get("target_scope") or "PLATFORM",
      "interface_decision_authority":False,
      "title":ci.get("name")
    }
    r=orchestrate(a.repo_root,a.orchestrator,human_intent,a.output_dir,continuation_of=str(prior.get("request_id") or "UNKNOWN"))
    r["continuation_of_request_id"]=prior.get("request_id")
    r.setdefault("decision",{})["continuation_mode"]="FRESH_CENTRAL_REORCHESTRATION"
    return r

def main()->int:
    ap=argparse.ArgumentParser(description="ChaCha DEV central controller for the human interface")
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"))
    ap.add_argument("--orchestrator",type=Path)
    ap.add_argument("--project-control",type=Path)
    sub=ap.add_subparsers(dest="command",required=True)
    st=sub.add_parser("status");st.add_argument("--project",default="chacha-dev-platform")
    ins=sub.add_parser("instruction");ins.add_argument("--intent",type=Path,required=True);ins.add_argument("--output-dir",type=Path,required=True)
    co=sub.add_parser("continue");co.add_argument("--project",default="chacha-dev-platform");co.add_argument("--prior-response",type=Path,required=True)
    co.add_argument("--expected-response-digest");co.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    a.repo_root=a.repo_root.resolve();a.runtime_root=a.runtime_root.resolve()
    a.orchestrator=(a.orchestrator or a.repo_root/"dev-hub/bin/autonomous-project-orchestrator.py").resolve()
    a.project_control=(a.project_control or a.repo_root/"dev-hub/bin/project-control.py").resolve()
    if a.command=="status":result=handle_status(a)
    elif a.command=="instruction":result=handle_instruction(a)
    else:result=handle_continue(a)
    result["platform_revision"]=runtime_revision(a.repo_root)
    result["platform_version"]=runtime_version(a.repo_root)
    save(a.output,result)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result["status"] not in {"BRAIN_UNAVAILABLE","BRAIN_RECEIPT_INVALID"} else 2

if __name__=="__main__":
    raise SystemExit(main())
