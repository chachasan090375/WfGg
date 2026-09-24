#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x
def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def parse_day(v:str)->datetime:return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc)
def build_challenge(dossier:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    route_map={str(x["id"]):x for x in policy.get("verification_routes") or [] if isinstance(x,dict) and x.get("id")}
    evidence=[x for x in dossier.get("evidence") or [] if isinstance(x,dict)]
    claims=[x for x in dossier.get("claims") or [] if isinstance(x,dict)];paths=[]
    def add(route,claim_id,reason):
        row=route_map.get(route) or {"id":route,"information_gain":50,"cost_rank":2}
        paths.append({"route":route,"claim_id":claim_id,"reason":reason,
          "expected_information_gain":int(row.get("information_gain",50)),"cost_rank":int(row.get("cost_rank",2))})
    for claim in claims:
        cid=str(claim.get("id") or "");rows=[x for x in evidence if str(x.get("claim_id") or "")==cid]
        support=[x for x in rows if str(x.get("stance") or "SUPPORT").upper()!="CONTRADICT"]
        groups={str(x.get("independence_group") or x.get("origin") or x.get("id") or "") for x in support}
        technical={str(x.get("type") or "") for x in support}
        if not (technical & {"executable_reproduction","project_pilot"}):add("EXECUTABLE_REPRODUCTION",cid,"No executable or real-pilot proof currently falsifies the claim.")
        if len(groups)<2:add("INDEPENDENT_CORROBORATION",cid,"Claim lacks at least two independent evidence origins.")
        if len(support)>len(groups):add("SOURCE_INDEPENDENCE_CHECK",cid,"Multiple evidence items share an origin and may create false consensus.")
        add("NEGATIVE_ISSUE_SEARCH",cid,"Search specifically for regressions, failures and counterexamples.")
        add("SECURITY_ADVISORY_SEARCH",cid,"Search security advisories and breaking-change evidence.")
    blast=str(dossier.get("blast_radius") or "medium").lower()
    if blast in {"high","critical"}:
        add("DEPENDENCY_COMPATIBILITY_MATRIX","*","High blast radius requires compatibility falsification.")
        add("RESOURCE_BUDGET_PROBE","*","High blast radius requires measurable runtime/resource comparison.")
        add("ROLLBACK_DRILL","*","Rollback must be demonstrated, not only documented.")
        add("SHADOW_COMPARISON","*","Compare candidate against incumbent without decision authority.")
    try:
        release=parse_day(str(dossier.get("release_date") or ""));asof=parse_day(str(dossier.get("as_of") or datetime.now(timezone.utc).isoformat()))
        if (asof-release).days<14:add("EARLY_RELEASE_REGRESSION_PROBE","*","Exact version is recent and needs targeted regression pressure.")
    except Exception:pass
    unique={(x["route"],x["claim_id"]):x for x in paths}
    ordered=sorted(unique.values(),key=lambda x:(-(x["expected_information_gain"]/max(x["cost_rank"],1)),-x["expected_information_gain"],x["route"],x["claim_id"]))
    return {"schema":"chacha.dev/technology-watch-logician-challenge/v1","owner_role":"logician",
      "decision_authority":"technology-watch-agent","technology_id":dossier.get("technology_id"),"version":dossier.get("version"),
      "falsification_paths":ordered,"adaptive_verification_order":True,"counterexample_search_required":True,
      "current_solution_is_a_candidate":True,"direct_mutation":False,"architecture_council_final_authority":True,
      "automatic_external_spend_eur":0}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--dossier",type=Path,required=True);ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=build_challenge(load(a.dossier),load(a.policy));save(a.output,out);print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V645_LOGICIAN_FALSIFICATION=PASS");print("CHACHA_DEV_V645_LOGICIAN_DECISION_AUTHORITY=NO");print("CHACHA_DEV_V645_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
if __name__=="__main__":raise SystemExit(main())
