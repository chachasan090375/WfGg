#!/usr/bin/env python3
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin';sys.path.insert(0,str(BIN))
import promotion_transaction as ptx
import promotion_cycle_evidence as pce

def save(p,x):p.write_text(json.dumps(x)+'\n')
def blocked(fn,needle):
    try:fn();raise AssertionError('expected '+needle)
    except ValueError as e:assert needle in str(e),(needle,e)

with tempfile.TemporaryDirectory() as td:
    t=Path(td);runtime=t/'runtime';runtime.mkdir();rev='a'*40
    lease=ptx.acquire(runtime,'promo','owner',rev,300);token=lease['lease_token'];lx=ptx.assert_owner(runtime,token,'promo',rev,'TEST')
    run=t/'run.json';save(run,{'status':'CONVERGED','next_state':'RESUME','run_id':'r1','direct_mutation_by_supervisor':False,'automatic_external_spend_eur':0})
    receipt=t/'controlled.json';pce.capture(runtime,'promo',token,rev,'CONTROLLED',run,7,8,receipt)
    assert pce.require(receipt,'CONTROLLED',lx,rev)['run_id']=='r1'
    x=json.loads(receipt.read_text());x['counter_after']=9;save(receipt,x)
    blocked(lambda:pce.require(receipt,'CONTROLLED',lx,rev),'CYCLE_EVIDENCE_COUNTER_INVALID')
    x['counter_after']=8;x['run_id']='evil';save(receipt,x)
    blocked(lambda:pce.require(receipt,'CONTROLLED',lx,rev),'CYCLE_EVIDENCE_BINDING_DIGEST_MISMATCH')
    # Fresh receipt for run-file tamper proof.
    receipt2=t/'controlled-2.json';pce.capture(runtime,'promo',token,rev,'CONTROLLED',run,8,9,receipt2)
    save(run,{'status':'CONVERGED','next_state':'RESUME','run_id':'r1','direct_mutation_by_supervisor':False,'automatic_external_spend_eur':0,'tampered':True})
    blocked(lambda:pce.require(receipt2,'CONTROLLED',lx,rev),'CYCLE_EVIDENCE_RUN_DIGEST_MISMATCH')
    timer=t/'timer.json';save(timer,{'status':'CONVERGED','next_state':'RESUME','run_id':'rt','direct_mutation_by_supervisor':False,'automatic_external_spend_eur':0})
    blocked(lambda:pce.capture(runtime,'promo',token,rev,'TIMER',timer,9,10,t/'timer-receipt.json'),'TIMER_TRIGGER_REQUIRED')
    ok=pce.capture(runtime,'promo',token,rev,'TIMER',timer,9,10,t/'timer-receipt-ok.json','SYSTEMD_TIMER:2026-10-01T11:02:28Z')
    assert pce.require(t/'timer-receipt-ok.json','TIMER',lx,rev)['run_id']=='rt'
print('CHACHA_DEV_PROMOTION_CYCLE_EVIDENCE_TAMPER_RESISTANCE=PASS')
