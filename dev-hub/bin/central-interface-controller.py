#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, re, subprocess, sys, time, uuid
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

def orchestrate(repo_root:Path,orchestrator:Path,human_intent:dict[str,Any],out_dir:Path,continuation_of:str|None=None)->dict[str,Any]:
    request_id=str(human_intent.get("request_id") or uuid.uuid4().hex)
    central={
      "name":str(human_intent.get("title") or ("Human Interface Request "+request_id[:12])),
      "text":str(human_intent.get("user_text") or ""),
      "source":"central-interface-controller",
      "request_id":request_id,
      "target_scope":human_intent.get("target_scope") or "PLATFORM",
      "requested_project_id":human_intent.get("project_id") or "chacha-dev-platform",
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
        return make_receipt("CONTINUE" if continuation_of else "INSTRUCTION",
                            str(human_intent.get("project_id") or "chacha-dev-platform"),
                            "BRAIN_UNAVAILABLE","RETRY_WHEN_BRAIN_AVAILABLE",[],
                            {"stdout":p.stdout[-1200:],"stderr":p.stderr[-1200:]})
    b=load(bootstrap)
    if b.get("schema")!=BOOTSTRAP_SCHEMA or not b.get("project_id"):
        return make_receipt("CONTINUE" if continuation_of else "INSTRUCTION",
                            str(human_intent.get("project_id") or "chacha-dev-platform"),
                            "BRAIN_RECEIPT_INVALID","RETRY_AFTER_RECEIPT_REPAIR",[str(bootstrap)],
                            {"bootstrap":b})
    refs=[str(bootstrap)+"#"+file_digest(bootstrap)]
    council=Path(str(b.get("architecture_decision_council") or ""))
    if council.is_file():refs.append(str(council)+"#"+file_digest(council))
    allowed=b.get("architecture_decision_allowed") is True and b.get("domain_dispatch_allowed") is True
    status=("CONTINUED_PLAN_READY" if continuation_of else "PLAN_READY") if allowed else "BLOCKED"
    nxt=str(b.get("next_stage") or ("AWAIT_REPLAN" if not allowed else "AWAIT_CENTRAL_CONTINUATION"))
    decision={
      "schema":b.get("schema"),"version":b.get("version"),"project_id":b.get("project_id"),
      "architecture_decision_allowed":b.get("architecture_decision_allowed"),
      "domain_dispatch_allowed":b.get("domain_dispatch_allowed"),
      "runtime_schedulable":b.get("runtime_schedulable"),
      "central_compromise_found":b.get("central_compromise_found"),
      "next_stage":b.get("next_stage"),"external_spend_eur":b.get("external_spend_eur"),
      "bootstrap_result":str(bootstrap),"central_intent":str(central_path)
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
    return orchestrate(a.repo_root,a.orchestrator,hi,a.output_dir)

def handle_continue(a)->dict[str,Any]:
    prior=load(a.prior_response)
    if prior.get("schema")!=HUMAN_RESPONSE_SCHEMA:
        return make_receipt("CONTINUE",a.project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",[],{"reason":"PRIOR_RESPONSE_SCHEMA_INVALID"})
    if a.expected_response_digest and file_digest(a.prior_response)!=a.expected_response_digest:
        return make_receipt("CONTINUE",a.project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",[],{"reason":"PRIOR_RESPONSE_DIGEST_MISMATCH"})
    if prior.get("brain_decision_obtained") is not True:
        return make_receipt("CONTINUE",a.project,"BRAIN_RECEIPT_INVALID","AWAIT_NEW_INSTRUCTION",list(prior.get("evidence_refs") or []),{"reason":"NO_PRIOR_BRAIN_DECISION"})
    project=str(prior.get("project_id") or a.project or "chacha-dev-platform")
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
    brain=prior.get("brain_receipt") or {}
    central_intent=Path(str(brain.get("central_intent") or ""))
    if not central_intent.is_file():
        bootstrap=Path(str(brain.get("bootstrap_result") or ""))
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
