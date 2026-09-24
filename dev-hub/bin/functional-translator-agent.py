#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys,time,uuid
from pathlib import Path
from typing import Any

OUT_SCHEMA="chacha.dev/functional-translation/v1"
HUMAN_INTENT_SCHEMA="chacha.dev/human-interface-intent/v1"

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def fd(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd:list[str],timeout:int=120)->None:
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
    if p.returncode!=0:raise SystemExit("FUNCTIONAL_TRANSLATOR_CHILD_FAILED:"+p.stderr[-1200:])

def main()->int:
    ap=argparse.ArgumentParser(description="ChaCha DEV satellite Functional Translator")
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--text",required=True)
    ap.add_argument("--project",default="chacha-dev-platform")
    ap.add_argument("--source",default="direct-operator")
    ap.add_argument("--operator",default="authenticated-operator")
    ap.add_argument("--request-id")
    ap.add_argument("--output-dir",type=Path,required=True)
    a=ap.parse_args()
    root=a.repo_root.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    request_id=a.request_id or ("fit-"+uuid.uuid4().hex)
    raw={
      "name":"Direct Operator Request "+request_id[:12],
      "text":a.text.strip(),
      "objective":a.text.strip(),
      "project":a.project,
      "source":a.source,
      "operator_identity":a.operator,
      "constraints":{
        "automatic_external_spend_eur":0,
        "functional_requirement_has_priority_over_user_technical_suggestion":True,
        "translator_has_execution_authority":False,
        "translator_has_architecture_authority":False,
        "central_orchestrator_required":True
      }
    }
    if not raw["text"]:raise SystemExit("FUNCTIONAL_TRANSLATOR_EMPTY_TEXT")
    raw_path=out/"functional-source-intent.json";save(raw_path,raw)
    contract=out/"functional-contract.json"
    preplan=out/"functional-preplan.json"
    run([sys.executable,str(root/"dev-hub/bin/specification-compiler.py"),"--intent",str(raw_path),"--output",str(contract)])
    run([sys.executable,str(root/"dev-hub/bin/functional-intent-orchestrator.py"),
         "--config",str(root/"dev-hub/config/domain-orchestration.v1.json"),
         "--intent",str(raw_path),"--output",str(preplan)])
    cv=load(contract);pv=load(preplan)
    interface_intent={
      "schema":HUMAN_INTENT_SCHEMA,
      "request_id":request_id,
      "received_at":now_iso(),
      "source":"functional-translator-satellite",
      "route":"CHACHA_DEV",
      "command":"INSTRUCTION",
      "user_text":raw["text"],
      "project_id":a.project,
      "target_scope":"PLATFORM" if a.project=="chacha-dev-platform" else "PROJECT",
      "interface_decision_authority":False,
      "functional_contract":str(contract),
      "functional_contract_digest":fd(contract),
      "functional_preplan":str(preplan),
      "functional_preplan_digest":fd(preplan)
    }
    interface_path=out/"interface-intent.json";save(interface_path,interface_intent)
    result={
      "schema":OUT_SCHEMA,"translated_at":now_iso(),"request_id":request_id,
      "project_id":a.project,"source":a.source,"operator_identity":a.operator,
      "raw_text_preserved":True,"raw_text_digest":"sha256:"+hashlib.sha256(raw["text"].encode()).hexdigest(),
      "functional_contract":str(contract),"functional_contract_digest":fd(contract),
      "functional_preplan":str(preplan),"functional_preplan_digest":fd(preplan),
      "interface_intent":str(interface_path),"interface_intent_digest":fd(interface_path),
      "primary_domains":pv.get("primary_domains") or [],
      "review_domains":pv.get("review_domains") or [],
      "criteria_count":len(cv.get("criteria") or []),
      "translator_execution_authority":False,
      "translator_architecture_authority":False,
      "central_orchestrator_required":True,
      "automatic_external_spend_eur":0
    }
    save(out/"translation.json",result)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
