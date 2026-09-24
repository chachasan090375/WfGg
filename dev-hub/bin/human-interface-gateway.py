#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

INTENT_SCHEMA="chacha.dev/human-interface-intent/v1"
RESPONSE_SCHEMA="chacha.dev/human-interface-response/v1"
BOOTSTRAP_SCHEMA="chacha.dev/autonomous-project-bootstrap/v1"

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def load(path:Path,default=None):
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:return default
        raise
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def atomic_write(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def canonical(value:Any)->bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")

def digest(value:Any)->str:
    return "sha256:"+hashlib.sha256(canonical(value)).hexdigest()

def file_digest(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def safe_id(value:str)->str:
    s=re.sub(r"[^A-Za-z0-9._-]+","-",value).strip("-")
    return s[:120] or uuid.uuid4().hex

def normalize_command(text:str)->str:
    t=text.strip().casefold()
    t=re.sub(r"[\s!?.,;:]+$","",t)
    return {"allo":"STATUS","go":"CONTINUE","stop":"STOP"}.get(t,"INSTRUCTION")

def runtime_revision(repo_root:Path)->str:
    p=repo_root/".revision"
    try:return p.read_text(encoding="utf-8").strip()
    except Exception:return "UNKNOWN"

def runtime_version(repo_root:Path)->str:
    p=repo_root/"dev-hub/bin/autonomous-project-orchestrator.py"
    try:s=p.read_text(encoding="utf-8")
    except Exception:return "UNKNOWN"
    m=re.search(r'"version"\s*:\s*"([^"]+)"',s)
    return m.group(1) if m else "UNKNOWN"

def run_json(cmd:list[str],timeout:int=180)->tuple[int,dict[str,Any]|None,str,str]:
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
    parsed=None
    if p.stdout.strip():
        # Project Control emits one JSON object in --json mode.
        try:parsed=json.loads(p.stdout)
        except Exception:
            # Emergency controller prints JSON to stdout; tolerate leading/trailing text only if one object spans all.
            try:
                start=p.stdout.index("{");end=p.stdout.rindex("}")+1
                parsed=json.loads(p.stdout[start:end])
            except Exception:parsed=None
    return p.returncode,parsed,p.stdout,p.stderr

def append_journal(path:Path,intent:dict[str,Any],response:dict[str,Any])->dict[str,Any]:
    path.parent.mkdir(parents=True,exist_ok=True)
    lock=path.with_suffix(path.suffix+".lock")
    with lock.open("a+") as lf:
        fcntl.flock(lf.fileno(),fcntl.LOCK_EX)
        seq=1;prev="GENESIS"
        if path.is_file():
            lines=[x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
            if lines:
                last=json.loads(lines[-1]);seq=int(last.get("seq") or 0)+1;prev=str(last.get("event_digest") or "")
        event={
          "schema":"chacha.dev/human-interface-audit-event/v1",
          "seq":seq,"recorded_at":now_iso(),"previous_event_digest":prev,
          "request_id":intent["request_id"],"intent_digest":digest(intent),"response_digest":digest(response),
          "command":intent["command"],"route":intent["route"],"authority":response.get("authority")
        }
        event["event_digest"]=digest({k:v for k,v in event.items() if k!="event_digest"})
        with path.open("a",encoding="utf-8") as out:
            out.write(json.dumps(event,separators=(",",":"),ensure_ascii=False)+"\n")
            out.flush();os.fsync(out.fileno())
        return event

def validate_journal(path:Path)->bool:
    if not path.is_file():return True
    prev="GENESIS";seq=1
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        x=json.loads(line)
        if int(x.get("seq") or -1)!=seq:return False
        if str(x.get("previous_event_digest") or "")!=prev:return False
        actual=digest({k:v for k,v in x.items() if k!="event_digest"})
        if actual!=x.get("event_digest"):return False
        prev=actual;seq+=1
    return True

def platform_status(repo_root:Path,runtime_root:Path)->dict[str,Any]:
    out={
      "platform_revision":runtime_revision(repo_root),
      "platform_version":runtime_version(repo_root),
      "emergency_stop_active":False,
      "guardian_all_hooks_active":None,
      "agent_count":None,
      "evidence_labels":{},
      "hygiene":None
    }
    try:out["emergency_stop_active"]=bool(load(runtime_root/"control/emergency-stop.json",{}).get("active"))
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
        out["hygiene"]={
          "platform_revision":h.get("platform_revision"),
          "platform_version":h.get("platform_version"),
          "threshold_reasons":h.get("threshold_reasons"),
          "metrics":h.get("metrics")
        }
    except Exception:pass
    return out

def response_base(intent:dict[str,Any],status:str,authority:str,next_action:str,evidence_refs:list[str])->dict[str,Any]:
    return {
      "schema":RESPONSE_SCHEMA,
      "request_id":intent["request_id"],
      "responded_at":now_iso(),
      "route":intent["route"],
      "command":intent["command"],
      "project_id":intent.get("project_id"),
      "status":status,
      "authority":authority,
      "brain_decision_obtained":authority in {"central-orchestrator","central-orchestrator-prior-receipt"},
      "next_action":next_action,
      "evidence_refs":evidence_refs,
      "interface_direct_technical_decision":False,
      "interface_direct_mutation":False,
      "automatic_external_spend_eur":0
    }

def handle_status(intent,repo_root,runtime_root,project_control)->dict[str,Any]:
    project=str(intent.get("project_id") or "chacha-dev-platform")
    refs=[]
    if project!="chacha-dev-platform":
        cmd=[sys.executable,str(project_control),"--repo-root",str(repo_root),"--json","status","--project",project]
        try:
            rc,payload,stdout,stderr=run_json(cmd,60)
        except Exception as exc:
            rc,payload,stderr=2,None,str(exc)
        if payload is not None:
            r=response_base(intent,"OK" if rc==0 else "BLOCKED","central-orchestrator","AWAIT_USER_DIRECTIVE",refs)
            r["brain_receipt"]=payload
            r["status_source"]="project-control"
            return r
    status=platform_status(repo_root,runtime_root)
    r=response_base(intent,"OK","central-orchestrator","AWAIT_USER_DIRECTIVE",refs)
    r["brain_receipt"]={"schema":"chacha.dev/platform-status-receipt/v1","status":status}
    r["status_source"]="canonical-platform-runtime"
    return r

def handle_continue(intent,session)->dict[str,Any]:
    prior_path=Path(str(session.get("last_response_path") or ""))
    if not prior_path.is_file():
        return response_base(intent,"BLOCKED","central-orchestrator-prior-receipt","AWAIT_NEW_INSTRUCTION",[])
    prior=load(prior_path)
    refs=list(prior.get("evidence_refs") or [])
    if prior.get("brain_decision_obtained") is not True or not refs:
        return response_base(intent,"BRAIN_RECEIPT_INVALID","central-orchestrator-prior-receipt","AWAIT_NEW_INSTRUCTION",refs)
    nxt=str(prior.get("next_action") or "AWAIT_NEW_INSTRUCTION")
    r=response_base(intent,"CONTINUE_ALLOWED","central-orchestrator-prior-receipt",nxt,refs)
    r["continuation_of_request_id"]=prior.get("request_id")
    r["brain_receipt"]=prior.get("brain_receipt")
    r["new_technical_decision_created"]=False
    return r

def handle_stop(intent,emergency_controller,emergency_state)->dict[str,Any]:
    cmd=[sys.executable,str(emergency_controller),"--state",str(emergency_state),"activate",
         "--reason","human-interface-request:"+intent["request_id"],"--actor","human-via-interface-gateway"]
    try:
        rc,payload,stdout,stderr=run_json(cmd,60)
    except Exception as exc:
        rc,payload,stderr=2,None,str(exc)
    if rc!=0 or not isinstance(payload,dict) or payload.get("active") is not True:
        r=response_base(intent,"BRAIN_UNAVAILABLE","emergency-stop-controller","STOP_RETRY_OR_MANUAL_CONTROL",[])
        r["controller_error"]=stderr[-1000:]
        return r
    r=response_base(intent,"STOP_ACTIVE","emergency-stop-controller","AWAIT_EXPLICIT_RESET_AND_HEALTH_CHECK",[])
    r["brain_receipt"]=payload
    r["brain_decision_obtained"]=True
    return r

def handle_instruction(intent,repo_root,runtime_root,orchestrator,runs_root)->dict[str,Any]:
    request_id=intent["request_id"];run_dir=runs_root/safe_id(request_id);planning=run_dir/"planning"
    run_dir.mkdir(parents=True,exist_ok=True);planning.mkdir(parents=True,exist_ok=True)
    central_intent={
      "name":str(intent.get("title") or ("Human Interface Request "+request_id[:12])),
      "text":intent["user_text"],
      "source":"human-interface-gateway",
      "request_id":request_id,
      "target_scope":intent.get("target_scope") or "PLATFORM",
      "requested_project_id":intent.get("project_id") or "chacha-dev-platform",
      "constraints":{
        "automatic_external_spend_eur":0,
        "interface_has_no_technical_decision_authority":True,
        "central_orchestrator_required":True
      }
    }
    intent_path=run_dir/"central-intent.json";atomic_write(intent_path,central_intent)
    cmd=[sys.executable,str(orchestrator),"--repo-root",str(repo_root),"--intent",str(intent_path),"--output-dir",str(planning)]
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=300)
    except Exception as exc:
        r=response_base(intent,"BRAIN_UNAVAILABLE","central-orchestrator","RETRY_WHEN_BRAIN_AVAILABLE",[])
        r["brain_error"]=str(exc);return r
    bootstrap=planning/"bootstrap-result.json"
    if p.returncode!=0 or not bootstrap.is_file():
        r=response_base(intent,"BRAIN_UNAVAILABLE","central-orchestrator","RETRY_WHEN_BRAIN_AVAILABLE",[])
        r["brain_stdout"]=p.stdout[-1500:];r["brain_stderr"]=p.stderr[-1500:];return r
    b=load(bootstrap)
    if b.get("schema")!=BOOTSTRAP_SCHEMA or not b.get("project_id"):
        r=response_base(intent,"BRAIN_RECEIPT_INVALID","central-orchestrator","RETRY_AFTER_RECEIPT_REPAIR",[str(bootstrap)])
        r["brain_receipt"]=b;return r
    refs=[str(bootstrap)+"#"+file_digest(bootstrap)]
    council=Path(str(b.get("architecture_decision_council") or ""))
    if council.is_file():refs.append(str(council)+"#"+file_digest(council))
    allowed=b.get("architecture_decision_allowed") is True and b.get("domain_dispatch_allowed") is True
    status="PLAN_READY" if allowed else "BLOCKED"
    next_action=str(b.get("next_stage") or ("AWAIT_REPLAN" if not allowed else "AWAIT_INTERFACE_EXECUTION"))
    r=response_base(intent,status,"central-orchestrator",next_action,refs)
    r["project_id"]=b["project_id"]
    r["brain_receipt"]={
      "schema":b.get("schema"),"version":b.get("version"),"project_id":b.get("project_id"),
      "architecture_decision_allowed":b.get("architecture_decision_allowed"),
      "domain_dispatch_allowed":b.get("domain_dispatch_allowed"),
      "runtime_schedulable":b.get("runtime_schedulable"),
      "central_compromise_found":b.get("central_compromise_found"),
      "next_stage":b.get("next_stage"),
      "external_spend_eur":b.get("external_spend_eur"),
      "bootstrap_result":str(bootstrap)
    }
    return r

def main()->int:
    ap=argparse.ArgumentParser(description="ChaCha DEV V7.2 Human Interface Gateway")
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"))
    ap.add_argument("--policy",type=Path)
    ap.add_argument("--text",required=True)
    ap.add_argument("--command",choices=["STATUS","CONTINUE","STOP","INSTRUCTION"])
    ap.add_argument("--route",choices=["CHACHA_DEV","GENERAL"],default="CHACHA_DEV")
    ap.add_argument("--project")
    ap.add_argument("--target-scope",default="PLATFORM")
    ap.add_argument("--request-id")
    ap.add_argument("--output",type=Path)
    ap.add_argument("--orchestrator",type=Path)
    ap.add_argument("--project-control",type=Path)
    ap.add_argument("--emergency-controller",type=Path)
    ap.add_argument("--emergency-state",type=Path)
    args=ap.parse_args()

    repo_root=args.repo_root.resolve();runtime_root=args.runtime_root.resolve()
    policy_path=args.policy or repo_root/"dev-hub/config/human-interface-gateway.v1.json"
    policy=load(policy_path)
    if policy.get("schema")!="chacha.dev/human-interface-gateway-policy/v1":
        raise SystemExit("HUMAN_INTERFACE_POLICY_SCHEMA_INVALID")
    rr=Path(str(policy.get("runtime_root") or runtime_root/"human-interface"))
    # Tests/custom runtimes may override the policy's production root.
    if runtime_root!=Path("/opt/chacha-dev/runtime").resolve():rr=runtime_root/"human-interface"
    session_path=rr/"session.json";journal_path=rr/"audit.jsonl";runs_root=rr/"runs"
    rr.mkdir(parents=True,exist_ok=True);runs_root.mkdir(parents=True,exist_ok=True)
    if not validate_journal(journal_path):raise SystemExit("HUMAN_INTERFACE_AUDIT_CHAIN_INVALID")
    session=load(session_path,{"schema":"chacha.dev/human-interface-session/v1","active_project":policy.get("default_project")})
    command=args.command or normalize_command(args.text)
    request_id=args.request_id or ("hir-"+uuid.uuid4().hex)
    project=args.project or session.get("active_project") or policy.get("default_project")
    intent={
      "schema":INTENT_SCHEMA,"request_id":request_id,"received_at":now_iso(),
      "source":"chatgpt-human-interface-adapter","route":args.route,"command":command,
      "user_text":args.text,"project_id":project,"target_scope":args.target_scope,
      "interface_decision_authority":False
    }

    if args.route=="GENERAL":
        response=response_base(intent,"DIRECT_ALLOWED","chat-interface","ANSWER_GENERAL_REQUEST_DIRECTLY",[])
        response["brain_decision_obtained"]=False
    else:
        orchestrator=args.orchestrator or repo_root/"dev-hub/bin/autonomous-project-orchestrator.py"
        project_control=args.project_control or repo_root/"dev-hub/bin/project-control.py"
        emergency_controller=args.emergency_controller or repo_root/"dev-hub/bin/emergency-stop-controller.py"
        emergency_state=args.emergency_state or runtime_root/"control/emergency-stop.json"
        if command=="STATUS":
            response=handle_status(intent,repo_root,runtime_root,project_control)
        elif command=="CONTINUE":
            response=handle_continue(intent,session)
        elif command=="STOP":
            response=handle_stop(intent,emergency_controller,emergency_state)
        else:
            response=handle_instruction(intent,repo_root,runtime_root,orchestrator,runs_root)

    response["platform_revision"]=runtime_revision(repo_root)
    response["platform_version"]=runtime_version(repo_root)
    response["intent_digest"]=digest(intent)
    response["response_digest"]=digest({k:v for k,v in response.items() if k!="response_digest"})
    out=args.output or rr/"responses"/(safe_id(request_id)+".json")
    atomic_write(out,response)
    journal=append_journal(journal_path,intent,response)
    session.update({
      "schema":"chacha.dev/human-interface-session/v1","updated_at":now_iso(),
      "active_project":response.get("project_id") or project,
      "last_request_id":request_id,"last_command":command,
      "last_response_path":str(out),"last_response_digest":file_digest(out),
      "last_journal_event_digest":journal["event_digest"]
    })
    atomic_write(session_path,session)
    print(json.dumps(response,indent=2,ensure_ascii=False))
    return 0 if response["status"] not in {"BRAIN_UNAVAILABLE","BRAIN_RECEIPT_INVALID"} else 2

if __name__=="__main__":
    raise SystemExit(main())
