#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA_IN="chacha.dev/dispatch-envelope/v1";SCHEMA_OUT="chacha.dev/task-result/v1"
ADAPTER="platform-command-adapter";PROVIDER="chacha-tech-watch"
ROOT=Path(os.environ.get("CHACHA_DEV_PLATFORM_ROOT","/opt/chacha-dev/platform/current")).resolve();WATCH=ROOT/"dev-hub/bin/technology-watch-service.py"
SUPPORTED={"technology-radar":"read","architecture-optimization":"plan"}
def now():return datetime.now(timezone.utc).isoformat()
def digest(b:bytes):return "sha256:"+hashlib.sha256(b).hexdigest()
def emit(req:dict[str,Any],status:str,summary:str,evidence=None,code=0):
 t=req.get("task") if isinstance(req.get("task"),dict) else {}
 outputs=[{"type":o.get("type"),"id":o.get("id"),"status":"UNVERIFIED"} for o in t.get("outputs") or [] if isinstance(o,dict)]
 x={"schema":SCHEMA_OUT,"project":str(req.get("project") or "unknown"),"task_id":str(t.get("id") or "unknown"),"status":status,"producer":ADAPTER,"observed_at":now(),"summary":summary,"evidence":evidence or [],"verification":{"status":"UNVERIFIED","method":"none","verifier":"none","observed_at":now(),"notes":"Independent verification required."},"outputs":outputs}
 print(json.dumps(x,ensure_ascii=False,separators=(",",":")));return code
def parse_json_prefix(text:str)->dict[str,Any]:
 x=json.JSONDecoder().raw_decode(text.lstrip())[0]
 if not isinstance(x,dict):raise ValueError("TECHNOLOGY_WATCH_OUTPUT_NOT_OBJECT")
 return x
def main():
 try:req=json.load(sys.stdin)
 except Exception:return emit({"task":{"id":"unknown"}},"BLOCKED","INPUT_JSON_INVALID",code=2)
 if not isinstance(req,dict) or req.get("schema")!=SCHEMA_IN:return emit(req if isinstance(req,dict) else {},"BLOCKED","INPUT_SCHEMA_INVALID",code=2)
 task=req.get("task") if isinstance(req.get("task"),dict) else {};caps=[str(x) for x in task.get("capabilities") or []]
 if len(caps)!=1 or caps[0] not in SUPPORTED:return emit(req,"BLOCKED","PLATFORM_COMMAND_CAPABILITY_UNSUPPORTED",code=2)
 cap=caps[0];expected=SUPPORTED[cap]
 if task.get("permission")!=expected:return emit(req,"BLOCKED","PLATFORM_COMMAND_PERMISSION_REQUIRED:"+expected,code=2)
 if not any(isinstance(x,dict) and x.get("provider")==PROVIDER and x.get("adapter")==ADAPTER for x in req.get("bindings") or []):return emit(req,"BLOCKED","PLATFORM_COMMAND_BINDING_MISSING",code=2)
 if not WATCH.is_file():return emit(req,"BLOCKED","TECHNOLOGY_WATCH_RUNTIME_MISSING",code=2)
 meta=req.get("metadata") if isinstance(req.get("metadata"),dict) else {};domain=str(meta.get("domain") or "")
 argv=[sys.executable,str(WATCH),"--repo-root",str(ROOT),"consult","--consumer","architecture-optimizer","--capability",cap]
 if domain:argv += ["--domain",domain]
 p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30,shell=False)
 raw=(p.stdout+"\n"+p.stderr).encode()
 if p.returncode!=0:return emit(req,"FAILED","TECHNOLOGY_WATCH_CONSULT_FAILED",[{"kind":"command","source":str(WATCH),"digest":digest(raw),"details":{"returncode":p.returncode,"capability":cap}}],1)
 try:feed=parse_json_prefix(p.stdout)
 except Exception:return emit(req,"FAILED","TECHNOLOGY_WATCH_CONSULT_INVALID",[{"kind":"command","source":str(WATCH),"digest":digest(raw),"details":{"capability":cap}}],1)
 fresh=feed.get("snapshot_freshness")=="FRESH";zero=float(feed.get("automatic_external_spend_eur") or 0)==0
 ev=[{"kind":"report","source":"local://technology-watch/consult","digest":digest(json.dumps(feed,sort_keys=True).encode()),"details":{"capability":cap,"domain":domain,"snapshot_freshness":feed.get("snapshot_freshness"),"source_snapshot_digest":feed.get("source_snapshot_digest"),"eligible_provider_candidates":len(feed.get("eligible_provider_candidates") or []),"automatic_external_spend_eur":feed.get("automatic_external_spend_eur")}}]
 return emit(req,"OK" if fresh and zero else "FAILED","TECHNOLOGY_WATCH_CONSULT_OK" if fresh and zero else "TECHNOLOGY_WATCH_CONSULT_NOT_READY",ev,0 if fresh and zero else 1)
if __name__=="__main__":raise SystemExit(main())
