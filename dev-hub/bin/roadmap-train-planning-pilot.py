#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,tempfile
from pathlib import Path

def pilot(planner:Path,policy:Path,roadmap:Path,candidates_dir:Path,base_revision:str)->dict:
    td=Path(tempfile.mkdtemp(prefix='chacha-roadmap-train-planning-pilot-'));out=td/'plan.json'
    cp=subprocess.run(['python3',str(planner),'--policy',str(policy),'--roadmap',str(roadmap),'--candidates-dir',str(candidates_dir),'--base-revision',base_revision,'--output',str(out)],capture_output=True,text=True)
    p=json.loads(out.read_text()) if out.exists() else {};selected=p.get('selected') or []
    ok=cp.returncode==0 and p.get('status')=='PASS' and bool(selected) and p.get('file_overlap_free') is True and p.get('promotion_authorized') is False
    return {'schema':'chacha.dev/roadmap-train-planning-pilot/v1','status':'PASS' if ok else 'BLOCK','selected_count':len(selected),'selected_chantiers':[x.get('chantier_id') for x in selected],'file_overlap_free':p.get('file_overlap_free'),'freeze_performed':False,'composition_performed':False,'promotion_performed':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--planner',type=Path,required=True);ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--roadmap',type=Path,required=True);ap.add_argument('--candidates-dir',type=Path,required=True);ap.add_argument('--base-revision',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();o=pilot(a.planner,a.policy,a.roadmap,a.candidates_dir,a.base_revision);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n');print('CHACHA_DEV_ROADMAP_TRAIN_PLANNING_PILOT='+o['status']);print('PROMOTION_PERFORMED=NO');return 0 if o['status']=='PASS' else 20
if __name__=='__main__':raise SystemExit(main())
