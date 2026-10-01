#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,hashlib,json,os
from pathlib import Path
from typing import Any
POLICY_SCHEMA="chacha.dev/roadmap-live-score-reconciler-policy/v1"
ROADMAP_SCHEMA="chacha.dev/autonomy-gap-roadmap/v1"
UPDATE_SCHEMA="chacha.dev/roadmap-gap-update-set/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def sha(path:Path)->str:return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def verify_refs(refs:list[dict[str,Any]])->None:
    if not refs:raise ValueError("EVIDENCE_REQUIRED")
    for r in refs:
        p=Path(str(r.get("path") or ""))
        if not p.is_file():raise ValueError("EVIDENCE_MISSING:"+str(p))
        if sha(p)!=str(r.get("digest") or ""):raise ValueError("EVIDENCE_DIGEST_MISMATCH:"+str(p))
def reconcile(policy:dict[str,Any],roadmap:dict[str,Any],updates:dict[str,Any])->dict[str,Any]:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("POLICY_SCHEMA_MISMATCH")
    if roadmap.get("schema")!=ROADMAP_SCHEMA:raise ValueError("ROADMAP_SCHEMA_MISMATCH")
    if updates.get("schema")!=UPDATE_SCHEMA:raise ValueError("UPDATE_SCHEMA_MISMATCH")
    allowed=set(policy.get("allowed_statuses") or [])
    gaps={str(g.get("id")):dict(g) for g in roadmap.get("gaps") or [] if isinstance(g,dict)}
    applied=[]
    for u in updates.get("updates") or []:
        gid=str(u.get("gap_id") or "")
        if gid not in gaps:raise ValueError("UNKNOWN_GAP:"+gid)
        verify_refs(list(u.get("evidence_refs") or []))
        progress=int(u.get("progress"));status=str(u.get("status") or "")
        if not 0<=progress<=100:raise ValueError("PROGRESS_RANGE")
        if status not in allowed:raise ValueError("STATUS_INVALID")
        row=gaps[gid];row.update({"progress":progress,"status":status,"state":str(u.get("state") or row.get("state") or ""),
                                 "evidence":str(u.get("evidence_summary") or row.get("evidence") or "")})
        gaps[gid]=row;applied.append(gid)
    ordered=[gaps[str(g.get("id"))] for g in roadmap.get("gaps") or []]
    score=round(sum(int(g.get("progress") or 0) for g in ordered)/max(1,len(ordered)))
    counts={s:sum(1 for g in ordered if g.get("status")==s) for s in allowed}
    out=dict(roadmap);out.update({"updated_at":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
        "score_percent":score,"counts":counts,"gaps":ordered,"reconciled_gap_ids":applied,
        "source_roadmap_mutated":False,"production_mutation":False,"automatic_external_spend_eur":0})
    return out

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--roadmap",type=Path,required=True)
    ap.add_argument("--updates",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    try:
        out=reconcile(load(a.policy),load(a.roadmap),load(a.updates));a.output.parent.mkdir(parents=True,exist_ok=True)
        t=a.output.with_suffix(a.output.suffix+".tmp");t.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n");os.replace(t,a.output)
        print("CHACHA_DEV_ROADMAP_LIVE_SCORE_RECONCILER=PASS")
        print("SOURCE_ROADMAP_MUTATED=NO");print("AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
    except Exception as exc:
        print("CHACHA_DEV_ROADMAP_LIVE_SCORE_RECONCILER=BLOCK reason="+str(exc));return 20

if __name__=="__main__":raise SystemExit(main())
