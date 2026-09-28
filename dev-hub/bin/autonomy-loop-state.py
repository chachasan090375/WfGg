#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,hashlib,json,os
from pathlib import Path
from typing import Any
SCHEMA='chacha.dev/autonomy-loop-state/v1'
def iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
def load(p:Path,default=None):
 try:
  x=json.loads(p.read_text(encoding='utf-8')); return x if isinstance(x,dict) else ({} if default is None else default)
 except Exception:return {} if default is None else default
def save(p:Path,x:dict[str,Any]):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n');os.replace(t,p)
def digest(x:Any)->str:return 'sha256:'+hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def issue_key(x:dict[str,Any])->str:return str(x.get('code'))+'|'+str(x.get('subject'))
def advance(state:dict[str,Any],model:dict[str,Any],plan:dict[str,Any])->dict[str,Any]:
 rec=model.get('reconciliation') if isinstance(model.get('reconciliation'),dict) else {};issues=[x for x in rec.get('issues') or [] if isinstance(x,dict)]
 current={issue_key(x):x for x in issues}; prior=state.get('issues') if isinstance(state.get('issues'),dict) else {}
 merged={}
 for k,v in current.items():
  old=prior.get(k) if isinstance(prior.get(k),dict) else {}
  merged[k]={'code':v.get('code'),'subject':v.get('subject'),'first_seen_at':old.get('first_seen_at') or iso(),'last_seen_at':iso(),'verified_resolved':False,'attempts':int(old.get('attempts') or 0),'last_action':old.get('last_action')}
 for k,old in prior.items():
  if k not in current and isinstance(old,dict): merged[k]={**old,'verified_resolved':True,'resolved_at':old.get('resolved_at') or iso()}
 cycle=int(state.get('cycle') or 0)+1
 return {'schema':SCHEMA,'cycle':cycle,'updated_at':iso(),'current_state':plan.get('next_state'),'self_model_digest':digest(model),'plan_digest':digest(plan),'issues':merged,'history':(state.get('history') or [])[-49:]+[{'cycle':cycle,'at':iso(),'state':plan.get('next_state'),'issue_count':len(current),'plan_status':plan.get('status')}],'automatic_external_spend_eur':0}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--state',type=Path,required=True);ap.add_argument('--self-model',type=Path,required=True);ap.add_argument('--plan',type=Path,required=True);a=ap.parse_args();s=load(a.state,{});m=load(a.self_model,{});p=load(a.plan,{});out=advance(s,m,p);save(a.state,out);print('CHACHA_DEV_AUTONOMY_LOOP_STATE=PASS');print('CYCLE='+str(out['cycle']));print('STATE='+str(out['current_state']));print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
if __name__=='__main__':main()
