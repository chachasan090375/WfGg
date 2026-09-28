#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,json,os,sqlite3
from pathlib import Path
from typing import Any
import canonical_component_registry as ccr
import component_registry_reconciler as reconciler

SCHEMA="chacha.dev/autonomy-self-model/v1"

def iso()->str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")
def load(p:Path,default=None):
    try:
        x=json.loads(p.read_text(encoding="utf-8"))
        return x
    except Exception:
        return {} if default is None else default
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,p)
def observation_count(db:Path)->int|None:
    if not db.is_file(): return None
    try:
        con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
        try:return int(con.execute('select count(*) from observations').fetchone()[0])
        finally:con.close()
    except Exception:return None
def active_release(platform:Path)->dict[str,Any]:
    current=platform/"current"
    try: release=current.resolve(strict=True)
    except Exception: return {"status":"MISSING","path":str(current),"revision":None}
    rev=None
    try: rev=(release/".revision").read_text(encoding="utf-8").strip()
    except Exception: pass
    return {"status":"ACTIVE","path":str(release),"revision":rev}
def issue_view(issue:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    code=str(issue.get("code") or "UNKNOWN")
    mapping=((policy.get("issue_owners") or {}).get(code) or {})
    return {
      "code":code,"severity":issue.get("severity"),"subject":issue.get("subject"),
      "class":mapping.get("class","UNKNOWN_DRIFT"),"owner":mapping.get("owner","UNRESOLVED"),
      "recommended_action":mapping.get("action") or issue.get("recommended_action") or "HUMAN_CLASSIFICATION_REQUIRED",
      "details":issue.get("details") or {},"mutation_authorized":False
    }
def build(repo:Path,runtime:Path,platform:Path,policy:dict[str,Any])->dict[str,Any]:
    reg_policy=load(repo/"dev-hub/config/canonical-component-registry.v1.json")
    canonical=ccr.build_registry(repo,reg_policy)
    fleet=load(runtime/"agent-evolution/fleet-observatory-latest.json",{})
    recon=reconciler.reconcile(repo,canonical,reg_policy,fleet if fleet else None,platform)
    issues=[issue_view(x,policy) for x in recon.get("issues") or [] if isinstance(x,dict)]
    blocking=sum(1 for x in issues if str(x.get("severity") or "").upper() in {"HIGH","CRITICAL"})
    fleet_expected=sum(1 for x in canonical.get("components") or [] if isinstance(x,dict) and x.get("fleet_required") is True)
    fleet_observed=len(fleet.get("agents") or []) if isinstance(fleet,dict) else 0
    dynamic=load(runtime/"canonical-registry/dynamic-components.json",{})
    status="PASS" if not issues else ("BLOCKED" if blocking else "DEGRADED")
    return {
      "schema":SCHEMA,"observed_at":iso(),"status":status,
      "identity":{"platform":"chacha-dev","active_release":active_release(platform)},
      "inventory":{"component_count":canonical.get("component_count"),"fleet_required_count":fleet_expected,
        "birth_contract_complete":canonical.get("birth_contract_complete"),"registry_digest":canonical.get("registry_digest"),
        "source":"canonical-component-registry"},
      "fleet":{"observed_count":fleet_observed,"expected_count":fleet_expected,
        "report_generated_at":fleet.get("generated_at") if isinstance(fleet,dict) else None,
        "source":"agent-fleet-observatory"},
      "observations":{"count":observation_count(runtime/"agent-observation/observations.db"),"source":"agent-observation-bus"},
      "dynamic_components":{"registration_count":len(dynamic.get("registrations") or []),"source":"universal-materialization-gate"},
      "reconciliation":{"status":recon.get("status"),"issue_count":len(issues),"blocking_issue_count":blocking,"issues":issues},
      "authority":{"read_only":True,"mutation_authority":False,"source_policy":policy.get("authorities") or {}},
      "automatic_external_spend_eur":0
    }
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"));ap.add_argument("--platform-root",type=Path,default=Path("/opt/chacha-dev/platform"));ap.add_argument("--policy",type=Path);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    repo=a.repo_root.resolve(); policy=load(a.policy or repo/"dev-hub/config/autonomy-self-model.v1.json")
    out=build(repo,a.runtime_root.resolve(),a.platform_root.resolve(),policy);save(a.output,out)
    print("CHACHA_DEV_AUTONOMY_SELF_MODEL="+str(out["status"]))
    print("COMPONENT_COUNT="+str(out["inventory"]["component_count"]))
    print("FLEET="+str(out["fleet"]["observed_count"])+"/"+str(out["fleet"]["expected_count"]))
    print("ISSUE_COUNT="+str(out["reconciliation"]["issue_count"]))
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0
if __name__=="__main__": raise SystemExit(main())
