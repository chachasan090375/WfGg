#!/usr/bin/env python3
from __future__ import annotations
import argparse,fcntl,hashlib,json,os,re,time,uuid
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA='chacha.dev/operator-directive-intake-receipt/v1'

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(path))
    return x

def now_iso()->str:return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())

def norm(text:str)->str:
    return re.sub(r'\s+',' ',str(text or '').strip().casefold())

def text_digest(text:str)->str:
    return 'sha256:'+hashlib.sha256(text.encode('utf-8')).hexdigest()

def classify(text:str,policy:dict[str,Any])->dict[str,Any]:
    cfg=policy.get('intake_classification') if isinstance(policy.get('intake_classification'),dict) else {}
    t=norm(text)
    phrases=[norm(x) for x in cfg.get('high_confidence_phrases') or []]
    terms=[norm(x) for x in cfg.get('structural_terms') or []]
    quants=[norm(x) for x in cfg.get('global_quantifiers') or []]
    phrase_hit=next((p for p in phrases if p and p in t),None)
    structural_hits=[x for x in terms if x and x in t]
    quantifier_hits=[x for x in quants if x and x in t]
    structural=bool(phrase_hit or (structural_hits and quantifier_hits))
    confidence='HIGH' if phrase_hit else ('MEDIUM' if structural else 'NONE')
    scope=str(cfg.get('default_candidate_scope') or 'PLATFORM_GLOBAL') if structural else 'TRANSIENT'
    category='ARCHITECTURE' if structural_hits else 'TRANSIENT'
    return {'structural':structural,'confidence':confidence,'suggested_scope':scope,
            'suggested_category':category,'phrase_hit':phrase_hit,
            'structural_hits':structural_hits,'quantifier_hits':quantifier_hits}

def append_private(path:Path,row:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    try:os.chmod(path.parent,0o700)
    except Exception:pass
    with path.open('a',encoding='utf-8') as f:
        fcntl.flock(f.fileno(),fcntl.LOCK_EX)
        f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
        f.flush();os.fsync(f.fileno());fcntl.flock(f.fileno(),fcntl.LOCK_UN)
    try:os.chmod(path,0o600)
    except Exception:pass
def capture(text:str,project_id:str,operator:str,request_id:str,policy:dict[str,Any],path:Path)->dict[str,Any]:
    c=classify(text,policy)
    out={'schema':RECEIPT_SCHEMA,'observed_at':now_iso(),'request_id':request_id,
         'project_id':project_id,'operator':operator,'structural_candidate':c['structural'],
         'classification':c,'automatic_external_spend_eur':0}
    if not c['structural']:
        out['status']='NOT_STRUCTURAL';return out
    did='opdir-candidate-'+uuid.uuid4().hex
    row={'schema':'chacha.dev/operator-directive-candidate/v1','directive_id':did,
         'received_at':out['observed_at'],'source':'OPERATOR','request_id':request_id,
         'project_id':project_id,'operator':operator,'raw_instruction':text,
         'text_digest':text_digest(text),'scope':c['suggested_scope'],
         'category':c['suggested_category'],'confidence':c['confidence'],
         'status':'RECEIVED','activation_status':'NOT_ACTIVE_UNTIL_PROPAGATION_VERIFIED',
         'requires_architecture_application':True,'automatic_external_spend_eur':0}
    append_private(path,row)
    out.update({'status':'CAPTURED','directive_id':did,
                'activation_status':row['activation_status']})
    return out

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--text',required=True);ap.add_argument('--project-id',required=True)
    ap.add_argument('--operator',required=True);ap.add_argument('--request-id',required=True)
    ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--intake',type=Path,required=True)
    a=ap.parse_args();out=capture(a.text,a.project_id,a.operator,a.request_id,load(a.policy),a.intake)
    print(json.dumps(out,ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
