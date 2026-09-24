#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

ROUTES={
 "accuracy":["ADVERSARIAL_COUNTEREXAMPLES","INDEPENDENT_ORACLE_CHECK"],
 "coverage":["MISSING_CASE_DISCOVERY","BOUNDARY_CASE_SWEEP"],
 "calibration":["CONFIDENCE_CALIBRATION_CURVE","OVERCONFIDENCE_TRAP"],
 "evidence_quality":["EVIDENCE_PROVENANCE_CHECK","EXECUTABLE_EVIDENCE_CHALLENGE"],
 "robustness":["FAULT_INJECTION","DEPENDENCY_FAILURE_SIMULATION"],
 "efficiency":["RESOURCE_BENCHMARK","LATENCY_COST_COMPARISON"],
 "handoff_quality":["CONTRACT_ROUNDTRIP","CROSS_AGENT_MISINTERPRETATION_TEST"],
 "learning_quality":["NEGATIVE_FEEDBACK_ASSIMILATION","STALE_KNOWLEDGE_REJECTION"],
 "drift_resistance":["DEPENDENCY_VERSION_DRIFT","POLICY_CONTRACT_DRIFT"],
 "authority_discipline":["PERMISSION_BOUNDARY_PROBE","SELF_PROMOTION_ATTEMPT"]
}
def build(agent_id:str,scorecard:dict[str,Any])->dict[str,Any]:
    dims=scorecard.get("dimensions") or {}
    ordered=sorted(((k,float(v)) for k,v in dims.items()),key=lambda x:x[1])
    paths=[]
    for dim,score in ordered:
        for route in ROUTES.get(dim,[]):
            paths.append({"dimension":dim,"route":route,"priority":"HIGH" if score<65 else "MEDIUM","current_score":score})
    paths.extend([
      {"dimension":"architecture","route":"SCOPE_OVERLAP_AND_DUPLICATION_REVIEW","priority":"HIGH","current_score":None},
      {"dimension":"control","route":"INCUMBENT_VS_CANDIDATE_SHADOW_COMPARISON","priority":"HIGH","current_score":None}
    ])
    return {
      "schema":"chacha.dev/agent-evolution-logician-challenge/v1",
      "agent_id":agent_id,
      "owner_role":"logician",
      "decision_authority":False,
      "falsification_paths":paths,
      "direct_agent_mutation":False,
      "automatic_external_spend_eur":0
    }
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--agent-id",required=True);ap.add_argument("--scorecard",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    x=json.loads(a.scorecard.read_text(encoding="utf-8"));out=build(a.agent_id,x)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V646_LOGICIAN_AGENT_FALSIFICATION=PASS")
    print("CHACHA_DEV_V646_LOGICIAN_AGENT_DECISION_AUTHORITY=NO")
    return 0
if __name__=="__main__":raise SystemExit(main())
