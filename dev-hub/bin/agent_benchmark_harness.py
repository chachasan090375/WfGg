#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any
def load(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding="utf-8"));assert isinstance(x,dict);return x
def save(p:Path,x)->None:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def family(agent_id:str,policy:dict)->str:
 for name,ids in (policy.get("fixture_families") or {}).items():
  if agent_id in ids:return name
 return "default"
def campaign(index:dict,fleet:dict,policy:dict,technology_watch:dict)->dict:
 by={str(a.get("agent_id")):a for a in fleet.get("agents") or []};contracts=[]
 for i,a in enumerate(index.get("scheduled_actions") or []):
  aid=str(a.get("agent_id") or "");row=by.get(aid) or {};sc=row.get("scorecard") or {}
  bid="bench-"+hashlib.sha256((aid+"|"+str(a.get("action"))+"|"+str(i)).encode()).hexdigest()[:18]
  contracts.append({"schema":"chacha.dev/agent-benchmark-contract/v1","benchmark_id":bid,"agent_id":aid,"action":a.get("action"),"fixture_family":family(aid,policy),"truth_scope":"BENCHMARK_ONLY","production_truth_eligible":False,"isolated_execution":True,"incumbent_control_group":True,"candidate_owner":"agent-foundry","logician_challenge":sc.get("logician_challenge"),"technology_watch_revalidation_required":True,"technology_watch_state":technology_watch.get("state"),"independent_oracle_required":True,"direct_agent_mutation":False,"self_scoring_authority":False,"self_promotion":False,"shadow_required":True,"pilot_required_for_material_change":True})
 return {"schema":"chacha.dev/agent-benchmark-campaign/v1","scheduled_action_count":len(index.get("scheduled_actions") or []),"contract_count":len(contracts),"contracts":contracts,"technology_watch":technology_watch,"benchmark_fixture_is_production_truth":False,"direct_agent_mutation":False,"agent_self_scoring_authority":False,"architecture_council_final_authority":True,"automatic_external_spend_eur":0}
def compare(inc:dict,cand:dict)->dict:
 if inc.get("verification")!="VERIFIED" or cand.get("verification")!="VERIFIED":return {"status":"BLOCKED","reason":"INDEPENDENT_VERIFICATION_REQUIRED","promotion_eligible":False}
 if inc.get("benchmark_id")!=cand.get("benchmark_id"):return {"status":"BLOCKED","reason":"BENCHMARK_ID_MISMATCH","promotion_eligible":False}
 im=inc.get("metrics") or {};cm=cand.get("metrics") or {};dims=sorted(set(im)&set(cm));delta={d:round(float(cm[d])-float(im[d]),3) for d in dims if isinstance(im[d],(int,float)) and isinstance(cm[d],(int,float))}
 gain=any(v>0 for v in delta.values());reg=any(v<0 for v in delta.values())
 return {"status":"PASS","delta":delta,"measurable_gain":gain,"material_regression":reg,"promotion_eligible":bool(gain and not reg),"architecture_council_final_authority":True}
def main():
 ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True);c=sub.add_parser("compile");c.add_argument("--index",type=Path,required=True);c.add_argument("--fleet",type=Path,required=True);c.add_argument("--policy",type=Path,required=True);c.add_argument("--technology-watch-status",type=Path,required=True);c.add_argument("--output",type=Path,required=True);q=sub.add_parser("compare");q.add_argument("--incumbent",type=Path,required=True);q.add_argument("--candidate",type=Path,required=True);q.add_argument("--output",type=Path,required=True);a=ap.parse_args()
 if a.cmd=="compile":x=campaign(load(a.index),load(a.fleet),load(a.policy),load(a.technology_watch_status))
 else:x=compare(load(a.incumbent),load(a.candidate))
 save(a.output,x);print(json.dumps(x,ensure_ascii=False));print("CHACHA_DEV_V650_AGENT_BENCHMARK_HARNESS=PASS")
if __name__=="__main__":main()
