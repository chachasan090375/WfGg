#!/usr/bin/env python3
import importlib.util,json,tempfile,threading,time,sys
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))
spec=importlib.util.spec_from_file_location('gpp',BIN/'governed-platform-promotion.py')
gpp=importlib.util.module_from_spec(spec);spec.loader.exec_module(gpp)
import promotion_transaction as ptx
import promotion_cycle_evidence as pce

def save(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj)+'\n')
def base_meta(rb):return {'candidate_revision':'a'*40,'candidate_tree':'b'*40,'human_production_approval_present':True,'platform_qualification':'PASS','guardian_pre_action':'PASS','sentinel_exact_revision':'PASS','rollback_path':str(rb),'automatic_external_spend_eur':0}

def expect(fn,needle):
 try:fn();raise AssertionError('expected failure '+needle)
 except ValueError as e:assert needle in str(e),(needle,e)

with tempfile.TemporaryDirectory() as td:
 t=Path(td);runtime=t/'runtime';runtime.mkdir();rel=t/'release';old=t/'old';rel.mkdir();old.mkdir();current=t/'current';current.symlink_to(old,target_is_directory=True)
 (rel/'dev-hub/systemd').mkdir(parents=True);(rel/'dev-hub/config').mkdir(parents=True)
 ext=t/'external';ext.mkdir();save(rel/'.release-preparation.json',base_meta(old))
 (rel/'dev-hub/systemd/x.service').write_text('[Service]\nReadWritePaths='+str(runtime/'alpha')+' '+str(runtime/'beta')+' '+str(ext)+'\n')
 stop=t/'stop.json';save(stop,{'active':False});save(rel/'dev-hub/config/emergency-stop.v1.json',{'schema':'chacha.dev/emergency-stop/v1','state_file':str(stop)})

 acq=ptx.acquire(runtime,'promotion-test','owner-a','a'*40,300);token=acq['lease_token'];lease_id=acq['lease_id']
 assert ptx.public_status(runtime)['lease_id']==lease_id
 expect(lambda:ptx.acquire(runtime,'promotion-other','owner-b','a'*40,300),'PROMOTION_LEASE_HELD')
 expect(lambda:ptx.assert_owner(runtime,'wrong','promotion-test','a'*40,'TEST'),'PROMOTION_LEASE_OWNER_MISMATCH')
 print('CHACHA_DEV_PROMOTION_SINGLE_WRITER_LEASE=PASS')

 prep=t/'prepare.json';out=gpp.prepare(rel,runtime,prep,'promotion-test',token)
 assert out['status']=='PASS' and out['promotion_lease_id']==lease_id and (runtime/'alpha').is_dir() and (runtime/'beta').is_dir(),out
 expect(lambda:gpp.prepare(rel,runtime,prep,'promotion-test',token),'IMMUTABLE_RECEIPT_ALREADY_EXISTS')
 print('CHACHA_DEV_PROMOTION_IMMUTABLE_PREPARE_RECEIPT=PASS')

 act=t/'activate.json';a=gpp.activate(rel,current,runtime,act,'promotion-test',token)
 assert a['status']=='PASS' and current.resolve()==rel.resolve() and a['current_release_mutated'] is True,a
 meta=json.load(open(rel/'.release-preparation.json'));assert meta['promotion_lease_id']==lease_id and meta['current_switch_controller']=='governed-platform-promotion'
 print('CHACHA_DEV_PROMOTION_EXCLUSIVE_ATOMIC_CURRENT_SWITCH=PASS')

 class H(BaseHTTPRequestHandler):
  count=0
  def do_GET(self):
   H.count+=1
   if H.count<3:self.send_response(503);self.end_headers();return
   body=b'{"status":"PASS","component":"test"}';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def log_message(self,*args):pass
 srv=HTTPServer(('127.0.0.1',0),H);threading.Thread(target=srv.serve_forever,daemon=True).start()
 ready=t/'ready.json';r=gpp.wait_ready('http://127.0.0.1:'+str(srv.server_port),5,.01,1,ready,runtime,'promotion-test',token,'a'*40)
 srv.shutdown();assert r['status']=='PASS' and r['attempt']==3 and r['promotion_lease_id']==lease_id,r
 print('CHACHA_DEV_PROMOTION_READINESS_LEASE_BOUND=PASS')

 guardian_src=t/'guardian-source.json';sentinel_src=t/'sentinel-source.json'
 save(guardian_src,{'schema':'chacha.dev/guardian-verdict/v3','verdict':'PASS','event_id':'g-post','stop_recommended':False})
 save(sentinel_src,{'schema':'chacha.dev/sentinel-technical-receipt/v1','verdict':'PASS','revision':'a'*40,'receipt_id':'s-post'})
 guardian=t/'guardian-bound.json';sentinel=t/'sentinel-bound.json'
 gpp.seal_assurance('guardian-post',guardian_src,guardian,runtime,'promotion-test',token,'a'*40)
 gpp.seal_assurance('sentinel-post',sentinel_src,sentinel,runtime,'promotion-test',token,'a'*40)
 print('CHACHA_DEV_PROMOTION_ASSURANCE_LEASE_BINDING=PASS')

 run={'status':'CONVERGED','next_state':'RESUME','run_id':'r1','direct_mutation_by_supervisor':False,'automatic_external_spend_eur':0}
 save(t/'controlled.json',run);save(t/'timer.json',dict(run,run_id='r2'))
 controlled_receipt=t/'controlled-cycle.json';timer_receipt=t/'timer-cycle.json'
 c=pce.capture(runtime,'promotion-test',token,'a'*40,'CONTROLLED',t/'controlled.json',70,71,controlled_receipt)
 tr=pce.capture(runtime,'promotion-test',token,'a'*40,'TIMER',t/'timer.json',71,72,timer_receipt,'SYSTEMD_TIMER')
 assert c['run_id']=='r1' and tr['run_id']=='r2' and c['counter_after']==71 and tr['counter_after']==72
 lx=ptx.assert_owner(runtime,token,'promotion-test','a'*40,'TEST_CYCLE_BINDING')
 save(t/'controlled.json',dict(run,run_id='tampered'))
 expect(lambda:pce.require(controlled_receipt,'CONTROLLED',lx,'a'*40),'CYCLE_EVIDENCE_RUN_DIGEST_MISMATCH')
 save(t/'controlled.json',run)
 assert pce.require(controlled_receipt,'CONTROLLED',lx,'a'*40)['run_id']=='r1'
 print('CHACHA_DEV_PROMOTION_CYCLE_EVIDENCE_TAMPER_BLOCK=PASS')
 expect(lambda:pce.capture(runtime,'promotion-test',token,'a'*40,'CONTROLLED',t/'controlled.json',70,71,controlled_receipt),'IMMUTABLE_RECEIPT_ALREADY_EXISTS')
 final=t/'final.json';out=gpp.finalize(rel,current,runtime,final,guardian,sentinel,ready,controlled_receipt,timer_receipt,3,'promotion-test',token)
 meta=json.load(open(rel/'.release-preparation.json'))
 assert out['status']=='PASS' and meta['promotion_acceptance_status']=='PASS' and meta['promotion_final_verification']=='PASS',(out,meta)
 assert meta['controlled_cycle_run_id']=='r1' and meta['first_automatic_timer_run_id']=='r2'
 assert meta['controlled_cycle_evidence_digest']==c['binding_digest'] and meta['first_automatic_timer_cycle_evidence_digest']==tr['binding_digest']
 assert ptx.public_status(runtime)['status']=='FINALIZED'
 expect(lambda:gpp.finalize(rel,current,runtime,t/'final2.json',guardian,sentinel,ready,controlled_receipt,timer_receipt,3,'promotion-test',token),'PROMOTION_LEASE_NOT_ACTIVE')
 print('CHACHA_DEV_PROMOTION_CYCLE_EVIDENCE_WRITE_ONCE=PASS')
 print('CHACHA_DEV_PROMOTION_FINALIZE_EXACTLY_ONCE=PASS')

