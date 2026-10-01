#!/usr/bin/env python3
from __future__ import annotations
import copy,datetime,json
from pathlib import Path
from typing import Any

def load(path:Path)->dict[str,Any]:
    try:
        x=json.loads(path.read_text(encoding='utf-8'))
        return x if isinstance(x,dict) else {}
    except Exception:return {}

def iso()->str:return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
def dotted(obj:dict[str,Any],field:str):
    cur:Any=obj
    for part in str(field).split('.'):
        if not isinstance(cur,dict) or part not in cur:return None
        cur=cur[part]
    return cur

def stage_ok(stage:dict[str,Any],release_root:Path,runtime_root:Path)->bool:
    for rel in stage.get('required_release_paths') or []:
        if not (release_root/str(rel)).is_file():return False
    spec=stage.get('required_runtime_json')
    if isinstance(spec,dict):
        x=load(runtime_root/str(spec.get('path') or ''))
        if dotted(x,str(spec.get('field') or ''))!=spec.get('equals'):return False
        rev_field=str(spec.get('release_revision_field') or '')
        if rev_field:
            rev_path=release_root/'.revision'
            if not rev_path.is_file():return False
            expected=rev_path.read_text(encoding='utf-8').strip()
            if not expected or str(dotted(x,rev_field) or '')!=expected:return False
    return True

def reassess(roadmap:dict[str,Any],policy:dict[str,Any],release_root:Path,runtime_root:Path)->dict[str,Any]:
    out=copy.deepcopy(roadmap);rules=policy.get('rules') if isinstance(policy.get('rules'),dict) else {}
    for row in out.get('gaps') or []:
        gid=str(row.get('id') or '');rule=rules.get(gid) if isinstance(rules.get(gid),dict) else {}
        source_progress=int(row.get('progress') or 0);applied=[]
        for stage in rule.get('stages') or []:
            if not isinstance(stage,dict) or not stage_ok(stage,release_root,runtime_root):continue
            target=int(stage.get('target_progress') or 0)
            if target>=int(row.get('progress') or 0):
                row['progress']=target;row['status']=str(stage.get('status') or row.get('status') or 'ORANGE');row['state']=str(stage.get('state') or row.get('state') or '')
                applied.append({'target_progress':target,'state':row['state']})
        row['reassessment']={'source_progress':source_progress,'live_progress':int(row.get('progress') or 0),'applied_stages':applied}
    vals=[int(x.get('progress') or 0) for x in out.get('gaps') or []]
    counts={k:sum(1 for x in out.get('gaps') or [] if str(x.get('status') or '').upper()==k) for k in ('GREEN','ORANGE','RED')}
    out.update(updated_at=iso(),score_percent=round(sum(vals)/len(vals)) if vals else 0,counts=counts,reassessment_source='LIVE_POLICY_EVIDENCE')
    return out
