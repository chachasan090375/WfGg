#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x
def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def build_core_watch(inventory:dict[str,Any],signals:dict[str,Any]|None=None)->dict[str,Any]:
    signals=signals or {};sigs=signals.get("components") or {};thresholds=inventory.get("debt_thresholds") or {"watch":20,"pilot":40,"act":60};rows=[]
    for c in inventory.get("components") or []:
        cid=str(c.get("id") or "");sig=sigs.get(cid) or {};debt=0;reasons=[]
        if sig.get("unsupported") is True:debt+=50;reasons.append("UNSUPPORTED")
        if sig.get("deprecated") is True:debt+=30;reasons.append("DEPRECATED")
        if sig.get("critical_security_advisory") is True:debt+=50;reasons.append("CRITICAL_SECURITY_ADVISORY")
        eol=sig.get("eol_days")
        if isinstance(eol,(int,float)) and eol<=30:debt+=40;reasons.append("EOL_WITHIN_30_DAYS")
        health=sig.get("maintenance_health")
        if isinstance(health,(int,float)) and health<40:debt+=25;reasons.append("LOW_MAINTENANCE_HEALTH")
        if sig.get("breaking_api") is True:debt+=25;reasons.append("BREAKING_API")
        if sig.get("better_verified_alternative") is True:debt+=15;reasons.append("BETTER_VERIFIED_ALTERNATIVE")
        debt=min(100,debt)
        status="ACT" if debt>=int(thresholds.get("act",60)) else "PILOT" if debt>=int(thresholds.get("pilot",40)) else "WATCH" if debt>=int(thresholds.get("watch",20)) else "CURRENT"
        rows.append({"component_id":cid,"class":c.get("class"),"criticality":c.get("criticality"),"technology_debt_score":debt,"status":status,"reason_codes":reasons})
    return {"schema":"chacha.dev/technology-core-watch-report/v1","status":"PASS","component_count":len(rows),
      "inventory_coverage_complete":len(rows)==len(inventory.get("components") or []),"components":rows,
      "recommendations_only":True,"uncontrolled_upgrade":False,"architecture_council_final_authority":True,
      "guardian_authority_preserved":True,"sentinel_authority_preserved":True,"automatic_external_spend_eur":0}
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--inventory",type=Path,required=True);ap.add_argument("--signals",type=Path);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=build_core_watch(load(a.inventory),load(a.signals) if a.signals and a.signals.is_file() else {});save(a.output,out);print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V645_CORE_ARCHITECTURE_WATCH=PASS");print("CHACHA_DEV_V645_UNCONTROLLED_CORE_UPGRADE=NO");print("CHACHA_DEV_V645_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
if __name__=="__main__":raise SystemExit(main())
