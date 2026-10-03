from __future__ import annotations
import argparse, hashlib, json, os, time
from pathlib import Path
from typing import Any

EVENT_TRIGGERS={
    'MISSION_ACCEPTED_COMPLETE',
    'MEMORY_PROMOTED_TRUSTED',
    'REUSABLE_ARCHITECTURE_CONSOLIDATED',
    'AGENT_SPECIALIST_CORPUS_UPDATED',
}
DEFAULT_PENDING=Path('/opt/chacha-dev/runtime/knowledge/cognitive-memory-tiering-events/pending')

def canon(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))

def emit(trigger:str,source:str,evidence_ref:str,event_root:Path=DEFAULT_PENDING)->dict[str,Any]:
    if trigger not in EVENT_TRIGGERS:raise ValueError('TRIGGER_NOT_ALLOWED')
    if not source or not evidence_ref:raise ValueError('SOURCE_AND_EVIDENCE_REQUIRED')
    identity={'trigger':trigger,'source':source,'evidence_ref':evidence_ref}
    event_id='cmf-event-'+hashlib.sha256(canon(identity).encode()).hexdigest()[:24]
    doc={'schema':'chacha.dev/cognitive-memory-tiering-event/v1','event_id':event_id,
         'trigger':trigger,'source':source,'evidence_ref':evidence_ref,
         'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
         'production_activation_authorized':False,'automatic_external_spend_eur':0}
    event_root.mkdir(parents=True,exist_ok=True)
    path=event_root/(event_id+'.json')
    if path.exists():
        return {'schema':'chacha.dev/cognitive-memory-tiering-event-emission/v1','status':'DEDUPLICATED','event_id':event_id,'path':str(path)}
    tmp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
    tmp.write_text(json.dumps(doc,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    try:os.link(tmp,path)
    except FileExistsError:pass
    finally:tmp.unlink(missing_ok=True)
    return {'schema':'chacha.dev/cognitive-memory-tiering-event-emission/v1','status':'QUEUED','event_id':event_id,'path':str(path)}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--trigger',required=True,choices=sorted(EVENT_TRIGGERS));ap.add_argument('--source',required=True);ap.add_argument('--evidence-ref',required=True);ap.add_argument('--event-root',type=Path,default=DEFAULT_PENDING);a=ap.parse_args()
    print(json.dumps(emit(a.trigger,a.source,a.evidence_ref,a.event_root),ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
