#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
from typing import Any
SHA=re.compile(r'^[0-9a-f]{40}$')

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def candidates(root:Path)->list[dict[str,Any]]:
    out=[]
    for p in sorted(root.glob('*.json')):
        try:x=load(p)
        except Exception:continue
        if x.get('schema')=='chacha.dev/roadmap-train-candidate/v1':out.append({**x,'manifest_path':str(p)})
    return out

def plan(policy:dict[str,Any],roadmap:dict[str,Any],rows:list[dict[str,Any]],base:str)->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/roadmap-release-train-planner-policy/v1':raise ValueError('POLICY_SCHEMA_MISMATCH')
    if roadmap.get('schema')!='chacha.dev/autonomy-gap-roadmap/v1':raise ValueError('ROADMAP_SCHEMA_MISMATCH')
    if not SHA.fullmatch(base):raise ValueError('EXACT_BASE_REQUIRED')
    gaps={str(g.get('id')):g for g in roadmap.get('gaps') or [] if isinstance(g,dict)}
    eligible=set(policy.get('eligible_gap_statuses') or []);prio=policy.get('status_priority') or {}
    valid=[];skipped=[]
    for c in rows:
        g=gaps.get(str(c.get('gap_id') or ''))
        reason=None
        if not g or g.get('status') not in eligible:reason='GAP_NOT_ELIGIBLE'
        elif c.get('base_revision')!=base:reason='BASELINE_MISMATCH'
        elif c.get('evidence_status')!=policy.get('candidate_evidence_status_required'):reason='EVIDENCE_NOT_PASS'
        elif not SHA.fullmatch(str(c.get('candidate_revision') or '')):reason='CANDIDATE_SHA_INVALID'
        elif not c.get('changed_files'):reason='EMPTY_CHANGESET'
        if reason:skipped.append({'chantier_id':c.get('chantier_id'),'reason':reason});continue
        valid.append((int(prio.get(g.get('status'),9)),int(g.get('progress') or 0),str(c.get('chantier_id')),c,g))
    valid.sort(key=lambda x:(x[0],x[1],x[2]));used=set();selected=[]
    for _,_,_,c,g in valid:
        overlap=sorted(used.intersection(set(c.get('changed_files') or [])))
        if overlap:skipped.append({'chantier_id':c.get('chantier_id'),'reason':'FILE_OVERLAP','overlap':overlap});continue
        if len(selected)>=int(policy.get('maximum_chantiers_per_train') or 6):skipped.append({'chantier_id':c.get('chantier_id'),'reason':'TRAIN_CAPACITY'});continue
        selected.append({'chantier_id':c.get('chantier_id'),'gap_id':c.get('gap_id'),'gap_status':g.get('status'),'gap_progress':g.get('progress'),'candidate_revision':c.get('candidate_revision'),'changed_files':sorted(c.get('changed_files') or []),'manifest_path':c.get('manifest_path')});used.update(c.get('changed_files') or [])
    return {'schema':'chacha.dev/roadmap-release-train-plan/v1','status':'PASS' if selected else 'HOLD','base_revision':base,'selected':selected,'skipped':skipped,'file_overlap_free':True,'freeze_authorized':False,'compose_authorized':False,'promotion_authorized':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--roadmap',type=Path,required=True);ap.add_argument('--candidates-dir',type=Path,required=True);ap.add_argument('--base-revision',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    try:
        out=plan(load(a.policy),load(a.roadmap),candidates(a.candidates_dir),a.base_revision);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('CHACHA_DEV_ROADMAP_RELEASE_TRAIN_PLANNER='+out['status']);print('SELECTED='+str(len(out['selected'])));print('PROMOTION_AUTHORIZED=NO');return 0 if out['status']=='PASS' else 10
    except Exception as e:print('CHACHA_DEV_ROADMAP_RELEASE_TRAIN_PLANNER=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
