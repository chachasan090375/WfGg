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
  fixture_contract={"fixture_family":family(aid,policy),"action":a.get("action"),"agent_id":aid,"truth_scope":"BENCHMARK_ONLY"}
  environment_contract={"isolated_execution":True,"same_inputs_required":True,"network_escalation":False,"automatic_external_spend_eur":0}
  contracts.append({"schema":"chacha.dev/agent-benchmark-contract/v1","benchmark_id":bid,"agent_id":aid,"action":a.get("action"),
    "fixture_family":fixture_contract["fixture_family"],"fixture_contract":fixture_contract,
    "fixture_contract_digest":"sha256:"+hashlib.sha256(json.dumps(fixture_contract,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
    "environment_contract":environment_contract,
    "environment_contract_digest":"sha256:"+hashlib.sha256(json.dumps(environment_contract,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
    "truth_scope":"BENCHMARK_ONLY","production_truth_eligible":False,"isolated_execution":True,"incumbent_control_group":True,
    "candidate_owner":"agent-foundry","logician_challenge":sc.get("logician_challenge"),"technology_watch_revalidation_required":True,
    "technology_watch_state":technology_watch.get("state"),"independent_oracle_required":True,"direct_agent_mutation":False,
    "self_scoring_authority":False,"self_promotion":False,"shadow_required":True,"pilot_required_for_material_change":True})
 return {"schema":"chacha.dev/agent-benchmark-campaign/v1","scheduled_action_count":len(index.get("scheduled_actions") or []),"contract_count":len(contracts),"contracts":contracts,"technology_watch":technology_watch,"benchmark_fixture_is_production_truth":False,"direct_agent_mutation":False,"agent_self_scoring_authority":False,"architecture_council_final_authority":True,"automatic_external_spend_eur":0}
def _independently_verified(x:dict)->bool:
 return (x.get("verification")=="VERIFIED" and bool(x.get("evidence_refs")) and
         str(x.get("verifier") or "") not in {"",str(x.get("agent_id") or ""),str(x.get("subject_id") or "")})
def compare(inc:dict,cand:dict,policy:dict|None=None)->dict:
 policy=policy or {};req=policy.get("result_requirements") or {};cmp=policy.get("comparison") or {}
 hard=[]
 if not _independently_verified(inc) or not _independently_verified(cand):hard.append("INDEPENDENT_VERIFICATION_REQUIRED")
 if inc.get("benchmark_id")!=cand.get("benchmark_id"):hard.append("BENCHMARK_ID_MISMATCH")
 if req.get("same_fixture_contract",True) and inc.get("fixture_contract_digest")!=cand.get("fixture_contract_digest"):hard.append("FIXTURE_CONTRACT_MISMATCH")
 if req.get("same_environment_contract",True) and inc.get("environment_contract_digest")!=cand.get("environment_contract_digest"):hard.append("ENVIRONMENT_CONTRACT_MISMATCH")
 if req.get("distinct_candidate_revision",True) and str(inc.get("revision") or "")==str(cand.get("revision") or ""):hard.append("DISTINCT_REVISIONS_REQUIRED")
 if cand.get("permission_expansion") is True:hard.append("PERMISSION_EXPANSION")
 if cand.get("guardian_preserved") is not True:hard.append("GUARDIAN_REGRESSION")
 if cand.get("sentinel_preserved") is not True:hard.append("SENTINEL_REGRESSION")
 if float(cand.get("automatic_external_spend_eur") or 0)>0:hard.append("EXTERNAL_SPEND")
 im=inc.get("metrics") or {};cm=cand.get("metrics") or {};dims=sorted(set(im)&set(cm))
 delta={d:round(float(cm[d])-float(im[d]),3) for d in dims if isinstance(im[d],(int,float)) and isinstance(cm[d],(int,float))}
 max_reg=float(cmp.get("maximum_dimension_regression",2.0))
 regress=[d for d,v in delta.items() if v < -max_reg]
 if regress:hard.append("MATERIAL_DIMENSION_REGRESSION")
 avg=round(sum(delta.values())/len(delta),3) if delta else None
 min_dims=int(cmp.get("minimum_measured_dimensions",2))
 min_gain=float(cmp.get("minimum_average_gain",3.0))
 if hard:decision="REJECT_CANDIDATE"
 elif len(delta)<min_dims:decision="SHADOW_CONTINUE"
 elif avg is not None and avg>=min_gain:decision="PILOT_ELIGIBLE"
 else:decision="KEEP_INCUMBENT"
 return {"status":"PASS" if not hard else "BLOCKED","delta":delta,"average_gain":avg,
   "measurable_gain":bool(avg is not None and avg>=min_gain),"material_regression":bool(regress),
   "hard_gate_failures":hard,"decision":decision,"promotion_eligible":decision=="PILOT_ELIGIBLE",
   "latest_version_priority":False,"direct_candidate_promotion":False,
   "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
def main():
 ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True);c=sub.add_parser("compile");c.add_argument("--index",type=Path,required=True);c.add_argument("--fleet",type=Path,required=True);c.add_argument("--policy",type=Path,required=True);c.add_argument("--technology-watch-status",type=Path,required=True);c.add_argument("--output",type=Path,required=True);q=sub.add_parser("compare");q.add_argument("--incumbent",type=Path,required=True);q.add_argument("--candidate",type=Path,required=True);q.add_argument("--policy",type=Path,required=True);q.add_argument("--output",type=Path,required=True);a=ap.parse_args()
 if a.cmd=="compile":x=campaign(load(a.index),load(a.fleet),load(a.policy),load(a.technology_watch_status))
 else:x=compare(load(a.incumbent),load(a.candidate),load(a.policy) if hasattr(a,"policy") and a.policy else {})
 save(a.output,x);print(json.dumps(x,ensure_ascii=False));print("CHACHA_DEV_V650_AGENT_BENCHMARK_HARNESS=PASS")
if __name__=="__main__":main()
