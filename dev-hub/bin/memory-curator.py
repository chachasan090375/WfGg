from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any

TRUST_RANK={"TRUSTED":4,"PROVISIONAL":3,"DEGRADED":2,"CONTRADICTED":1,"SUSPENDED":0}

def load(path:Path)->dict[str,Any]:
    obj=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj,dict):raise ValueError("JSON_OBJECT_REQUIRED")
    return obj

def rank(row:dict[str,Any])->tuple[int,float,int,str]:
    return (TRUST_RANK.get(str(row.get("trust_state") or ""),-1),float(row.get("confidence") or 0),int(row.get("evidence_count") or 0),str(row.get("observed_at") or ""))

def curate(policy:dict[str,Any],batch:dict[str,Any])->dict[str,Any]:
    if policy.get("schema")!="chacha.dev/cognitive-memory-fabric-policy/v1":raise ValueError("POLICY_SCHEMA")
    if batch.get("schema")!="chacha.dev/cognitive-memory-curation-batch/v1":raise ValueError("BATCH_SCHEMA")
    rows=[x for x in batch.get("records") or [] if isinstance(x,dict)]
    winners:dict[str,dict[str,Any]]={};decisions=[]
    for row in rows:
        mid=str(row.get("memory_id") or "");key=str(row.get("memory_key") or "")
        if not mid or not key:
            decisions.append({"memory_id":mid or None,"decision":"QUARANTINE","reason":"IDENTITY_MISSING"});continue
        privacy=row.get("privacy") if isinstance(row.get("privacy"),dict) else {}
        if privacy.get("contains_secret") or privacy.get("contains_raw_user_content"):
            decisions.append({"memory_id":mid,"decision":"QUARANTINE","reason":"PRIVACY_FORBIDDEN"});continue
        state=str(row.get("trust_state") or "")
        if state in {"CONTRADICTED","SUSPENDED"}:
            decisions.append({"memory_id":mid,"decision":"QUARANTINE","reason":"TRUST_STATE_"+state});continue
        prev=winners.get(key)
        if prev is None or rank(row)>rank(prev):
            if prev is not None:decisions.append({"memory_id":prev["memory_id"],"decision":"DROP_DUPLICATE_REFERENCE","reason":"SUPERSEDED_BY_HIGHER_CONFIDENCE"})
            winners[key]=row
        else:decisions.append({"memory_id":mid,"decision":"DROP_DUPLICATE_REFERENCE","reason":"LOWER_CONFIDENCE_DUPLICATE"})
    for key,row in winners.items():
        anti=bool(row.get("anti_pattern"));state=str(row.get("trust_state") or "")
        decision="RETAIN_HOT" if state=="TRUSTED" else "RETAIN_PROVISIONAL"
        if anti and policy.get("curation",{}).get("retain_failed_patterns_as_anti_patterns"):decision="RETAIN_ANTI_PATTERN"
        decisions.append({"memory_id":row["memory_id"],"memory_key":key,"decision":decision,"archive_long_term":state=="TRUSTED" or anti})
    return {
      "schema":"chacha.dev/cognitive-memory-curation-result/v1","status":"PASS","input_count":len(rows),
      "decisions":decisions,"hard_delete_performed":False,"execution_authority":False,"production_mutation":False,
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--batch",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=curate(load(a.policy),load(a.batch));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print("CHACHA_DEV_MEMORY_CURATOR=PASS");print("HARD_DELETE=NO");return 0
if __name__=="__main__":raise SystemExit(main())
