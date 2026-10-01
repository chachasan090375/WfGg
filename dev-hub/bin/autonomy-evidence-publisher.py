#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,hashlib,json,os,re
from pathlib import Path
from typing import Any
SAFE_ID=re.compile(r'^[a-z0-9][a-z0-9._-]{1,80}$')

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED:'+str(p))
    return x

def digest(p:Path)->str:return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def iso()->str:return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
def atomic(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n');os.replace(tmp,p)

def build(policy:dict[str,Any],spec:dict[str,Any])->dict[str,Any]:
    if policy.get('schema')!='chacha.dev/autonomy-evidence-publisher-policy/v1':raise ValueError('POLICY_SCHEMA_MISMATCH')
    eid=str(spec.get('evidence_id') or '');src=Path(str(spec.get('source_path') or ''));expected=str(spec.get('expected_status') or '')
    if not SAFE_ID.fullmatch(eid):raise ValueError('EVIDENCE_ID_INVALID')
    if not src.is_file():raise ValueError('SOURCE_NOT_FILE')
    source=load(src)
    if spec.get('expected_schema') and source.get('schema')!=spec.get('expected_schema'):raise ValueError('SOURCE_SCHEMA_MISMATCH')
    if not expected or str(source.get('status') or '')!=expected:raise ValueError('SOURCE_STATUS_MISMATCH')
    revision=None
    if spec.get('revision_field'):revision=source.get(str(spec['revision_field']))
    return {'schema':'chacha.dev/autonomy-evidence/v1','status':'PASS','evidence_id':eid,'source_path':str(src.resolve()),'source_digest':digest(src),'source_schema':source.get('schema'),'source_status':source.get('status'),'platform_revision':revision,'published_at':iso(),'execution_authority':False,'production_mutation':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--spec',type=Path,required=True);ap.add_argument('--output',type=Path);ap.add_argument('--apply',action='store_true');a=ap.parse_args()
    try:
        pol=load(a.policy);spec=load(a.spec);out=build(pol,spec)
        target=(Path(str(pol['runtime_root']))/(out['evidence_id']+'.json')).resolve()
        root=Path(str(pol['runtime_root'])).resolve()
        if root not in target.parents:raise ValueError('TARGET_OUTSIDE_RUNTIME_ROOT')
        dest=target if a.apply else (a.output or Path('/tmp/autonomy-evidence-preview.json'))
        atomic(dest,out);print('CHACHA_DEV_AUTONOMY_EVIDENCE_PUBLISHER=PASS');print('APPLIED='+str(a.apply).lower());print('TARGET='+str(target));return 0
    except Exception as e:print('CHACHA_DEV_AUTONOMY_EVIDENCE_PUBLISHER=BLOCK');print('REASON='+str(e));return 20
if __name__=='__main__':raise SystemExit(main())
