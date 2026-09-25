#!/usr/bin/env python3
from __future__ import annotations

import argparse,hashlib,json,mimetypes,os,re,subprocess,sys,threading,time,uuid
from email.header import decode_header
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs,urlparse
from progress_state_controller import ProgressStore

HUMAN_RESPONSE_SCHEMA="chacha.dev/human-interface-response/v1"
CENTRAL_RECEIPT_SCHEMA="chacha.dev/central-interface-receipt/v1"
POLICY_SCHEMA="chacha.dev/direct-operator-policy/v1"
PROFILE_SCHEMA="chacha.dev/human-conversation-profile/v1"
TIMELINE_SCHEMA="chacha.dev/conversation-timeline/v1"
TURN_SCHEMA="chacha.dev/conversation-turn/v1"
PROFILE_ALLOWED_FIELDS={
  "preferred_name","preferred_form_of_address","gender_identity","age_band","languages",
  "cultural_contexts","regional_contexts","conversation_register","directness","verbosity",
  "humor_level","voice_preferences","assistant_persona_id"
}

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def load(p:Path,default=None):
    try:x=json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:return default
        raise
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def atomic(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(tmp,p)
def fd(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def safe_id(v:str)->str:
    x=re.sub(r"[^A-Za-z0-9._-]+","-",v).strip("-")
    return x[:120] or uuid.uuid4().hex
def normalize(text:str)->str:
    t=re.sub(r"[\s!?.,;:]+$","",text.strip().casefold())
    return {"allo":"STATUS","go":"CONTINUE","stop":"STOP"}.get(t,"INSTRUCTION")

def transient_project(value:Any)->bool:
    v=str(value or "")
    return v.startswith("human-interface-request-") or v.startswith("dor-")

def stable_project(value:Any,default_project:str="chacha-dev-platform")->str:
    v=str(value or "").strip()
    return default_project if not v or transient_project(v) else v

def should_auto_continue(receipt:dict[str,Any])->bool:
    status=str(receipt.get("status") or "").upper()
    next_action=str(receipt.get("next_action") or "").upper()
    non_terminal=(status in {"PLAN_READY","CONTINUED","READY"} or status.startswith("CONTINUED_") or status.endswith("_PLAN_READY"))
    if not non_terminal: return False
    if next_action.startswith("AWAIT_") or "APPROVAL" in next_action: return False
    return True
def decode_identity(v:str)->str:
    try:
        out=[]
        for part,enc in decode_header(v):
            if isinstance(part,bytes):out.append(part.decode(enc or "utf-8","replace"))
            else:out.append(part)
        return "".join(out)
    except Exception:return v
def authorized_users(path:Path)->set[str]:
    x=load(path,{"authorized_logins":[]})
    return {str(v).strip().casefold() for v in x.get("authorized_logins") or [] if str(v).strip()}
def operator_from_headers(headers:Any,policy:dict[str,Any])->str|None:
    auth=policy.get("authentication") or {};name=str(auth.get("login_header") or "Tailscale-User-Login")
    raw=str(headers.get(name) or "").strip()
    if not raw:return None
    login=decode_identity(raw).strip().casefold()
    users=authorized_users(Path(str(auth.get("authorized_users_file") or "")))
    return login if users and login in users else None
def run(cmd:list[str],timeout:int=3700)->subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
def wrap(intent:dict[str,Any],receipt:dict[str,Any])->dict[str,Any]:
    status=str(receipt.get("status") or "BRAIN_RECEIPT_INVALID")
    return {
      "schema":HUMAN_RESPONSE_SCHEMA,"request_id":intent["request_id"],"responded_at":now_iso(),
      "route":"CHACHA_DEV","command":intent["command"],
      "project_id":intent.get("project_id"),
      "execution_project_id":receipt.get("project_id") or intent.get("project_id"),
      "status":status,"authority":"central-orchestrator",
      "brain_decision_obtained":receipt.get("brain_decision_obtained") is True and status not in {"BRAIN_UNAVAILABLE","BRAIN_RECEIPT_INVALID"},
      "next_action":receipt.get("next_action") or "AWAIT_USER_DIRECTIVE",
      "evidence_refs":receipt.get("evidence_refs") or [],
      "brain_receipt":receipt,
      "interface_direct_technical_decision":False,"interface_direct_mutation":False,
      "automatic_external_spend_eur":0
    }

class State:
    def __init__(self,repo:Path,runtime:Path,policy:dict[str,Any]):
        self.repo=repo;self.runtime=runtime;self.policy=policy
        self.root=Path(str(policy.get("runtime_root") or runtime/"direct-operator"))
        self.root.mkdir(parents=True,exist_ok=True)
        self.jobs=self.root/"jobs";self.jobs.mkdir(parents=True,exist_ok=True)
        self.responses=self.root/"responses";self.responses.mkdir(parents=True,exist_ok=True)
        self.conversations=self.root/"conversations";self.conversations.mkdir(parents=True,exist_ok=True)
        self.human_profiles=self.root/"human-profiles";self.human_profiles.mkdir(parents=True,exist_ok=True)
        for private_dir in (self.conversations,self.human_profiles):
            try:os.chmod(private_dir,0o700)
            except Exception:pass
        self.idempotency=self.root/"idempotency";self.idempotency.mkdir(parents=True,exist_ok=True)
        self.session_path=self.root/"session.json";self.lock=threading.RLock()
        ui=Path(str(policy.get("ui_root") or "dev-hub/direct-operator-ui"))
        self.ui_root=ui if ui.is_absolute() else repo/ui
        self.live_ui_root=Path(str(policy.get("live_ui_root") or "/opt/chacha-dev/runtime/live-ui/current/ui"))
        self.live_app_config=Path(str(policy.get("live_app_config") or "/opt/chacha-dev/runtime/live-ui/current/app-config.json"))
        self.controller=repo/str(policy.get("central_controller") or "dev-hub/bin/central-interface-controller.py")
        self.translator=repo/str(((policy.get("translator") or {}).get("script")) or "dev-hub/bin/functional-translator-agent.py")
        self.conversation=repo/str(((policy.get("conversation") or {}).get("script")) or "dev-hub/bin/conversation-interface-agent.py")
        self.human_context=repo/str(((policy.get("human_conversation") or {}).get("context_engine")) or "dev-hub/bin/human-context-engine.py")
        dialogue_cfg=policy.get("dialogue_orchestrator") if isinstance(policy.get("dialogue_orchestrator"),dict) else {}
        self.dialogue_orchestrator=repo/str(dialogue_cfg.get("script") or "dev-hub/bin/dialogue-orchestrator.py")
        self.dialogue_policy=repo/str(dialogue_cfg.get("policy") or "dev-hub/config/dialogue-orchestrator.v1.json")
        self.dialogue_attestation=Path(str(dialogue_cfg.get("zero_cost_attestation") or "/opt/chacha-dev/runtime/provider-economics/agy-conversation-zero-cost.json"))
        hbc_cfg=policy.get("human_behavior_center") if isinstance(policy.get("human_behavior_center"),dict) else {}
        self.persona_dir=Path(str(hbc_cfg.get("persona_dir") or "/opt/chacha-dev/runtime/knowledge/human-behavior/personas"))
        self.emergency=repo/str(policy.get("emergency_controller") or "dev-hub/bin/emergency-stop-controller.py")
        progress_policy=repo/str(policy.get("progress_policy") or "dev-hub/config/progress-reporting.v1.json")
        self.progress=ProgressStore(load(progress_policy))
        live_shell_path=repo/str(policy.get("android_live_shell_config") or "dev-hub/config/android-live-shell.v1.json")
        self.live_shell_config=load(live_shell_path)
        native_policy_path=repo/str(policy.get("android_native_update_policy") or "dev-hub/config/android-native-update.v1.json")
        self.native_update_policy=load(native_policy_path)
        self.native_update_manifest=Path(str(policy.get("native_update_manifest") or "/opt/chacha-dev/runtime/native-update/current/manifest.json"))
        self.native_update_packages_root=Path(str(policy.get("native_update_packages_root") or "/opt/chacha-dev/runtime/native-update/current/packages"))
    def effective_ui_root(self):
        live=self.live_ui_root
        if (live/"index.html").is_file():return live
        return self.ui_root
    def effective_live_shell_config(self):
        x=None
        try:
            candidate=load(self.live_app_config)
            if candidate.get("schema")=="chacha.dev/android-live-shell-config/v1":x=candidate
        except Exception:pass
        if x is None:x=dict(self.live_shell_config)
        else:x=dict(x)
        try:x["runtime_revision"]=(self.repo/".revision").read_text(encoding="utf-8").strip()
        except Exception:x["runtime_revision"]="unknown"
        return x

    def effective_native_update_manifest(self):
        try:
            x=load(self.native_update_manifest)
            if x.get("schema")=="chacha.dev/android-native-update/v1" and x.get("package_id")==self.native_update_policy.get("app_id"):
                return x
        except Exception:pass
        return {"schema":"chacha.dev/android-native-update/v1","status":"NONE",
                "package_id":self.native_update_policy.get("app_id"),
                "automatic_external_spend_eur":0}

    def session(self)->dict[str,Any]:
        return load(self.session_path,{"schema":"chacha.dev/direct-operator-session/v1",
          "active_project":self.policy.get("default_project") or "chacha-dev-platform"})
    def session_view(self)->dict[str,Any]:
        s=self.session()
        out={"status":"OK","active_project":s.get("active_project"),"last_command":s.get("last_command"),
             "last_request_id":s.get("last_request_id")}
        last_path=str(s.get("last_response_path") or "")
        if last_path:
            try:
                p=Path(last_path).resolve()
                responses_root=self.responses.resolve()
                if str(p).startswith(str(responses_root)+os.sep) and p.is_file():
                    last=load(p)
                    expected=str(s.get("last_response_digest") or "")
                    actual=fd(p)
                    if not expected or expected==actual:
                        out["last_response"]=last
                        out["last_response_digest"]=actual
            except Exception:
                pass
        return out
    def save_session(self,x:dict[str,Any])->None:atomic(self.session_path,x)

    def operator_key(self,operator:str)->str:
        return hashlib.sha256(str(operator).strip().casefold().encode("utf-8")).hexdigest()[:32]

    def profile_path(self,operator:str)->Path:
        return self.human_profiles/(self.operator_key(operator)+".json")

    def profile_view(self,operator:str)->dict[str,Any]:
        x=load(self.profile_path(operator),{"schema":PROFILE_SCHEMA,"explicit_opt_in":True})
        return {k:v for k,v in x.items() if k=="schema" or k=="explicit_opt_in" or k in PROFILE_ALLOWED_FIELDS}

    def save_profile(self,operator:str,raw:dict[str,Any])->dict[str,Any]:
        out={"schema":PROFILE_SCHEMA,"explicit_opt_in":True,"updated_at":now_iso()}
        for k in PROFILE_ALLOWED_FIELDS:
            if k not in raw:continue
            v=raw[k]
            if isinstance(v,str):
                v=v.strip()[:300]
                if v:out[k]=v
            elif isinstance(v,list):
                vals=[str(x).strip()[:120] for x in v if str(x).strip()]
                if vals:out[k]=vals[:20]
            elif isinstance(v,dict) and k=="voice_preferences":
                safe={}
                for kk,vv in v.items():
                    if str(kk) in {"enabled","language","voice_style","speech_rate","pitch","auto_speak"}:safe[str(kk)]=vv
                if safe:out[k]=safe
        path=self.profile_path(operator);atomic(path,out)
        try:os.chmod(path,0o600)
        except Exception:pass
        return out

    def timeline_path(self,operator:str)->Path:
        return self.conversations/(self.operator_key(operator)+".jsonl")

    def append_turn(self,operator:str,response:dict[str,Any])->dict[str,Any]:
        cv=response.get("conversation") if isinstance(response.get("conversation"),dict) else {}
        turn={
          "schema":TURN_SCHEMA,"turn_id":"turn-"+uuid.uuid4().hex,
          "request_id":response.get("request_id"),"project_id":response.get("session_project_id") or response.get("project_id"),
          "submitted_at":response.get("submitted_at"),"responded_at":response.get("responded_at") or cv.get("responded_at"),
          "user":{"role":"user","text":str(response.get("submitted_user_message") or "")},
          "assistant":{"role":"assistant","text":str(cv.get("message") or response.get("message") or ""),
                       "kind":cv.get("kind") or "INFO",
                       "persona_id":((cv.get("dialogue_orchestrator") or {}).get("speaker_persona_id")
                         if isinstance(cv.get("dialogue_orchestrator"),dict) else None)},
          "status":response.get("status"),"next_action":response.get("next_action"),
          "response_digest":None,"automatic_external_spend_eur":0
        }
        path=self.timeline_path(operator);path.parent.mkdir(parents=True,exist_ok=True)
        with self.lock:
            if not path.exists():path.touch(mode=0o600)
            try:os.chmod(path,0o600)
            except Exception:pass
            with path.open("a",encoding="utf-8") as fh:fh.write(json.dumps(turn,ensure_ascii=False)+"\n")
        return turn

    def conversation_view(self,operator:str,limit:int=100)->dict[str,Any]:
        limit=max(1,min(200,int(limit)))
        path=self.timeline_path(operator);items=[]
        if path.is_file():
            try:
                lines=path.read_text(encoding="utf-8").splitlines()[-limit:]
                for line in lines:
                    try:
                        x=json.loads(line)
                        if isinstance(x,dict) and x.get("schema")==TURN_SCHEMA:items.append(x)
                    except Exception:pass
            except Exception:pass
        return {"schema":TIMELINE_SCHEMA,"items":items,"count":len(items),"limit":limit,
                "profile_available":self.profile_path(operator).is_file(),"automatic_external_spend_eur":0}

    def persona_catalog(self,limit:int=100)->dict[str,Any]:
        items=[]
        if self.persona_dir.is_dir():
            for path in sorted(self.persona_dir.glob("*.json"))[:max(1,min(200,int(limit)))]:
                try:
                    x=load(path)
                except Exception:
                    continue
                if x.get("schema")!="chacha.dev/fictional-persona-card/v1":continue
                items.append({
                  "persona_id":x.get("persona_id"),
                  "display_name":x.get("display_name"),
                  "stereotype_intensity":x.get("stereotype_intensity"),
                  "identity_frame":x.get("identity_frame") if isinstance(x.get("identity_frame"),dict) else {},
                  "source_mix":x.get("source_mix") if isinstance(x.get("source_mix"),dict) else {}
                })
        return {"schema":"chacha.dev/persona-catalog/v1","items":items,"count":len(items),
                "automatic_external_spend_eur":0}

    def selected_persona_path(self,operator:str)->Path|None:
        try:profile=self.profile_view(operator)
        except Exception:return None
        pid=str(profile.get("assistant_persona_id") or "").strip()
        if not pid:return None
        candidate=self.persona_dir/(safe_id(pid)+".json")
        if not candidate.is_file():return None
        try:
            x=load(candidate)
            if x.get("schema")!="chacha.dev/fictional-persona-card/v1" or str(x.get("persona_id") or "")!=pid:return None
        except Exception:return None
        return candidate

    def job_path(self,jid:str)->Path:return self.jobs/(safe_id(jid)+".json")
    def set_job(self,jid:str,**fields)->dict[str,Any]:
        with self.lock:
            p=self.job_path(jid);x=load(p,{"schema":"chacha.dev/direct-operator-job/v1","job_id":jid,"created_at":now_iso()})
            x.update(fields);x["updated_at"]=now_iso();atomic(p,x);return x

    def central(self,args:list[str],out:Path)->dict[str,Any]:
        cmd=[sys.executable,str(self.controller),"--repo-root",str(self.repo),"--runtime-root",str(self.runtime),"--output",str(out),*args]
        p=run(cmd)
        if not out.is_file():
            return {"schema":CENTRAL_RECEIPT_SCHEMA,"status":"BRAIN_UNAVAILABLE","brain_decision_obtained":False,
                    "project_id":"chacha-dev-platform","next_action":"RETRY_WHEN_BRAIN_AVAILABLE","evidence_refs":[],
                    "decision":{"stderr":p.stderr[-1200:]}}
        return load(out)

    def idempotency_key(self,operator:str,project:str,client_request_id:str)->str:
        raw=(operator+"\n"+project+"\n"+client_request_id).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def accept_intent(self,text:str,project:str,operator:str,client_request_id:str)->tuple[str,bool]:
        client_request_id=str(client_request_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}",client_request_id):
            raise ValueError("CLIENT_REQUEST_ID_INVALID")
        key=self.idempotency_key(operator,project,client_request_id)
        p=self.idempotency/(key+".json")
        text_digest="sha256:"+hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self.lock:
            if p.is_file():
                x=load(p)
                if x.get("text_digest")!=text_digest or x.get("operator")!=operator or x.get("project_id")!=project:
                    raise RuntimeError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                jid=str(x.get("job_id") or "")
                if jid and self.job_path(jid).is_file():return jid,False
            jid="doj-"+uuid.uuid4().hex
            self.set_job(jid,state="QUEUED",operator=operator,project_id=project,
                         client_request_id=client_request_id,text_digest=text_digest)
            atomic(p,{"schema":"chacha.dev/direct-operator-idempotency/v1","client_request_id":client_request_id,
                      "job_id":jid,"operator":operator,"project_id":project,"text_digest":text_digest,
                      "created_at":now_iso()})
            return jid,True

    def process(self,jid:str,text:str,project:str,operator:str)->None:
        project=stable_project(project,str(self.policy.get("default_project") or "chacha-dev-platform"))
        request_id="dor-"+uuid.uuid4().hex
        command=normalize(text)
        work=self.root/"requests"/request_id;work.mkdir(parents=True,exist_ok=True)
        intent={"schema":"chacha.dev/human-interface-intent/v1","request_id":request_id,"received_at":now_iso(),
          "source":"direct-operator","route":"CHACHA_DEV","command":command,"user_text":text,
          "project_id":project,"target_scope":"PLATFORM" if project=="chacha-dev-platform" else "PROJECT",
          "interface_decision_authority":False,"operator_identity":operator}
        atomic(work/"intent.json",intent)
        self.set_job(jid,state="TRANSLATING" if command=="INSTRUCTION" else "CENTRAL_ORCHESTRATION",
                     request_id=request_id,command=command,project_id=project)
        self.progress.begin(request_id,"ChaCha s’occupe de ta demande ✨",project)
        self.progress.update("direct-operator-service",100,"COMPLETE","Demande reçue",10,"Demande reçue")
        try:
            if command=="STOP":
                self.progress.update("central-interface-controller",35,"RUNNING","Activation du Stop",35,"Arrêt d’urgence en cours")
                out=work/"stop.json"
                p=run([sys.executable,str(self.emergency),"--state",str(self.runtime/"control/emergency-stop.json"),
                       "activate","--reason","direct-operator:"+request_id,"--actor","direct-operator"],120)
                try:payload=json.loads(p.stdout[p.stdout.index("{"):p.stdout.rindex("}")+1])
                except Exception:payload={"active":False}
                receipt={"schema":CENTRAL_RECEIPT_SCHEMA,"receipt_id":"stop-"+uuid.uuid4().hex,"observed_at":now_iso(),
                  "command":"STOP","project_id":project,"status":"STOP_ACTIVE" if payload.get("active") else "BRAIN_UNAVAILABLE",
                  "authority":"emergency-stop-controller","brain_decision_obtained":bool(payload.get("active")),
                  "next_action":"AWAIT_EXPLICIT_RESET_AND_HEALTH_CHECK","evidence_refs":[],"decision":{"emergency_stop":payload},
                  "automatic_external_spend_eur":0}
            elif command=="STATUS":
                self.progress.update("central-interface-controller",55,"RUNNING","Lecture de l’état plateforme",55,"ChaCha vérifie son état")
                receipt=self.central(["status","--project",project],work/"brain-receipt.json")
            elif command=="CONTINUE":
                self.progress.update("central-interface-controller",55,"RUNNING","Reprise de la dernière action",55,"ChaCha reprend")
                with self.lock:s=self.session()
                prior=Path(str(s.get("last_response_path") or ""));expected=str(s.get("last_response_digest") or "")
                if not prior.is_file() or not expected:
                    receipt={"schema":CENTRAL_RECEIPT_SCHEMA,"status":"BRAIN_RECEIPT_INVALID","brain_decision_obtained":False,
                      "project_id":project,"next_action":"AWAIT_NEW_INSTRUCTION","evidence_refs":[],"decision":{"reason":"NO_PRIOR_DIRECT_OPERATOR_RESPONSE"}}
                else:
                    receipt=self.central(["continue","--project",project,"--prior-response",str(prior),
                      "--expected-response-digest",expected,"--output-dir",str(work/"brain")],work/"brain-receipt.json")
            else:
                self.set_job(jid,state="TRANSLATING",request_id=request_id,command=command,project_id=project)
                self.progress.update("functional-translator-satellite",20,"RUNNING","Traduction de ta demande",28,"ChaCha comprend ta demande")
                trans=work/"translation"
                p=run([sys.executable,str(self.translator),"--repo-root",str(self.repo),"--text",text,
                  "--project",project,"--source","direct-operator","--operator",operator,
                  "--request-id",request_id,"--output-dir",str(trans)],180)
                if p.returncode!=0:raise RuntimeError("FUNCTIONAL_TRANSLATOR_FAILED:"+p.stderr[-1200:])
                translation=load(trans/"translation.json")
                self.progress.update("functional-translator-satellite",100,"COMPLETE","Intention prête",45,"Demande comprise ✨")
                self.set_job(jid,state="CENTRAL_ORCHESTRATION",translation=translation)
                self.progress.update("central-interface-controller",55,"RUNNING","Transmission au cerveau central",62,"Transmission au cerveau central")
                receipt=self.central(["instruction","--intent",str(trans/"interface-intent.json"),
                  "--output-dir",str(work/"brain")],work/"brain-receipt.json")
                self.progress.update("central-orchestrator",90,"RUNNING","Décision centrale reçue",88,"ChaCha finalise")
            if receipt.get("schema")!=CENTRAL_RECEIPT_SCHEMA:
                raise RuntimeError("CENTRAL_RECEIPT_SCHEMA_INVALID")

            continuation_steps=[]
            max_steps=max(1,int(((self.policy.get("auto_continue") or {}).get("max_steps")) or 24))
            if command in {"INSTRUCTION","CONTINUE"}:
                for step in range(max_steps):
                    if not should_auto_continue(receipt): break
                    prior_response=wrap(intent,receipt)
                    prior_response["project_id"]=project
                    prior_response["execution_project_id"]=receipt.get("project_id") or project
                    prior_path=work/("continuation-prior-%02d.json"%step)
                    atomic(prior_path,prior_response)
                    self.set_job(jid,state="CENTRAL_ORCHESTRATION",continuation_step=step+1,
                                 execution_project_id=prior_response["execution_project_id"],
                                 next_action=receipt.get("next_action"))
                    pct=min(92,64+(step+1)*4)
                    self.progress.update("central-orchestrator",pct,"RUNNING",
                      "Exécution : "+str(receipt.get("next_action") or "étape suivante"),
                      pct,"ChaCha poursuit l’exécution")
                    receipt=self.central(["continue","--project",project,"--prior-response",str(prior_path),
                      "--expected-response-digest",fd(prior_path),"--output-dir",str(work/("brain-cont-%02d"%step))],
                      work/("brain-receipt-cont-%02d.json"%step))
                    if receipt.get("schema")!=CENTRAL_RECEIPT_SCHEMA:
                        raise RuntimeError("CENTRAL_CONTINUATION_RECEIPT_SCHEMA_INVALID")
                    continuation_steps.append({
                      "step":step+1,"status":receipt.get("status"),"next_action":receipt.get("next_action"),
                      "execution_project_id":receipt.get("project_id")
                    })
                if should_auto_continue(receipt):
                    receipt={
                      "schema":CENTRAL_RECEIPT_SCHEMA,"receipt_id":"autocont-"+uuid.uuid4().hex,
                      "observed_at":now_iso(),"command":command,"project_id":project,
                      "status":"PARTIAL","authority":"central-orchestrator","brain_decision_obtained":True,
                      "next_action":"MANUAL_CONTINUE_REQUIRED","evidence_refs":receipt.get("evidence_refs") or [],
                      "decision":{"reason":"AUTO_CONTINUE_STEP_LIMIT","last_receipt":receipt},
                      "automatic_external_spend_eur":0
                    }

            central_for_conversation=work/"central-receipt-for-conversation.json"
            atomic(central_for_conversation,receipt)
            conversation_path=work/"conversation-response.json"
            human_context_path=work/"human-context.json"
            profile_path=self.profile_path(operator)
            human_cmd=[sys.executable,str(self.human_context),"--text",text,"--output",str(human_context_path)]
            if profile_path.is_file():human_cmd[2:2]=["--profile",str(profile_path)]
            hp=run(human_cmd,60)
            if hp.returncode!=0 or not human_context_path.is_file():
                atomic(human_context_path,{"schema":"chacha.dev/human-context-brief/v1","profile":{},
                  "interaction_signals":{},"rules":{"technical_decision_authority":False},
                  "fallback":True,"automatic_external_spend_eur":0})
            self.progress.update("conversation-interface-agent",55,"RUNNING","ChaCha prépare sa réponse",94,"ChaCha te répond")
            cp=run([sys.executable,str(self.conversation),"--receipt",str(central_for_conversation),
                    "--intent",str(work/"intent.json"),"--human-context",str(human_context_path),
                    "--output",str(conversation_path)],120)
            if cp.returncode==0 and conversation_path.is_file():
                conversation=load(conversation_path)
            else:
                conversation={"schema":"chacha.dev/conversation-response/v1","agent_id":"conversation-interface-agent",
                  "kind":"INFO","message":str(receipt.get("status") or "Réponse reçue"),
                  "requires_user_response":False,"status":receipt.get("status"),
                  "next_action":receipt.get("next_action"),"central_authority_preserved":True,
                  "decision_modified":False,"fallback":True,"automatic_external_spend_eur":0}

            # Dialogue Orchestrator may rephrase the already-locked human message.
            # It never receives or gains technical execution authority.
            dialogue_history_path=work/"dialogue-history.json"
            atomic(dialogue_history_path,self.conversation_view(operator,16))
            dialogue_path=work/"dialogue-response.json"
            self.progress.update("conversation-interface-agent",78,"RUNNING","ChaCha ajuste sa réponse",96,"ChaCha te répond naturellement")
            dialogue_cmd=[sys.executable,str(self.dialogue_orchestrator),
              "--base",str(conversation_path),"--human-context",str(human_context_path),
              "--timeline",str(dialogue_history_path),"--policy",str(self.dialogue_policy),
              "--output",str(dialogue_path)]
            persona_path=self.selected_persona_path(operator)
            if persona_path is not None:
                dialogue_cmd.extend(["--persona-card",str(persona_path)])
            if self.dialogue_attestation.is_file():
                dialogue_cmd.extend(["--attestation",str(self.dialogue_attestation)])
            dp=run(dialogue_cmd,150)
            if dp.returncode==0 and dialogue_path.is_file():
                candidate=load(dialogue_path)
                if candidate.get("schema")=="chacha.dev/conversation-response/v1":
                    conversation=candidate

            for ephemeral in (human_context_path,dialogue_history_path):
                try:ephemeral.unlink(missing_ok=True)
                except Exception:pass
            self.progress.update("conversation-interface-agent",100,"COMPLETE","Réponse prête",98,"Réponse prête ✨")
            response=wrap(intent,receipt)
            response["conversation"]=conversation
            response["message"]=conversation.get("message")
            response["submitted_user_message"]=text
            response["submitted_at"]=intent.get("received_at")
            response["session_project_id"]=project
            response["continuation_steps"]=continuation_steps
            response_path=self.responses/(safe_id(request_id)+".json");atomic(response_path,response)
            turn=self.append_turn(operator,response)
            response["conversation_turn_id"]=turn["turn_id"]
            atomic(response_path,response)
            with self.lock:
                s=self.session();s.update({"schema":"chacha.dev/direct-operator-session/v1","updated_at":now_iso(),
                  "active_project":project,"last_request_id":request_id,
                  "last_response_path":str(response_path),"last_response_digest":fd(response_path),
                  "last_command":command,"last_operator":operator});self.save_session(s)
            self.set_job(jid,state="COMPLETE",response=response,response_path=str(response_path))
            final_status=str(response.get("status") or "UNKNOWN").upper()
            if final_status in {"SUCCESS","PASS","OK","COMPLETE"}:
                self.progress.complete("C’est fait ✨")
            elif final_status in {"BLOCKED","FAILED","PARTIAL","AWAITING_APPROVAL"}:
                self.progress.complete("Traitement terminé — action requise")
            else:
                self.progress.complete("Traitement terminé")
        except Exception as exc:
            self.progress.fail("ChaCha a rencontré un problème")
            self.set_job(jid,state="FAILED",error=str(exc)[:2000])

class Handler(BaseHTTPRequestHandler):
    server_version="ChaChaDirectOperator/1.0"
    def log_message(self,fmt,*args):sys.stderr.write("%s %s\n"%(self.address_string(),fmt%args))
    @property
    def st(self)->State:return self.server.state  # type: ignore[attr-defined]
    def json(self,status:int,payload:dict[str,Any]):
        raw=json.dumps(payload,ensure_ascii=False).encode();self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff");self.end_headers();self.wfile.write(raw)
    def auth(self)->str|None:
        identity=operator_from_headers(self.headers,self.st.policy)
        if not identity:self.json(HTTPStatus.FORBIDDEN,{"status":"FORBIDDEN","reason":"TAILSCALE_IDENTITY_REQUIRED"});return None
        return identity
    def do_GET(self):
        parsed=urlparse(self.path);path=parsed.path
        if path=="/healthz":return self.json(200,{"status":"PASS","component":"direct-operator","bind":"loopback"})
        identity=self.auth()
        if not identity:return
        if path=="/api/v1/session":
            return self.json(200,self.st.session_view())
        if path=="/api/v1/conversation":
            qs=parse_qs(parsed.query);raw=(qs.get("limit") or ["100"])[0]
            try:limit=int(raw)
            except Exception:limit=100
            return self.json(200,self.st.conversation_view(identity,limit))
        if path=="/api/v1/human-profile":
            return self.json(200,self.st.profile_view(identity))
        if path=="/api/v1/personas":
            return self.json(200,self.st.persona_catalog())
        if path=="/api/v1/progress":
            return self.json(200,self.st.progress.snapshot())
        if path=="/api/v1/app-config":
            return self.json(200,self.st.effective_live_shell_config())
        if path=="/api/v1/native-update":
            return self.json(200,self.st.effective_native_update_manifest())
        if path.startswith("/api/v1/jobs/"):
            jid=path.rsplit("/",1)[-1];p=self.st.job_path(jid)
            return self.json(200,load(p)) if p.is_file() else self.json(404,{"status":"NOT_FOUND"})
        if path.startswith("/native-updates/"):
            rel_apk=path[len("/native-updates/"):]
            if not rel_apk or "/" in rel_apk or "\\" in rel_apk or not rel_apk.endswith(".apk"):
                return self.json(404,{"status":"NOT_FOUND"})
            root=self.st.native_update_packages_root.resolve()
            target=(root/rel_apk).resolve()
            try:target.relative_to(root)
            except ValueError:return self.json(403,{"status":"FORBIDDEN"})
            if not target.is_file():return self.json(404,{"status":"NOT_FOUND"})
            raw=target.read_bytes();self.send_response(200)
            self.send_header("Content-Type","application/vnd.android.package-archive")
            self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff");self.end_headers();self.wfile.write(raw);return
        rel="index.html" if path in {"/","/index.html"} else path.lstrip("/")
        ui_root=self.st.effective_ui_root()
        target=(ui_root/rel).resolve()
        try:target.relative_to(ui_root.resolve())
        except ValueError:return self.json(403,{"status":"FORBIDDEN"})
        if not target.is_file():return self.json(404,{"status":"NOT_FOUND"})
        raw=target.read_bytes();self.send_response(200)
        self.send_header("Content-Type",mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store")
        self.send_header("Content-Security-Policy","default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'")
        self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        identity=self.auth()
        if not identity:return
        path=urlparse(self.path).path
        if path=="/api/v1/human-profile":
            maxb=min(int(self.st.policy.get("max_request_bytes") or 65536),32768)
            try:n=int(self.headers.get("Content-Length") or 0)
            except Exception:n=0
            if n<=0 or n>maxb:return self.json(413,{"status":"INVALID_SIZE"})
            try:body=json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:return self.json(400,{"status":"INVALID_JSON"})
            if not isinstance(body,dict):return self.json(400,{"status":"PROFILE_OBJECT_REQUIRED"})
            return self.json(200,self.st.save_profile(identity,body))
        if path!="/api/v1/intent":return self.json(404,{"status":"NOT_FOUND"})
        maxb=int(self.st.policy.get("max_request_bytes") or 65536)
        try:n=int(self.headers.get("Content-Length") or 0)
        except Exception:n=0
        if n<=0 or n>maxb:return self.json(413,{"status":"INVALID_SIZE"})
        try:body=json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:return self.json(400,{"status":"INVALID_JSON"})
        text=str(body.get("text") or "").strip()
        if not text:return self.json(400,{"status":"TEXT_REQUIRED"})
        client_request_id=str(body.get("client_request_id") or "").strip()
        legacy_client_request_id=not bool(client_request_id)
        if legacy_client_request_id:client_request_id="legacy-"+uuid.uuid4().hex
        s=self.st.session()
        default_project=str(self.st.policy.get("default_project") or "chacha-dev-platform")
        project=stable_project(body.get("project") or s.get("active_project"),default_project)
        try:
            jid,created=self.st.accept_intent(text,project,identity,client_request_id)
        except ValueError as e:return self.json(400,{"status":str(e)})
        except RuntimeError as e:return self.json(409,{"status":str(e)})
        if created:
            threading.Thread(target=self.st.process,args=(jid,text,project,identity),daemon=True).start()
        state=load(self.st.job_path(jid)).get("state") or "QUEUED"
        self.json(202,{"status":"ACCEPTED","job_id":jid,"state":state,"project_id":project,
                       "client_request_id":client_request_id,"deduplicated":not created,
                       "legacy_non_idempotent_client":legacy_client_request_id})

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"))
    ap.add_argument("--policy",type=Path,required=True)
    a=ap.parse_args();repo=a.repo_root.resolve();runtime=a.runtime_root.resolve();policy=load(a.policy)
    if policy.get("schema")!=POLICY_SCHEMA:raise SystemExit("DIRECT_OPERATOR_POLICY_SCHEMA_INVALID")
    bind=str(policy.get("bind") or "")
    if bind not in {"127.0.0.1","::1","localhost"}:raise SystemExit("DIRECT_OPERATOR_LOOPBACK_BIND_REQUIRED")
    auth=policy.get("authentication") or {}
    if str(auth.get("mode"))!="TAILSCALE_SERVE_IDENTITY":raise SystemExit("DIRECT_OPERATOR_TAILSCALE_IDENTITY_REQUIRED")
    if not authorized_users(Path(str(auth.get("authorized_users_file") or ""))):raise SystemExit("DIRECT_OPERATOR_AUTHORIZED_USER_REQUIRED")
    server=ThreadingHTTPServer((bind,int(policy.get("port") or 8792)),Handler);server.state=State(repo,runtime,policy)  # type: ignore[attr-defined]
    print("CHACHA_DEV_DIRECT_OPERATOR=READY",flush=True);server.serve_forever();return 0

if __name__=="__main__":raise SystemExit(main())
