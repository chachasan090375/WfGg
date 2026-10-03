from __future__ import annotations
import argparse,json,os,subprocess,sys
from pathlib import Path
from typing import Any
from cognitive_memory_trigger import EVENT_TRIGGERS

DEFAULT_POLICY=Path('/opt/chacha-dev/platform/current/dev-hub/config/cognitive-memory-fabric.v1.json')
DEFAULT_RUNNER=Path('/opt/chacha-dev/platform/current/dev-hub/bin/cognitive-memory-tiering.py')
DEFAULT_PENDING=Path('/opt/chacha-dev/runtime/knowledge/cognitive-memory-tiering-events/pending')
DEFAULT_PROCESSED=Path('/opt/chacha-dev/runtime/knowledge/cognitive-memory-tiering-events/processed')

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('EVENT_JSON_OBJECT_REQUIRED')
    return x

def drain(*,policy:Path,runner:Path,pending:Path,processed:Path,extra:list[str]|None=None)->dict[str,Any]:
    pending.mkdir(parents=True,exist_ok=True);processed.mkdir(parents=True,exist_ok=True)
    rows=[]
    for path in sorted(pending.glob('*.json')):
        event=load(path)
        if event.get('schema')!='chacha.dev/cognitive-memory-tiering-event/v1':raise RuntimeError('EVENT_SCHEMA_INVALID:'+path.name)
        trigger=str(event.get('trigger') or '')
        if trigger not in EVENT_TRIGGERS:raise RuntimeError('EVENT_TRIGGER_INVALID:'+trigger)
        cmd=[sys.executable,str(runner),'--policy',str(policy),'--trigger',trigger,'--shadow-execute']+list(extra or [])
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=180)
        if p.returncode!=0:raise RuntimeError('TIERING_EVENT_FAILED:'+path.name+':'+(p.stderr or p.stdout)[-400:])
        target=processed/path.name
        if target.exists():path.unlink()
        else:os.replace(path,target)
        rows.append({'event_id':event.get('event_id'),'trigger':trigger,'result':json.loads(p.stdout)})
    return {'schema':'chacha.dev/cognitive-memory-tiering-event-drain/v1','status':'PASS','processed':len(rows),'results':rows,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,default=DEFAULT_POLICY);ap.add_argument('--runner',type=Path,default=DEFAULT_RUNNER);ap.add_argument('--pending',type=Path,default=DEFAULT_PENDING);ap.add_argument('--processed',type=Path,default=DEFAULT_PROCESSED);ap.add_argument('--agent-root',type=Path);ap.add_argument('--ledger',type=Path);ap.add_argument('--publish-adapter',type=Path);ap.add_argument('--readback-adapter',type=Path);a=ap.parse_args()
    extra=[]
    for flag,val in (('--agent-root',a.agent_root),('--ledger',a.ledger),('--publish-adapter',a.publish_adapter),('--readback-adapter',a.readback_adapter)):
        if val is not None:extra += [flag,str(val)]
    print(json.dumps(drain(policy=a.policy,runner=a.runner,pending=a.pending,processed=a.processed,extra=extra),ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
