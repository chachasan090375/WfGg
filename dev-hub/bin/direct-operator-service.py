#!/usr/bin/env python3
from __future__ import annotations

import argparse,hashlib,json,mimetypes,os,re,subprocess,sys,threading,time,uuid
from email.header import decode_header
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from progress_state_controller import ProgressStore

HUMAN_RESPONSE_SCHEMA="chacha.dev/human-interface-response/v1"
CENTRAL_RECEIPT_SCHEMA="chacha.dev/central-interface-receipt/v1"
POLICY_SCHEMA="chacha.dev/direct-operator-policy/v1"

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
      "project_id":receipt.get("project_id") or intent.get("project_id"),
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
        self.session_path=self.root/"session.json";self.lock=threading.RLock()
        ui=Path(str(policy.get("ui_root") or "dev-hub/direct-operator-ui"))
        self.ui=ui if ui.is_absolute() else repo/ui
        self.controller=repo/str(policy.get("central_controller") or "dev-hub/bin/central-interface-controller.py")
        self.translator=repo/str(((policy.get("translator") or {}).get("script")) or "dev-hub/bin/functional-translator-agent.py")
        self.emergency=repo/str(policy.get("emergency_controller") or "dev-hub/bin/emergency-stop-controller.py")
        progress_policy=repo/str(policy.get("progress_policy") or "dev-hub/config/progress-reporting.v1.json")
        self.progress=ProgressStore(load(progress_policy))
        live_shell_path=repo/str(policy.get("android_live_shell_config") or "dev-hub/config/android-live-shell.v1.json")
        self.live_shell_config=load(live_shell_path)
    def effective_ui_root(self):
        live=self.live_ui_root
        if (live/"index.html").is_file():return live
        return self.ui_root
    def effective_live_shell_config(self):
        try:
            x=load(self.live_app_config)
            if x.get("schema")=="chacha.dev/android-live-shell-config/v1":return x
        except Exception:pass
        return self.live_shell_config

    def session(self)->dict[str,Any]:
        return load(self.session_path,{"schema":"chacha.dev/direct-operator-session/v1",
          "active_project":self.policy.get("default_project") or "chacha-dev-platform"})
    def save_session(self,x:dict[str,Any])->None:atomic(self.session_path,x)
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

    def process(self,jid:str,text:str,project:str,operator:str)->None:
        request_id="dor-"+uuid.uuid4().hex
        command=normalize(text)
        work=self.root/"requests"/request_id;work.mkdir(parents=True,exist_ok=True)
        intent={"schema":"chacha.dev/human-interface-intent/v1","request_id":request_id,"received_at":now_iso(),
          "source":"direct-operator","route":"CHACHA_DEV","command":command,"user_text":text,
          "project_id":project,"target_scope":"PLATFORM" if project=="chacha-dev-platform" else "PROJECT",
          "interface_decision_authority":False,"operator_identity":operator}
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
            response=wrap(intent,receipt)
            response_path=self.responses/(safe_id(request_id)+".json");atomic(response_path,response)
            with self.lock:
                s=self.session();s.update({"schema":"chacha.dev/direct-operator-session/v1","updated_at":now_iso(),
                  "active_project":response.get("project_id") or project,"last_request_id":request_id,
                  "last_response_path":str(response_path),"last_response_digest":fd(response_path),
                  "last_command":command,"last_operator":operator});self.save_session(s)
            self.set_job(jid,state="COMPLETE",response=response,response_path=str(response_path))
            self.progress.complete("C’est fait ✨")
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
        path=urlparse(self.path).path
        if path=="/healthz":return self.json(200,{"status":"PASS","component":"direct-operator","bind":"loopback"})
        identity=self.auth()
        if not identity:return
        if path=="/api/v1/session":
            s=self.st.session();return self.json(200,{"status":"OK","active_project":s.get("active_project"),"last_command":s.get("last_command")})
        if path=="/api/v1/progress":
            return self.json(200,self.st.progress.snapshot())
        if path=="/api/v1/app-config":
            return self.json(200,self.st.effective_live_shell_config())
        if path.startswith("/api/v1/jobs/"):
            jid=path.rsplit("/",1)[-1];p=self.st.job_path(jid)
            return self.json(200,load(p)) if p.is_file() else self.json(404,{"status":"NOT_FOUND"})
        rel="index.html" if path in {"/","/index.html"} else path.lstrip("/")
        target=(self.st.ui/rel).resolve()
        try:target.relative_to(self.st.ui.resolve())
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
        if path!="/api/v1/intent":return self.json(404,{"status":"NOT_FOUND"})
        maxb=int(self.st.policy.get("max_request_bytes") or 65536)
        try:n=int(self.headers.get("Content-Length") or 0)
        except Exception:n=0
        if n<=0 or n>maxb:return self.json(413,{"status":"INVALID_SIZE"})
        try:body=json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:return self.json(400,{"status":"INVALID_JSON"})
        text=str(body.get("text") or "").strip()
        if not text:return self.json(400,{"status":"TEXT_REQUIRED"})
        s=self.st.session();project=str(body.get("project") or s.get("active_project") or self.st.policy.get("default_project"))
        jid="doj-"+uuid.uuid4().hex
        self.st.set_job(jid,state="QUEUED",operator=identity,project_id=project)
        threading.Thread(target=self.st.process,args=(jid,text,project,identity),daemon=True).start()
        self.json(202,{"status":"ACCEPTED","job_id":jid,"state":"QUEUED","project_id":project})

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
