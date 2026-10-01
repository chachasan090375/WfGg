#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,hashlib,json,subprocess
from pathlib import Path
from typing import Any
POLICY_SCHEMA="chacha.dev/foundry-pilot-change-set-policy/v1"
PILOT_SCHEMA="chacha.dev/platform-component-comparative-pilot-result/v1"
EVIDENCE_SCHEMA="chacha.dev/golden-path-artifact-evidence/v1"

def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return value

def run(repo:Path,*args:str)->str:
    p=subprocess.run(["git","-C",str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    if p.returncode: raise ValueError("GIT_FAILED:"+" ".join(args)+":"+p.stderr[-500:])
    return p.stdout.strip()

def digest_obj(value:Any)->str:
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def iso()->str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")

def validate(pilot:dict[str,Any],policy:dict[str,Any])->None:
    if policy.get("schema")!=POLICY_SCHEMA: raise ValueError("POLICY_SCHEMA_MISMATCH")
    if pilot.get("schema")!=PILOT_SCHEMA: raise ValueError("PILOT_SCHEMA_MISMATCH")
    req=policy.get("requirements") or {}
    if pilot.get("status")!=req.get("pilot_status"): raise ValueError("PILOT_NOT_PASS")
    if pilot.get("pipeline_status")!=req.get("pipeline_status"): raise ValueError("PILOT_PIPELINE_NOT_HOLD_PASS")
    if pilot.get("council_review_technical_pass") is not True: raise ValueError("COUNCIL_TECHNICAL_REVIEW_NOT_PASS")
    comp=pilot.get("comparison") if isinstance(pilot.get("comparison"),dict) else {}
    if comp.get("candidate_technically_admissible_for_council_review") is not True: raise ValueError("CANDIDATE_NOT_TECHNICALLY_ADMISSIBLE")
    if pilot.get("human_explicit_promotion_approval_present") is not False: raise ValueError("HUMAN_PROMOTION_APPROVAL_MUST_BE_ABSENT")
    if pilot.get("production_change_authorized") is not False: raise ValueError("PRODUCTION_CHANGE_ALREADY_AUTHORIZED")
    if pilot.get("promotion_authorized") is not False: raise ValueError("PROMOTION_ALREADY_AUTHORIZED")
    if float(pilot.get("automatic_external_spend_eur") or 0)!=0: raise ValueError("NONZERO_EXTERNAL_SPEND")

def build(repo:Path,pilot:dict[str,Any],policy:dict[str,Any],pilot_path:Path)->dict[str,Any]:
    validate(pilot,policy)
    cand=str(pilot.get("candidate_revision") or "");inc=str(pilot.get("incumbent_revision") or "")
    if not cand or not inc: raise ValueError("EXACT_REVISIONS_REQUIRED")
    if run(repo,"cat-file","-t",cand)!="commit" or run(repo,"cat-file","-t",inc)!="commit": raise ValueError("REVISION_NOT_COMMIT")
    files=[x for x in run(repo,"diff","--name-only",inc,cand).splitlines() if x]
    if not files: raise ValueError("EMPTY_CHANGE_SET")
    tree=run(repo,"rev-parse",cand+"^{tree}")
    details={"state":policy.get("output_state"),"workspace_commit":cand,"workspace_tree":tree,"incumbent_revision":inc,
      "files":files,"component_id":pilot.get("component_id"),"dispatch_id":pilot.get("dispatch_id"),"pilot_run_id":pilot.get("run_id"),
      "pilot_result_path":str(pilot_path.resolve()),"pilot_result_digest":"sha256:"+hashlib.sha256(pilot_path.read_bytes()).hexdigest(),
      "council_technical_review_pass":True,"technical_admissibility":True,"rollback":{"strategy":"git-revert-or-reset-to-incumbent","target_revision":inc},
      "production_change_authorized":False,"promotion_authorized":False,"human_promotion_approval_present":False,
      "direct_component_mutation":False,"automatic_external_spend_eur":0}
    out={"schema":EVIDENCE_SCHEMA,"artifact_id":"change-set","status":"PASS","observed_at":iso(),"details":details}
    out["evidence_digest"]=digest_obj(out);return out

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repository",type=Path,required=True);ap.add_argument("--pilot-result",type=Path,required=True)
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    try:
        out=build(a.repository.resolve(),load(a.pilot_result),load(a.policy),a.pilot_result)
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("FOUNDRY_PILOT_CHANGE_SET=PASS");print("STATE="+str(out["details"]["state"]));print("FILES="+str(len(out["details"]["files"])))
        print("PRODUCTION_CHANGE_AUTHORIZED=NO");print("PROMOTION_AUTHORIZED=NO");print("AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
    except Exception as exc:
        out={"schema":"chacha.dev/foundry-pilot-change-set-error/v1","status":"BLOCK","reason":str(exc),"production_change_authorized":False,"promotion_authorized":False,"automatic_external_spend_eur":0}
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
        print("FOUNDRY_PILOT_CHANGE_SET=BLOCK");print("REASON="+str(exc));return 20

if __name__=="__main__": raise SystemExit(main())
