#!/usr/bin/env python3
import importlib.util,json,tempfile,threading,time
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('gpp',ROOT/'dev-hub/bin/governed-platform-promotion.py')
gpp=importlib.util.module_from_spec(spec);spec.loader.exec_module(gpp)

def save(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj)+'\n')
def base_meta(rb):return {'candidate_revision':'a'*40,'candidate_tree':'b'*40,'human_production_approval_present':True,'platform_qualification':'PASS','guardian_pre_action':'PASS','sentinel_exact_revision':'PASS','rollback_path':str(rb),'activation_status':'ACTIVE','automatic_external_spend_eur':0}

with tempfile.TemporaryDirectory() as td:
 t=Path(td);candidate=t/'candidate';runtime=t/'runtime';rb=t/'rollback';ext=t/'external';rb.mkdir();ext.mkdir();runtime.mkdir();(candidate/'dev-hub/systemd').mkdir(parents=True)
 save(candidate/'.release-preparation.json',base_meta(rb))
 (candidate/'dev-hub/systemd/x.service').write_text('[Service]\nReadWritePaths='+str(runtime/'alpha')+' '+str(runtime/'beta')+' '+str(ext)+'\n')
 out=gpp.prepare(candidate,runtime,t/'prepare.json')
 assert out['status']=='PASS' and (runtime/'alpha').is_dir() and (runtime/'beta').is_dir(),out
 assert out['current_release_mutated'] is False,out
 print('CHACHA_DEV_PROMOTION_RUNTIME_ROOT_MATERIALIZATION=PASS')

class H(BaseHTTPRequestHandler):
 count=0
 def do_GET(self):
  H.count+=1
  if H.count<3:self.send_response(503);self.end_headers();return
  body=b'{"status":"PASS","component":"test"}'
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
srv=HTTPServer(('127.0.0.1',0),H);threading.Thread(target=srv.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory() as td:
 r=gpp.wait_ready('http://127.0.0.1:'+str(srv.server_port),5,.01,1,Path(td)/'ready.json')
 assert r['status']=='PASS' and r['attempt']==3,r
srv.shutdown();print('CHACHA_DEV_PROMOTION_READINESS_RETRY=PASS')

with tempfile.TemporaryDirectory() as td:
 t=Path(td);rel=t/'release';old=t/'old';rel.mkdir();old.mkdir();current=t/'current';current.symlink_to(rel,target_is_directory=True)
 save(rel/'.release-preparation.json',base_meta(old))
 save(t/'guardian.json',{'verdict':'PASS','event_id':'g-post'})
 save(t/'sentinel.json',{'verdict':'PASS','revision':'a'*40,'receipt_id':'s-post'})
 save(t/'ready.json',{'schema':gpp.SCHEMA,'phase':'READINESS','status':'PASS'})
 run={'status':'CONVERGED','next_state':'RESUME','run_id':'r1','direct_mutation_by_supervisor':False,'automatic_external_spend_eur':0}
 save(t/'controlled.json',run);run2=dict(run,run_id='r2');save(t/'timer.json',run2);save(t/'stop.json',{'active':False})
 out=gpp.finalize(rel,current,t/'guardian.json',t/'sentinel.json',t/'ready.json',t/'controlled.json',t/'timer.json',t/'stop.json',3,70,71,71,72)
 meta=json.load(open(rel/'.release-preparation.json'))
 assert out['status']=='PASS' and meta['promotion_acceptance_status']=='PASS' and meta['promotion_final_verification']=='PASS',(out,meta)
 assert current.resolve()==rel.resolve()
 print('CHACHA_DEV_PROMOTION_RECEIPT_FINALIZATION=PASS')
 try:gpp.finalize(rel,current,t/'guardian.json',t/'sentinel.json',t/'ready.json',t/'controlled.json',t/'timer.json',t/'stop.json',4,70,71,71,72);raise AssertionError('release overage accepted')
 except ValueError as e:assert 'RELEASE_RETENTION_OVERAGE' in str(e)
 print('CHACHA_DEV_PROMOTION_FINALIZATION_FAIL_CLOSED=PASS')

wf=(ROOT/'.github/workflows/dev-hub-v7-guardian-contract-sync.yml').read_text()
assert 'fetch-depth: 2' in wf,wf[:1000]
assert "0000000000000000000000000000000000000000" in wf
assert 'git rev-parse HEAD^' in wf
source=(ROOT/'dev-hub/bin/governed-platform-promotion.py').read_text()
for forbidden in ('os.symlink','current.symlink_to','ln -s','unlink(current'):
 assert forbidden not in source,forbidden
print('CHACHA_DEV_PROMOTION_CURRENT_MUTATION_FORBIDDEN=PASS')
print('CHACHA_DEV_GUARDIAN_SYNC_NEW_BRANCH_TRANSPORT=PASS')
print('CHACHA_DEV_GOVERNED_PLATFORM_PROMOTION=PASS')
