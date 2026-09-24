#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
import agent_evolution_logician as ael

DIMENSIONS=["accuracy","coverage","calibration","evidence_quality","robustness","efficiency","handoff_quality","learning_quality","drift_resistance","authority_discipline"]

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def build_inventory(routing:dict[str,Any],seven:dict[str,Any],project_registries:list[dict[str,Any]])->dict[str,Any]:
    rows={}
    for role,spec in (routing.get("roles") or {}).items():
        rows[role]={"agent_id":role,"scope":"PLATFORM","source":"agent-routing","capabilities":spec.get("capabilities") or []}
    for role in seven.get("required_agents") or []:
        role=str(role)
        rows.setdefault(role,{"agent_id":role,"scope":"PLATFORM","source":"seven-agent-final-compromise","capabilities":[]})
    for reg in project_registries:
        for agent in reg.get("agents") or []:
            aid=str(agent.get("agent_id") or "")
            if not aid:continue
            key=f"{reg.get('project_id')}::{aid}"
            rows[key]={"agent_id":aid,"scope":"PROJECT","project_id":reg.get("project_id"),"source":"project-agent-registry","capabilities":agent.get("capabilities") or []}
    return {"schema":"chacha.dev/agent-evolution-inventory/v1","agents":sorted(rows.values(),key=lambda x:(x.get("scope"),x.get("project_id") or "",x["agent_id"])),"agent_count":len(rows),"automatic_external_spend_eur":0}

def score(agent_id:str,metrics:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    raw=metrics.get("dimensions") or {}
    dims={d:round(max(0,min(100,float(raw.get(d,50)))),1) for d in DIMENSIONS}
    weakest=min(dims.values());avg=round(sum(dims.values())/len(dims),1)
    incidents=int(metrics.get("verified_failures") or 0)+int(metrics.get("rollbacks") or 0)+int(metrics.get("handoff_failures") or 0)
    tech_debt=float(metrics.get("technology_debt") or 0)
    overlap=float(metrics.get("scope_overlap_risk") or 0)
    debt=round(max(0,min(100,(100-avg)*0.45+incidents*8+tech_debt*0.30+overlap*0.25)),1)
    th=policy.get("recommendation_thresholds") or {}
    if weakest<float(th.get("block_and_review_below",40)) or debt>=float(th.get("debt_block",70)):
        rec="BLOCK_AND_REVIEW"
    elif weakest<float(th.get("shadow_candidate_below",65)) or debt>=float(th.get("debt_shadow",40)):
        rec="SHADOW_CANDIDATE"
    elif weakest<float(th.get("keep_min_dimension",80)) or debt>=float(th.get("debt_watch",20)):
        rec="OPTIMIZE"
    else:rec="KEEP"
    scorecard={"schema":"chacha.dev/agent-evolution-scorecard/v1","agent_id":agent_id,"dimensions":dims,"average":avg,"weakest_dimension":min(dims,key=dims.get),"agent_debt":debt,"recommendation":rec,"automatic_external_spend_eur":0}
    scorecard["logician_challenge"]=ael.build(agent_id,scorecard)
    return scorecard

def plan(agent_id:str,scorecard:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    rec=scorecard["recommendation"]
    material=rec in {"SHADOW_CANDIDATE","BLOCK_AND_REVIEW"}
    return {
      "schema":"chacha.dev/agent-evolution-plan/v1","agent_id":agent_id,"recommendation":rec,
      "evolution_surfaces":policy.get("evolution_surfaces") or [],
      "self_evolution":{"proposal_allowed":True,"active_self_mutation":False,"self_promotion":False,"permission_expansion":False},
      "candidate":{"owner":"agent-foundry","isolated":True,"incumbent_control_group":True,"shadow_required":rec!="KEEP","pilot_required":material},
      "assurance":{"technology_watch_required":True,"logician_falsification_required":True,"guardian_permission_diff_required":True,"sentinel_regression_required":True,"architecture_council_final_authority":True},
      "promotion":{"measurable_gain_required":True,"no_material_regression_required":True,"rollback_required":True,"latest_version_priority":False},
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True)
    i=sub.add_parser("inventory");i.add_argument("--routing",type=Path,required=True);i.add_argument("--seven",type=Path,required=True);i.add_argument("--project-registry",type=Path,action="append",default=[]);i.add_argument("--output",type=Path,required=True)
    e=sub.add_parser("evaluate");e.add_argument("--agent-id",required=True);e.add_argument("--metrics",type=Path,required=True);e.add_argument("--policy",type=Path,required=True);e.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    if a.cmd=="inventory":
        out=build_inventory(load(a.routing),load(a.seven),[load(p) for p in a.project_registry]);save(a.output,out)
        print("CHACHA_DEV_V646_AGENT_INVENTORY=PASS");print("AGENT_COUNT="+str(out["agent_count"]));return 0
    sc=score(a.agent_id,load(a.metrics),load(a.policy));out={"scorecard":sc,"plan":plan(a.agent_id,sc,load(a.policy))};save(a.output,out)
    print("CHACHA_DEV_V646_AGENT_EVOLUTION_SCORECARD=PASS");print("CHACHA_DEV_V646_ACTIVE_SELF_MUTATION=NO");print("CHACHA_DEV_V646_SELF_PROMOTION=NO");return 0
if __name__=="__main__":raise SystemExit(main())
