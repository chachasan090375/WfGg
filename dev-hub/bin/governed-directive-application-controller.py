#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,hashlib,time
from pathlib import Path

def load(p): return json.loads(Path(p).read_text())
def rows(p): return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]
def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--intake',required=True); ap.add_argument('--directive-id',required=True); ap.add_argument('--plan',required=True); ap.add_argument('--output',required=True); a=ap.parse_args()
 cand=next((x for x in rows(a.intake) if x.get('directive_id')==a.directive_id),None)
 if not cand: raise SystemExit('BLOCK:DIRECTIVE_NOT_FOUND')
 if cand.get('status')!='RECEIVED' or cand.get('activation_status')!='NOT_ACTIVE_UNTIL_PROPAGATION_VERIFIED': raise SystemExit('BLOCK:DIRECTIVE_STATE_INVALID')
 plan=load(a.plan); required={'lifecycle','component-registry-reconciler','guardian','canonical-component-registry'}
 sinks=set(plan.get('required_sinks') or [])
 if not required.issubset(sinks): raise SystemExit('BLOCK:REQUIRED_SINKS_MISSING')
 out={'schema':'chacha.dev/governed-directive-application/v1','directive_id':a.directive_id,'status':'READY_TO_APPLY','generated_at':now(),'candidate_text_digest':cand.get('text_digest'),'required_sinks':sorted(sinks),'activation_requires':['APPLIED','VERIFIED','ACTIVE'],'fail_closed':True,'automatic_external_spend_eur':0}
 Path(a.output).write_text(json.dumps(out,indent=2)+'\n'); print('GOVERNED_DIRECTIVE_APPLICATION=READY_TO_APPLY'); return 0
if __name__=='__main__': raise SystemExit(main())
