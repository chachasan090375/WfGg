#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
from typing import Any
import agent_evolution_controller as aec

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def canon(x:Any)->bytes:return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
def digest(x:Any)->str:return "sha256:"+hashlib.sha256(canon(x)).hexdigest()
def key(row:dict[str,Any])->tuple[str,str,str]:
    return (str(row.get("scope") or "PLATFORM"),str(row.get("project_id") or ""),str(row.get("agent_id") or ""))
def safe_name(v:str)->str:return re.sub(r"[^A-Za-z0-9_.-]+","_",v)
def build_index(report:dict[str,Any],routing:dict[str,Any],seven:dict[str,Any],project_regs:list[dict[str,Any]],
                adapter_cfg:dict[str,Any],evolution_policy:dict[str,Any],profile_policy:dict[str,Any])->dict[str,Any]:
    inv=aec.build_inventory(routing,seven,project_regs)
    by={key(x):x for x in report.get("agents") or []}
    adapter_specs=adapter_cfg.get("supported_agents") or {}
    maturity=((evolution_policy.get("measurement") or {}).get("evidence_maturity") or {})
    target=float(maturity.get("minimum_production_dimension_coverage_for_candidate_pct") or profile_policy.get("production_maturity_target_pct") or 40)
    rows=[]
    for item in inv.get("agents") or []:
        k=key(item);fleet=by.get(k)
        if fleet is None:
            matches=[x for x in report.get("agents") or [] if str(x.get("agent_id"))==str(item.get("agent_id")) and str(x.get("scope") or "PLATFORM")==str(item.get("scope") or "PLATFORM")]
            fleet=matches[0] if len(matches)==1 else {}
        aid=str(item.get("agent_id") or "")
        sc=(fleet or {}).get("scorecard") or {};pl=(fleet or {}).get("plan") or {}
        total=float(sc.get("measurement_coverage_pct") or 0);prod=float(sc.get("production_measurement_coverage_pct") or 0);bench=float(sc.get("benchmark_measurement_coverage_pct") or 0)
        adapter=adapter_specs.get(aid);supported=isinstance(adapter,dict)
        if not supported and total<40:next_action="INSTRUMENT_EXECUTABLE_ADAPTER"
        elif total<40:next_action="RUN_EXECUTABLE_BENCHMARK"
        elif prod<target:next_action="ACCUMULATE_PRODUCTION_EVIDENCE"
        elif sc.get("unmeasured_dimensions"):next_action="MEASURE_REMAINING_DIMENSIONS"
        else:next_action="CONTINUE_MONITORING"
        project_local=str(item.get("scope"))=="PROJECT"
        identity={"agent_id":aid,"scope":item.get("scope"),"project_id":item.get("project_id"),"source":item.get("source"),"capabilities":sorted(item.get("capabilities") or [])}
        contract_fingerprint=digest({"identity":identity,"profile_policy_version":profile_policy.get("version"),"evolution_policy_version":evolution_policy.get("version"),"adapter":adapter})
        row={
          "schema":"chacha.dev/agent-evolution-profile/v1",
          "profile_id":(str(item.get("project_id"))+"::"+aid) if project_local else aid,
          "identity":identity,"risk":(fleet or {}).get("risk") or "medium",
          "contract_fingerprint":contract_fingerprint,
          "profile_is_performance_score":False,
          "measurement":{
            "recommendation":sc.get("recommendation") or "MEASURE_FIRST",
            "total_coverage_pct":total,"production_coverage_pct":prod,"benchmark_coverage_pct":bench,
            "unmeasured_dimensions":sc.get("unmeasured_dimensions") or list(aec.DIMENSIONS),
            "production_maturity_target_pct":target,
            "executable_adapter_supported":supported,
            "adapter":(adapter or {}).get("adapter") if supported else None,
            "strategy":"EXECUTABLE_BENCHMARK_PLUS_PRODUCTION_OBSERVATION" if supported else "PROFILE_ONLY",
            "next_action":next_action
          },
          "evolution":{
            "scope":"PROJECT_LOCAL" if project_local else "PLATFORM",
            "platform_global_promotion_forbidden":project_local,
            "candidate_owner":"agent-foundry",
            "candidate_materialization_allowed_now":bool(((pl.get("candidate") or {}).get("owner"))),
            "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
            "technology_watch_revalidation_required":True,"logician_falsification_required":True,
            "guardian_required":True,"sentinel_required":True,"architecture_council_final_authority":True,
            "latest_version_priority":False
          },
          "observation_bus":{"inventory_or_capability_change_requires_reassessment":True,"profile_policy_change_requires_reassessment":True},
          "automatic_external_spend_eur":0
        }
        rows.append(row)
    rows.sort(key=lambda x:(x["identity"]["scope"],str(x["identity"].get("project_id") or ""),x["identity"]["agent_id"]))
    return {"schema":"chacha.dev/agent-evolution-profile-index/v1","profile_count":len(rows),"profiles":rows,
      "profile_is_performance_score":False,"automatic_external_spend_eur":0}
def write_profiles(root:Path,index:dict[str,Any])->None:
    root.mkdir(parents=True,exist_ok=True)
    for p in index.get("profiles") or []:save(root/(safe_name(str(p["profile_id"]))+".json"),p)
    save(root/"index.json",index)
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--fleet",type=Path,required=True);ap.add_argument("--routing",type=Path,required=True);ap.add_argument("--seven",type=Path,required=True)
    ap.add_argument("--project-registry",type=Path,action="append",default=[]);ap.add_argument("--adapter-config",type=Path,required=True);ap.add_argument("--evolution-policy",type=Path,required=True);ap.add_argument("--profile-policy",type=Path,required=True);ap.add_argument("--output-root",type=Path,required=True);a=ap.parse_args()
    idx=build_index(load(a.fleet),load(a.routing),load(a.seven),[load(p) for p in a.project_registry],load(a.adapter_config),load(a.evolution_policy),load(a.profile_policy));write_profiles(a.output_root,idx)
    print("CHACHA_DEV_V654_UNIVERSAL_AGENT_PROFILES=PASS");print("PROFILE_COUNT="+str(idx["profile_count"]));print("PROFILE_IS_PERFORMANCE_SCORE=NO");print("CHACHA_DEV_V654_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
if __name__=="__main__":raise SystemExit(main())