with tempfile.TemporaryDirectory() as td:
 t=Path(td);runtime=t/'runtime';runtime.mkdir();rel=t/'release';old=t/'old';rel.mkdir();old.mkdir();current=t/'current';current.symlink_to(old,target_is_directory=True)
 (rel/'dev-hub/config').mkdir(parents=True);save(rel/'.release-preparation.json',base_meta(old));stop=t/'stop.json';save(stop,{'active':False});save(rel/'dev-hub/config/emergency-stop.v1.json',{'schema':'chacha.dev/emergency-stop/v1','state_file':str(stop)})
 acq=ptx.acquire(runtime,'promotion-rollback','owner-a','a'*40,300);token=acq['lease_token'];gpp.activate(rel,current,runtime,t/'activate.json','promotion-rollback',token)
 rb=gpp.rollback(rel,current,runtime,t/'rollback.json','promotion-rollback',token,'TEST_FAILURE')
 assert rb['status']=='PASS' and current.resolve()==old.resolve() and ptx.public_status(runtime)['status']=='ROLLED_BACK'
 print('CHACHA_DEV_PROMOTION_ROLLBACK_LEASE_BOUND=PASS')

with tempfile.TemporaryDirectory() as td:
 runtime=Path(td)/'runtime';runtime.mkdir();acq=ptx.acquire(runtime,'promotion-recover','owner-a','a'*40,300)
 lp=ptx.runtime_paths(runtime)['lease'];x=json.load(open(lp));x['expires_epoch']=time.time()-1;save(lp,x)
 expect(lambda:ptx.recover(runtime,'promotion-recover','owner-b','a'*40,acq['lease_id'],300),'RECOVERY_OWNER_MISMATCH')
 rec=ptx.recover(runtime,'promotion-recover','owner-a','a'*40,acq['lease_id'],300)
 st=ptx.public_status(runtime)
 assert rec['status']=='PASS' and rec['lease_id']!=acq['lease_id'] and st['recovered_from_lease_id']==acq['lease_id']
 assert st['root_lease_id']==acq['lease_id'] and st['recovery_generation']==1
 assert ptx.lease_lineage(runtime,rec['lease_id'])==[rec['lease_id'],acq['lease_id']]
 print('CHACHA_DEV_PROMOTION_EXPIRED_LEASE_RECOVERY=PASS')
 print('CHACHA_DEV_PROMOTION_RECOVERY_SAME_OWNER_ONLY=PASS')

