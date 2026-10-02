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
from session_bootstrap_cockpit import build as build_session_bootstrap
import operator_directive_intake as odi

HUMAN_RESPONSE_SCHEMA="chacha.dev/human-interface-response/v1"
CENTRAL_RECEIPT_SCHEMA="chacha.dev/central-interface-receipt/v1"
POLICY_SCHEMA="chacha.dev/direct-operator-policy/v1"
PROFILE_SCHEMA="chacha.dev/human-conversation-profile/v1"
TIMELINE_SCHEMA="chacha.dev/conversation-timeline/v1"
TURN_SCHEMA="chacha.dev/conversation-turn/v1"
PROFILE_ALLOWED_FIELDS={
  "preferred_name","preferred_form_of_address","gender_identity","age_band","languages",
  "cultural_contexts","regional_contexts","conversation_register","directness","verbosity",
  "humor_level","voice_preferences","assistant_persona_id","preferred_channel"
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

TARGET_REQUEST_RX=re.compile(r"\bdor-[0-9a-f]{32}\b",re.I)
RECOVERY_CUES=(
    "reprise","reprendre","repris","resume","recover","recovery",
    "répar","repair","blocage","blocked","continuation","continue",
    "adapter_enablement_required","provider_health_probe_required",
    "provider_probe_definition_required","provider_binding_required",
    "task_graph_decomposition_required"
)

def targeted_platform_recovery(text:str,project:str,direct_operator_root:Path,operator:str|None=None)->str|None:
    if project!="chacha-dev-platform":return None
    folded=str(text or "").casefold()
    if not any(cue in folded for cue in RECOVERY_CUES):return None
    seen=set()
    for match in TARGET_REQUEST_RX.finditer(str(text or "")):
        request_id=match.group(0).lower()
        if request_id in seen:continue
        seen.add(request_id)
        prior=direct_operator_root/"responses"/(safe_id(request_id)+".json")
        if not prior.is_file():continue
        try:payload=load(prior)
        except Exception:continue
        if payload.get("schema")!="chacha.dev/human-interface-response/v1":continue
        if stable_project(payload.get("project_id"))!="chacha-dev-platform":continue
        if operator:
            source_intent=direct_operator_root/"requests"/request_id/"intent.json"
            if not source_intent.is_file():continue
            try:owner=str(load(source_intent).get("operator_identity") or "").casefold()
            except Exception:continue
            if not owner or owner!=str(operator).casefold():continue
        return request_id
    return None

def should_auto_continue(receipt:dict[str,Any])->bool:
    status=str(receipt.get("status") or "").upper()
    next_action=str(receipt.get("next_action") or "").upper()
    non_terminal=(status in {"PLAN_READY","CONTINUED","READY"} or status.startswith("CONTINUED_") or status.endswith("_PLAN_READY"))
    if not non_terminal: return False
    if next_action.startswith("AWAIT_") or "APPROVAL" in next_action: return False
    return True

def progress_stage(next_action:Any)->tuple[str,int,int,str]:
    action=str(next_action or "").upper()
    rules=(
      (("DOMAIN_FACTORIES","DOMAIN_FACTORY"),"domain-factory",58,52,"Construction des domaines"),
      (("PROVIDER_HEALTH","ADAPTER_ENABLEMENT","PROVIDER_BINDING","PROBE_DEFINITION","READINESS"),"domain-readiness",68,60,"Vérification de la readiness"),
      (("SCHEDULER",),"execution-scheduler",76,68,"Planification des tâches"),
      (("GUARDIAN",),"guardian",82,74,"Contrôle Guardian"),
      (("RUN_CONTROLLER",),"run-controller",88,82,"Exécution gouvernée"),
      (("VERIFICATION",),"independent-verification",94,90,"Vérification indépendante"),
      (("CANDIDATE","RELEASE","PUBLICATION","QUALIFICATION","PROMOTION","ROLLBACK","APPROVAL"),"release-lifecycle",96,94,"Cycle de release"),
    )
    for needles,module,pct,overall,detail in rules:
        if any(n in action for n in needles):return module,pct,overall,detail
    return "central-orchestrator",72,64,"Orchestration centrale"
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
        dual=policy.get("dual_channel") if isinstance(policy.get("dual_channel"),dict) else {}
        self.dual_channel_policy=repo/str(dual.get("policy") or "dev-hub/config/dual-channel.v1.json")
        self.channel_router=repo/str(dual.get("router") or "dev-hub/bin/conversation-channel-router.py")
        self.advisory_bus=repo/str(dual.get("advisory_bus") or "dev-hub/bin/conversation-advisory-bus.py")
        self.research_broker=repo/str(dual.get("research_broker") or "dev-hub/bin/research-broker.py")
        self.conversation_reasoner=repo/str(dual.get("reasoner") or "dev-hub/bin/conversation-reasoner.py")
        self.conversation_reasoner_policy=repo/str(dual.get("reasoner_policy") or "dev-hub/config/conversation-reasoner.v1.json")
        self.conversation_reasoner_attestation=Path(str(dual.get("zero_cost_attestation") or "/opt/chacha-dev/runtime/provider-economics/agy-conversation-zero-cost.json"))
        self.central_memory_snapshot=Path(str(dual.get("central_memory_snapshot") or "/opt/chacha-dev/runtime/knowledge/central-memory-assimilation.json"))
        self.technology_watch_snapshot=Path(str(dual.get("technology_watch_snapshot") or "/opt/chacha-dev/runtime/technology-watch/optimizer-input.json"))
        self.human_behavior_db=Path(str(hbc_cfg.get("evidence_db") or "/opt/chacha-dev/runtime/knowledge/human-behavior/evidence.db"))
        self.emergency=repo/str(policy.get("emergency_controller") or "dev-hub/bin/emergency-stop-controller.py")
        progress_policy=repo/str(policy.get("progress_policy") or "dev-hub/config/progress-reporting.v1.json")
        self.progress=ProgressStore(load(progress_policy))
        live_shell_path=repo/str(policy.get("android_live_shell_config") or "dev-hub/config/android-live-shell.v1.json")
        self.live_shell_config=load(live_shell_path)
        native_policy_path=repo/str(policy.get("android_native_update_policy") or "dev-hub/config/android-native-update.v1.json")
        self.native_update_policy=load(native_policy_path)
        self.native_update_manifest=Path(str(policy.get("native_update_manifest") or "/opt/chacha-dev/runtime/native-update/current/manifest.json"))
        self.native_update_packages_root=Path(str(policy.get("native_update_packages_root") or "/opt/chacha-dev/runtime/native-update/current/packages"))
        directive_cfg=policy.get("operator_directives") if isinstance(policy.get("operator_directives"),dict) else {}
        directive_policy=Path(str(directive_cfg.get("policy") or "dev-hub/config/operator-directives.v1.json"))
        self.operator_directive_policy_path=directive_policy if directive_policy.is_absolute() else repo/directive_policy
        self.operator_directive_policy=load(self.operator_directive_policy_path)
        directive_runtime=self.operator_directive_policy.get("runtime") if isinstance(self.operator_directive_policy.get("runtime"),dict) else {}
        self.operator_directive_intake=Path(str(directive_cfg.get("intake") or directive_runtime.get("intake") or "/opt/chacha-dev/runtime/governance/operator-directives/intake.jsonl"))
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
        out={"status":"OK","active_project":s.get("active_project"),"active_channel":s.get("active_channel"),
             "progress":self.progress.snapshot(),
             "canonical_bootstrap":build_session_bootstrap(self.runtime,self.repo),
             "last_command":s.get("last_command"),"last_request_id":s.get("last_request_id"),
             "last_conversation_request_id":s.get("last_conversation_request_id"),
             "has_build_continuation":bool(s.get("last_response_path") and s.get("last_response_digest")),
             "has_conversation_history":bool(s.get("last_conversation_response_path") and s.get("last_conversation_response_digest"))}
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
          "channel":response.get("channel") or ("BUILD" if response.get("route")=="CHACHA_DEV" else None),
          "subroute":response.get("subroute"),
          "submitted_at":response.get("submitted_at"),"responded_at":response.get("responded_at") or cv.get("responded_at"),
          "user":{"role":"user","text":str(response.get("submitted_user_message") or "")},
          "assistant":{"role":"assistant","text":str(cv.get("message") or response.get("message") or ""),
                       "kind":cv.get("kind") or "INFO",
                       "persona_id":(
                         (cv.get("dialogue_orchestrator") or {}).get("speaker_persona_id")
                         if isinstance(cv.get("dialogue_orchestrator"),dict)
                         else ((cv.get("conversation_reasoner") or {}).get("speaker_persona_id")
                           if isinstance(cv.get("conversation_reasoner"),dict) else None))},
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