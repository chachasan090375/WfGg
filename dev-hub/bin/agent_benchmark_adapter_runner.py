#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
from typing import Any
import agent_benchmark_adapters as adapters
import agent_benchmark_oracles as oracles
import technology_watch_runtime as tw

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def digest(x:Any)->str:return "sha256:"+hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def run(agent_id:str,repo_root:Path,revision:str,config:dict[str,Any])->dict[str,Any]:
    started=time.perf_counter();raw=adapters.execute(agent_id,repo_root);oracle=oracles.verify(agent_id,raw);elapsed=round((time.perf_counter()-started)*1000,3)
    watch=tw.snapshot_status(repo_root)
    spec=(config.get("supported_agents") or {}).get(agent_id) or {}
    evidence={
      "schema":"chacha.dev/agent-benchmark-raw-evidence/v1","agent_id":agent_id,"adapter":spec.get("adapter"),
      "revision":revision,"truth_scope":"BENCHMARK_ONLY","production_truth_eligible":False,
      "verification":"BENCHMARK_VERIFIED","verifier":oracle["verifier"],"producer":"agent-benchmark-adapter:"+agent_id,
      "oracle_complete":oracle["oracle_complete"],"case_count":oracle["case_count"],"passed_case_count":oracle["passed_case_count"],
      "dimensions":oracle["dimensions"],"cases":oracle["cases"],"technology_watch":watch,
      "technology_watch_revalidation_required":True,"guardian_preserved":True,"sentinel_preserved":True,
      "canonical_observation_bus_writes":False,"direct_agent_mutation":False,"candidate_materialization":False,
      "self_promotion":False,"duration_ms":elapsed,"automatic_external_spend_eur":0
    }
    evidence["evidence_digest"]=digest({k:v for k,v in evidence.items() if k!="evidence_digest"})
    evidence["evidence_refs"]=["benchmark-digest:"+evidence["evidence_digest"]]+["benchmark-case:"+agent_id+":"+str(c["case_id"]) for c in oracle["cases"]]
    return evidence
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--agent-id",required=True);ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--revision",required=True);ap.add_argument("--config",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    cfg=load(a.config)
    if a.agent_id not in (cfg.get("supported_agents") or {}):raise SystemExit("NO_EXECUTABLE_ADAPTER:"+a.agent_id)
    out=run(a.agent_id,a.repo_root.resolve(),a.revision,cfg);save(a.output,out)
    print("CHACHA_DEV_V651_EXECUTABLE_ADAPTER=PASS");print("AGENT_ID="+a.agent_id)
    print("CASE_COUNT="+str(out["case_count"]));print("PASSED_CASE_COUNT="+str(out["passed_case_count"]))
    print("CHACHA_DEV_V651_PRODUCTION_TRUTH=NO");print("CHACHA_DEV_V651_CANONICAL_BUS_WRITE=NO");print("CHACHA_DEV_V651_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
if __name__=="__main__":raise SystemExit(main())
