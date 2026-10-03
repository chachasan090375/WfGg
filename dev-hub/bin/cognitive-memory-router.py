from __future__ import annotations
import argparse,json,re
from pathlib import Path
from typing import Any

AGENT_RE=re.compile(r"^[a-zA-Z0-9._:-]{1,128}$")

def load(path:Path)->dict[str,Any]:
    obj=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj,dict):raise ValueError("JSON_OBJECT_REQUIRED")
    return obj

def route(policy:dict[str,Any],request:dict[str,Any])->dict[str,Any]:
    if policy.get("schema")!="chacha.dev/cognitive-memory-fabric-policy/v1":raise ValueError("POLICY_SCHEMA")
    if request.get("schema")!="chacha.dev/cognitive-memory-request/v1":raise ValueError("REQUEST_SCHEMA")
    operation=str(request.get("operation") or "").upper();scope=str(request.get("scope") or "").upper()
    memory_type=str(request.get("memory_type") or "").lower();agent_id=str(request.get("agent_id") or "")
    if operation not in {"READ","WRITE"}:raise ValueError("OPERATION_INVALID")
    if scope not in {"AGENT","CENTRAL"}:raise ValueError("SCOPE_INVALID")
    if memory_type not in set(policy.get("memory_types") or []):raise ValueError("MEMORY_TYPE_INVALID")
    if scope=="AGENT" and not AGENT_RE.fullmatch(agent_id):raise ValueError("AGENT_ID_INVALID")
    privacy=request.get("privacy") if isinstance(request.get("privacy"),dict) else {}
    blockers=[]
    if privacy.get("contains_secret") is True:blockers.append("SECRET_FORBIDDEN")
    if privacy.get("contains_raw_user_content") is True:blockers.append("RAW_USER_CONTENT_FORBIDDEN")
    if operation=="WRITE" and policy.get("privacy",{}).get("filtered_learning_sources_only") and request.get("filtered_source") is not True:
        blockers.append("FILTERED_SOURCE_REQUIRED")
    if operation=="WRITE" and scope=="CENTRAL":
        if policy.get("routing",{}).get("central_write_requires_trusted_state") and request.get("trust_state")!="TRUSTED":blockers.append("CENTRAL_TRUST_REQUIRED")
        if int(request.get("evidence_count") or 0)<int(policy.get("routing",{}).get("central_write_minimum_evidence") or 0):blockers.append("CENTRAL_EVIDENCE_INSUFFICIENT")
    ns=policy.get("namespaces") or {};src=policy.get("existing_sources") or {}
    if operation=="READ":
        sources=[]
        if scope=="AGENT":
            sources.append(str(Path(ns["agent_hot_root"])/(agent_id+".jsonl")))
            if policy.get("routing",{}).get("agent_read_includes_central_fallback"):sources.append(src["central_memory_snapshot"])
        else:sources.append(src["central_memory_snapshot"])
        destination=None
    else:
        sources=[]
        destination=(str(Path(ns["agent_hot_root"])/(agent_id+".jsonl")) if scope=="AGENT" else src["central_memory_db"])
    assist=policy.get("cognitive_assist") or {}
    return {
      "schema":"chacha.dev/cognitive-memory-route-plan/v1","status":"PASS" if not blockers else "HOLD",
      "operation":operation,"scope":scope,"memory_type":memory_type,"agent_id":agent_id or None,
      "sources":sources,"destination":destination,"long_term_tier":ns.get("long_term_tier"),"blockers":blockers,
      "cognitive_assist":{"provider_id":assist.get("provider_id"),"requested":bool(request.get("cognitive_assist")),"advisory_only":True,"activation_required":False},
      "execution_authority":False,"production_mutation":False,"automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--request",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=route(load(a.policy),load(a.request));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print("CHACHA_DEV_COGNITIVE_MEMORY_ROUTER="+out["status"]);print("EXECUTION_AUTHORITY=NO");return 0 if out["status"]=="PASS" else 10
if __name__=="__main__":raise SystemExit(main())
