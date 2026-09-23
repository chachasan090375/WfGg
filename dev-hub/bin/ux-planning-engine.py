#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/ux-planning-report/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise SystemExit("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def canon(v:Any)->str:return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v:Any)->str:return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()
def user_facing(pkg:dict[str,Any],domains:set[str])->bool:
    vals={str(pkg.get("domain") or "").lower(),str(pkg.get("kind") or "").lower()}
    vals.update(str(x).lower() for x in pkg.get("capabilities") or [])
    joined=" ".join(vals)
    return any(d in joined for d in domains)
def has_user_language(text:str)->bool:
    return bool(re.search(r"\b(user|utilisateur|client|screen|écran|interface|mobile|web|app|application|dashboard|button|bouton|form|formulaire|parcours|navigation)\b",text,re.I))

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--intent",type=Path,required=True);ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--preplan",type=Path,required=True);ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    intent=load(a.intent);contract=load(a.contract);pre=load(a.preplan);policy=load(a.policy)
    text=str(contract.get("functional_intent") or intent.get("text") or intent.get("objective") or "")
    domains={str(x).lower() for x in policy.get("user_facing_domains") or []}
    packages=[x for x in pre.get("packages") or [] if isinstance(x,dict)]
    visible=[x for x in packages if user_facing(x,domains)]
    audiences=[str(x) for x in contract.get("audiences") or []]
    styles=[str(x) for x in contract.get("styles") or []]
    is_user_facing=bool(visible or audiences or styles or has_user_language(text))
    primary_domains=[str(x) for x in pre.get("primary_domains") or []]
    recommendations=[
      {"id":"PRIMARY_JOB_FIRST","requirement":"Present the user's primary job before secondary controls."},
      {"id":"MINIMIZE_REQUIRED_ACTIONS","requirement":"Minimize mandatory interactions required to reach the primary result."},
      {"id":"PROGRESSIVE_DISCLOSURE","requirement":"Hide advanced complexity until it is needed."},
      {"id":"SENSIBLE_DEFAULTS","requirement":"Use safe defaults that avoid unnecessary decisions."},
      {"id":"STATE_FEEDBACK","requirement":"Every async action defines loading, success, empty and error feedback."},
      {"id":"ERROR_RECOVERY","requirement":"User-visible failures offer a clear recovery path."},
      {"id":"RESPONSIVE","requirement":"Primary tasks remain usable on narrow and touch interfaces."},
      {"id":"ACCESSIBILITY","requirement":"Interaction, focus, contrast and semantics remain accessible."}
    ] if is_user_facing else []
    duplicate_surface_pressure=max(0,len(visible)-1)
    complexity_score=(len(visible)*2)+len(primary_domains)+duplicate_surface_pressure
    th=policy.get("challenge_thresholds") or {}
    if not is_user_facing:
        status="KEEP";reason="NO_USER_FACING_SURFACE_DETECTED"
    elif len(visible)>=int(th.get("replan_user_facing_packages",6)) or len(primary_domains)>=int(th.get("replan_primary_domains",7)):
        status="REPLAN_REQUIRED";reason="UX_FRAGMENTATION_RISK"
    elif len(visible)>=int(th.get("reconsider_user_facing_packages",3)) or duplicate_surface_pressure>=2:
        status="RECONSIDER";reason="UX_SIMPLIFICATION_OPPORTUNITY"
    else:
        status="KEEP";reason="UX_COMPLEXITY_WITHIN_POLICY"
    result={
      "schema":SCHEMA,"version":"1.0.0","contract_id":contract.get("contract_id"),
      "user_facing":is_user_facing,"user_facing_package_count":len(visible),
      "primary_domain_count":len(primary_domains),"experience_complexity_score":complexity_score,
      "audiences":audiences,"styles":styles,
      "user_facing_packages":[{"package_id":x.get("id"),"domain":x.get("domain"),"kind":x.get("kind")} for x in visible],
      "ux_contract":{
        "primary_job_statement":text[:500] if is_user_facing else None,
        "recommendations":recommendations,
        "interaction_principles":["DIRECT","PREDICTABLE","RECOVERABLE","RESPONSIVE","ACCESSIBLE"] if is_user_facing else [],
        "curator_handoff_required":is_user_facing
      },
      "challenge_status":status,"challenge_reason":reason,
      "central_brain_response_required":status!="KEEP",
      "dismissal_without_evidence_forbidden":True,
      "recommended_next_action":"REOPEN_USER_JOURNEY" if status=="REPLAN_REQUIRED" else "SIMPLIFY_AND_ANSWER" if status=="RECONSIDER" else "CONTINUE",
      "architecture_change_requires_technology_watch":True,
      "architecture_council_final_authority":True,
      "direct_mutation":False,"automatic_external_spend_eur":0
    }
    result["report_digest"]=digest(result)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_UX_PLANNING=PASS")
    print("USER_FACING="+("YES" if is_user_facing else "NO"))
    print("UX_CHALLENGE_STATUS="+status)
    print("CURATOR_HANDOFF="+("YES" if is_user_facing else "NO"))
    print("DIRECT_MUTATION=NO")
    return 0

if __name__=="__main__":raise SystemExit(main())