with tempfile.TemporaryDirectory() as td:
 t=Path(td);runtime=t/'runtime';runtime.mkdir();rel=t/'release';old=t/'old';rel.mkdir();old.mkdir();current=t/'current';current.symlink_to(old,target_is_directory=True)
 (rel/'dev-hub/config').mkdir(parents=True);save(rel/'.release-preparation.json',base_meta(old));stop=t/'stop.json';save(stop,{'active':False});save(rel/'dev-hub/config/emergency-stop.v1.json',{'schema':'chacha.dev/emergency-stop/v1','state_file':str(stop)})
 acq=ptx.acquire(runtime,'promotion-recovery-finalize','owner-a','a'*40,300);token=acq['lease_token'];old_lx=ptx.assert_owner(runtime,token,'promotion-recovery-finalize','a'*40,'TEST')
 gpp.activate(rel,current,runtime,t/'activate.json','promotion-recovery-finalize',token)
 guardian_src=t/'guardian-source.json';sentinel_src=t/'sentinel-source.json'
 save(guardian_src,{'schema':'chacha.dev/guardian-verdict/v3','verdict':'PASS','event_id':'g-post','stop_recommended':False})
 save(sentinel_src,{'schema':'chacha.dev/sentinel-technical-receipt/v1','verdict':'PASS','revision':'a'*40,'receipt_id':'s-post'})
 guardian=t/'guardian-bound.json';sentinel=t/'sentinel-bound.json'
 gpp.seal_assurance('guardian-post',guardian_src,guardian,runtime,'promotion-recovery-finalize',token,'a'*40)
 gpp.seal_assurance('sentinel-post',sentinel_src,sentinel,runtime,'promotion-recovery-finalize',token,'a'*40)
 ready=t/'ready.json';save(ready,ptx.bind_receipt(old_lx,{'schema':gpp.SCHEMA,'phase':'READINESS','status':'PASS','candidate_revision':'a'*40,'url':'http://127.0.0.1/ready','attempt':1,'payload':{'status':'PASS'}}))
 run={'status':'CONVERGED','next_state':'RESUME','run_id':'r1','direct_mutation_by_supervisor':False,'automatic_external_spend_eur':0}
 save(t/'controlled.json',run);save(t/'timer.json',dict(run,run_id='r2'))
 controlled=t/'controlled-cycle.json';timer=t/'timer-cycle.json'
 pce.capture(runtime,'promotion-recovery-finalize',token,'a'*40,'CONTROLLED',t/'controlled.json',10,11,controlled)
 pce.capture(runtime,'promotion-recovery-finalize',token,'a'*40,'TIMER',t/'timer.json',11,12,timer,'SYSTEMD_TIMER')
 lp=ptx.runtime_paths(runtime)['lease'];x=json.load(open(lp));x['expires_epoch']=time.time()-1;save(lp,x)
 rec=ptx.recover(runtime,'promotion-recovery-finalize','owner-a','a'*40,acq['lease_id'],300);new_token=rec['lease_token']
 out=gpp.finalize(rel,current,runtime,t/'final-after-recovery.json',guardian,sentinel,ready,controlled,timer,2,'promotion-recovery-finalize',new_token)
 assert out['status']=='PASS' and ptx.public_status(runtime)['status']=='FINALIZED'
 print('CHACHA_DEV_PROMOTION_FINALIZE_AFTER_LEASE_RECOVERY_WITHOUT_EVIDENCE_REPLAY=PASS')

source=(BIN/'governed-platform-promotion.py').read_text();tx=(BIN/'promotion_transaction.py').read_text()
for marker in ('lease-acquire','lease-recover','seal-assurance','IMMUTABLE_RECEIPT_ALREADY_EXISTS','promotion_lease_id','atomic_current_switch'):
 assert marker in source or marker in tx,marker
print('CHACHA_DEV_GOVERNED_PLATFORM_PROMOTION_V2=PASS')
