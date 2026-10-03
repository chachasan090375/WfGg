from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
from typing import Any
HEX=re.compile(r'^[a-f0-9]{64}$')

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED')
    return x

def memory_type(item:dict[str,Any])->str:
    kind=str(item.get('subject_kind') or '').lower();sig=str(item.get('signal_key') or '').lower()
    if kind in {'architecture','branch','capability'}:return 'procedural'
    if sig.startswith('change:') or sig.startswith('incident:'):return 'episodic'
    return 'semantic'

def bootstrap(snapshot:dict[str,Any])->dict[str,Any]:
    if snapshot.get('schema')!='chacha.dev/central-memory-assimilation/v1':raise ValueError('SNAPSHOT_SCHEMA')
    records=[]
    for item in snapshot.get('items') or []:
        if not isinstance(item,dict):continue
        key=str(item.get('item_key') or '');dig=str(item.get('evidence_digest') or '')
        if not key or not HEX.fullmatch(dig):continue
        subject=str(item.get('subject_id') or 'central');kind=str(item.get('subject_kind') or '')
        namespace=('agent:'+subject) if kind=='agent' else 'central'
        records.append({
          'schema':'chacha.dev/historical-memory-record/v1','memory_id':'bootstrap:'+key,'memory_key':key,
          'namespace':namespace,'memory_type':memory_type(item),'trust_state':str(item.get('state') or 'PROVISIONAL'),
          'evidence_count':int(item.get('evidence_count') or 0),'confidence':float(item.get('confidence') or 0),
          'content_digest':'sha256:'+dig,'observed_at':item.get('latest_observed_at'),'source_snapshot_digest':snapshot.get('snapshot_digest'),
          'raw_user_content':False,'secret_material':False
        })
    raw=json.dumps(records,sort_keys=True,separators=(',',':')).encode()
    return {'schema':'chacha.dev/historical-memory-bootstrap/v1','status':'PASS','source_schema':snapshot.get('schema'),
      'source_item_count':len(snapshot.get('items') or []),'record_count':len(records),'records':records,
      'bootstrap_digest':'sha256:'+hashlib.sha256(raw).hexdigest(),'writes_performed':False,'production_mutation':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--snapshot',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=bootstrap(load(a.snapshot));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+"\n",encoding='utf-8');print('CHACHA_DEV_HISTORICAL_MEMORY_BOOTSTRAP=PASS');print('WRITES_PERFORMED=NO');return 0
if __name__=='__main__':raise SystemExit(main())
