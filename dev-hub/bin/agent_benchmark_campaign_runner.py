#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
import agent_benchmark_adapter_runner as runner
import agent_benchmark_evidence_promoter as promoter

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def execute(campaign:dict[str,Any],repo_root:Path,runtime_root:Path,revision:str,cfg:dict[str,Any])->dict[str,Any]:
    supported=set((cfg.get("supported_agents") or {}).keys());results=[]
    raw_root=runtime_root/str((cfg.get("evidence") or {}).get("raw_dir") or "agent-evolution/benchmark-results/raw")
    promoted_root=runtime_root/str((cfg.get("evidence") or {}).get("promoted_dir") or "agent-evolution/benchmark-evidence")
    seen=set()
    for contract in campaign.get("contracts") or []:
        aid=str(contract.get("agent_id") or "")
        if not aid or aid in seen:continue
        seen.add(aid)
        if aid not in supported:
            results.append({"agent_id":aid,"status":"NO_EXECUTABLE_ADAPTER","promoted":False});continue
        raw=runner.run(aid,repo_root,revision,cfg);raw_path=raw_root/(aid+"-"+revision+".json");save(raw_path,raw)
        out_path=promoted_root/aid/(revision+".json")
        prom=promoter.promote(raw,revision,cfg,out_path)
        results.append({"agent_id":aid,"status":prom.get("status"),"promoted":bool(prom.get("promoted")),"raw_path":str(raw_path),"promoted_path":prom.get("path"),"reason_codes":prom.get("reason_codes")})
    return {"schema":"chacha.dev/agent-benchmark-campaign-run/v1","revision":revision,"campaign_contract_count":len(campaign.get("contracts") or []),
      "supported_adapter_count":len(supported),"attempted_supported_count":sum(1 for x in results if x["status"]!="NO_EXECUTABLE_ADAPTER"),
      "promoted_count":sum(1 for x in results if x.get("promoted")),"results":results,
      "benchmark_fixture_is_production_truth":False,"canonical_observation_bus_writes":False,
      "direct_agent_mutation":False,"candidate_materialization":False,"architecture_council_final_authority":True,"automatic_external_spend_eur":0}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--campaign",type=Path,required=True);ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--runtime-root",type=Path,required=True);ap.add_argument("--revision",required=True);ap.add_argument("--config",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=execute(load(a.campaign),a.repo_root.resolve(),a.runtime_root.resolve(),a.revision,load(a.config));save(a.output,out)
    print("CHACHA_DEV_V651_CAMPAIGN_RUNNER=PASS");print("PROMOTED_COUNT="+str(out["promoted_count"]))
    print("CHACHA_DEV_V651_UNSUPPORTED_AGENT_IS_FAILURE=NO");print("CHACHA_DEV_V651_PRODUCTION_TRUTH=NO");print("CHACHA_DEV_V651_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
if __name__=="__main__":raise SystemExit(main())
