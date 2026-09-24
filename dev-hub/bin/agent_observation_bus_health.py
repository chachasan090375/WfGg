#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,tempfile,time,shutil
from pathlib import Path
from typing import Any
import agent_observation_bus as aob
import agent_evolution_controller as aec
def load(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding="utf-8"));assert isinstance(x,dict);return x
def save(p:Path,x:dict[str,Any])->None:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def dg(x):return "sha256:"+hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def rel(root:Path,v:str)->Path:
 p=Path(v);return p if p.is_absolute() else root/p
def inventory(repo:Path):
 regs=[]
 for p in sorted((repo/"dev-hub/projects").glob("*/project-agent-registry.v1.json")):
  try:regs.append(load(p))
  except Exception:pass
 return aec.build_inventory(load(repo/"dev-hub/config/agent-routing.v1.json"),load(repo/"dev-hub/config/seven-agent-final-compromise.v1.json"),regs)
def proj(inv):
 return sorted([{"agent_id":a.get("agent_id"),"scope":a.get("scope"),"project_id":a.get("project_id"),"capabilities":sorted(a.get("capabilities") or [])} for a in inv.get("agents") or []],key=lambda x:(str(x["scope"]),str(x.get("project_id") or ""),str(x["agent_id"])))
def diff(a,b):
 key=lambda x:(x["scope"],str(x.get("project_id") or ""),x["agent_id"]);A={key(x):x for x in a};B={key(x):x for x in b}
 added=[B[k] for k in sorted(B.keys()-A.keys())];removed=[A[k] for k in sorted(A.keys()-B.keys())];changed=[{"before":A[k],"after":B[k]} for k in sorted(A.keys()&B.keys()) if A[k]!=B[k]]
 return {"added":added,"removed":removed,"changed":changed,"material":bool(added or removed or changed)}
def shadow(policy,n=12):
 vals=[]
 with tempfile.TemporaryDirectory(prefix="aob-shadow-") as td:
  rt=Path(td)
  for i in range(n):
   e={"event_id":f"s-{i}","event_type":"BUS_HEALTH_PROBE","source_id":"agent-observation-bus-health","source_surface":"shadow","project_id":"platform-global","revision":"SHADOW","subject_role":"agent-observation-bus","outcome":"OK","verification":"OBSERVED","capabilities":["publish"],"evidence_refs":[f"shadow:{i}"]}
   t=time.perf_counter();aob.publish(e,policy,rt);vals.append((time.perf_counter()-t)*1000)
  vals.sort();return {"status":aob.verify_chain(rt,policy)["status"],"runtime_root_isolated":str(aob.db_path(rt,policy)).startswith(str(rt)),"p95_ms":round(vals[max(0,min(len(vals)-1,int(.95*(len(vals)-1))))],3)}
def assess(repo:Path,root:Path,policy:dict,state:Path,report:Path,deep=False):
 inv=inventory(repo);p=proj(inv);fp=dg(p);old={}
 if state.is_file():
  try:old=load(state)
  except Exception:old={}
 d=diff(old.get("inventory_projection") if isinstance(old.get("inventory_projection"),list) else p,p)
 db=aob.db_path(root,policy);sql={"status":"PASS","event_count":0}
 if db.exists():
  con=sqlite3.connect(db);q=con.execute("pragma quick_check").fetchone();n=con.execute("select count(*) from observations").fetchone()[0];con.close();sql={"status":"PASS" if q and str(q[0]).lower()=="ok" else "FAIL","event_count":int(n)}
 chain=aob.verify_chain(root,policy) if sql["status"]=="PASS" else {"status":"FAIL"}
 sh=shadow(policy,40 if deep else 12);evo=((policy.get("self_health") or {}).get("evolution") or {})
 checks={"runtime_root_relative":(policy.get("storage") or {}).get("runtime_root_relative") is True,"self_verify_forbidden":(policy.get("verification") or {}).get("producer_self_assertion_can_be_verified") is False,"self_mutation_forbidden":evo.get("direct_self_mutation") is False,"self_promotion_forbidden":evo.get("self_promotion") is False,"capability_foundry_owner":evo.get("candidate_owner")=="capability-foundry","shadow_required":evo.get("shadow_required") is True,"pilot_required":evo.get("pilot_required") is True}
 reasons=[]
 if sql["status"]!="PASS":reasons.append("BUS_SQLITE_INTEGRITY")
 if chain.get("status")!="PASS":reasons.append("BUS_HASH_CHAIN")
 if not all(checks.values()):reasons.append("BUS_CONTRACT_DRIFT")
 th=(policy.get("self_health") or {}).get("thresholds") or {}
 if sh["status"]!="PASS" or not sh["runtime_root_isolated"] or sh["p95_ms"]>float(th.get("max_shadow_publish_p95_ms",100)):reasons.append("BUS_SHADOW_REGRESSION")
 if old and d["material"]:reasons.append("AGENT_INVENTORY_OR_CAPABILITY_CHANGED")
 out={"schema":"chacha.dev/agent-observation-bus-health/v1","status":"REASSESS_REQUIRED" if reasons else "PASS","component_id":"agent-observation-bus","integrity":{"sqlite":sql,"hash_chain":chain},"contract_checks":checks,"shadow_benchmark":sh,"inventory":{"agent_count":inv.get("agent_count"),"fingerprint":fp,"delta":d},"candidate_owner":"capability-foundry","technology_watch_revalidation_required":True,"logician_falsification_required":True,"direct_self_mutation":False,"self_promotion":False,"shadow_required":True,"pilot_required":True,"architecture_council_final_authority":True,"automatic_external_spend_eur":0}
 if reasons:
  q=rel(root,str((policy.get("self_health") or {}).get("platform_reassessment_queue") or "platform-evolution/reassessment-queue"));q.mkdir(parents=True,exist_ok=True);rid="bus-"+hashlib.sha256(("|".join(sorted(reasons))+fp).encode()).hexdigest()[:20]
  req={"schema":"chacha.dev/platform-component-reassessment-request/v1","request_id":rid,"component_id":"agent-observation-bus","trigger_reasons":sorted(reasons),"candidate_owner":"capability-foundry","direct_self_mutation":False,"self_promotion":False,"technology_watch_revalidation_required":True,"logician_falsification_required":True,"shadow_required":True,"pilot_required":True,"architecture_council_final_authority":True,"automatic_external_spend_eur":0};rp=q/(rid+".json");save(rp,req);out["reassessment"]={"path":str(rp)}
 save(report,out);save(state,{"inventory_projection":p,"inventory_fingerprint":fp,"status":out["status"]});return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"));ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--mode",choices=["lightweight","deep"],default="lightweight");a=ap.parse_args();p=load(a.policy);cfg=p.get("self_health") or {};r=rel(a.runtime_root,cfg.get("health_report","agent-observation/bus-health-latest.json"));s=rel(a.runtime_root,cfg.get("state","agent-observation/bus-health-state.json"));x=assess(a.repo_root,a.runtime_root,p,s,r,a.mode=="deep");print(json.dumps(x,ensure_ascii=False));print("CHACHA_DEV_V650_BUS_HEALTH="+x["status"]);print("CHACHA_DEV_V650_BUS_SELF_MUTATION=NO");print("CHACHA_DEV_V650_BUS_CANDIDATE_OWNER=CAPABILITY_FOUNDRY")
if __name__=="__main__":main()
