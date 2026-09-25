#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time,subprocess,sys
from pathlib import Path
from typing import Any

OBS_SCHEMA="chacha.dev/dark-intelligence-observation/v1"
OUT_SCHEMA="chacha.dev/dark-intelligence-dossier/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def digest(v:str)->str:
    return hashlib.sha256(v.encode()).hexdigest()
def normalize(obs:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if obs.get("schema")!=OBS_SCHEMA: raise SystemExit("DARK_INTELLIGENCE_OBSERVATION_SCHEMA_INVALID")
    source_class=str(obs.get("source_class") or "")
    if source_class not in set(policy.get("source_classes") or []): raise SystemExit("DARK_INTELLIGENCE_SOURCE_CLASS_INVALID")
    collection=policy.get("collection") or {}
    if source_class=="tor_onion":
        if obs.get("network_isolated") is not True: raise SystemExit("DARK_INTELLIGENCE_TOR_ISOLATION_REQUIRED")
        if str(obs.get("network_route") or "") not in {"TOR_ISOLATED_CAPSULE","ISOLATED_PROXY_CAPSULE"}:
            raise SystemExit("DARK_INTELLIGENCE_TOR_ROUTE_INVALID")
    forbidden={
      "used_platform_credentials":False,
      "purchase_performed":False,
      "contact_or_post_performed":False,
      "payload_executed":False
    }
    for k,expected in forbidden.items():
        if bool(obs.get(k)) is not expected: raise SystemExit("DARK_INTELLIGENCE_FORBIDDEN_ACTION:"+k)
    claims=[]
    for i,c in enumerate(obs.get("claims") or []):
        if isinstance(c,str): claims.append({"id":f"claim-{i+1}","class":"general","required":True,"text":c})
        elif isinstance(c,dict):
            row=dict(c);row.setdefault("id",f"claim-{i+1}");row.setdefault("class","general");row.setdefault("required",True);claims.append(row)
    source_ref=str(obs.get("source_ref") or "")
    source_id=str(obs.get("source_id") or ("source-"+digest(source_ref)[:16]))
    evidence=[]
    for i,c in enumerate(claims):
        evidence.append({
          "id":f"{source_id}-e{i+1}","claim_id":c["id"],
          "type":str(obs.get("evidence_type") or ("security_advisory" if source_class=="threat_intelligence_feed" else "unverified_blog")),
          "origin":source_id,"independence_group":str(obs.get("independence_group") or source_id),
          "stance":"SUPPORT","verified":False,"reproducible":False,
          "source_class":source_class,"source_ref":source_ref
        })
    now=str(obs.get("observed_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
    tech={
      "technology_id":str(obs.get("subject_id") or "dark-intelligence:"+source_id),
      "publisher":str(obs.get("publisher") or source_id),
      "version":str(obs.get("version") or now[:10]),
      "release_date":str(obs.get("release_date") or now),
      "as_of":now,"claims":claims,"evidence":evidence,
      "operational":{"maintenance_health":50,"security_health":50,"rollback_documented":False},
      "architecture_fit":{"compatibility":50,"security_fit":50,"resource_efficiency":50,"observability":50,"rollback_readiness":50,"integration_fit":50,"cost_fit":100,"migration_safety":50},
      "blast_radius":"high" if source_class=="tor_onion" else "medium"
    }
    return {
      "schema":OUT_SCHEMA,"agent_id":"dark-intelligence-agent","observed_at":now,
      "source":{"id":source_id,"class":source_class,"ref":source_ref,"network_isolated":bool(obs.get("network_isolated"))},
      "claims":claims,"raw_source_authority":"ADVISORY_ONLY","technology_dossier":tech,
      "verification_handoff":{
        "technology_watch_evaluation_required":True,
        "truth_scoring_required":True,
        "source_reputation_required":True,
        "logician_falsification_required":True,
        "evidence_independence_graph_required":True,
        "guardian_required":True,"sentinel_required":True,"bastion_boundary_preserved":True
      },
      "direct_fact_promotion_allowed":False,"direct_decision_authority":False,
      "automatic_external_spend_eur":0
    }
def verify_with_technology_watch(repo_root:Path,dossier:dict[str,Any],output_dir:Path)->dict[str,Any]:
    output_dir.mkdir(parents=True,exist_ok=True)
    technology_dossier=output_dir/"technology-dossier.json"
    save(technology_dossier,dossier["technology_dossier"])
    service=repo_root/"dev-hub/bin/technology-watch-service.py"
    p=subprocess.run([
      sys.executable,str(service),"--repo-root",str(repo_root),"evaluate",
      "--dossier",str(technology_dossier),"--output-dir",str(output_dir)
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=180)
    evaluation=output_dir/"evaluation.json"
    if p.returncode!=0 or not evaluation.is_file():
        raise RuntimeError("DARK_INTELLIGENCE_TECHNOLOGY_WATCH_HANDOFF_FAILED:"+(p.stderr or p.stdout)[-1200:])
    result=load(evaluation)
    if result.get("status")!="PASS":
        raise RuntimeError("DARK_INTELLIGENCE_TECHNOLOGY_WATCH_EVALUATION_INVALID")
    return result

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--observation",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--verification-output-dir",type=Path,required=True)
    a=ap.parse_args()
    out=normalize(load(a.observation),load(a.policy));save(a.output,out)
    evaluation=verify_with_technology_watch(a.repo_root.resolve(),out,a.verification_output_dir)
    out["technology_watch_evaluation"]=evaluation
    save(a.output,out)
    print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V800_DARK_INTELLIGENCE_NORMALIZATION=PASS")
    print("CHACHA_DEV_V800_TECHNOLOGY_WATCH_HANDOFF=PASS")
    print("CHACHA_DEV_V800_UNVERIFIED_SOURCE_AUTHORITY=NO")
    return 0
if __name__=="__main__": raise SystemExit(main())
