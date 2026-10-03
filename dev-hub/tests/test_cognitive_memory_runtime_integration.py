from __future__ import annotations
import importlib.util,json,os,sqlite3,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def loadmod(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
T=loadmod('cmf_tiering',ROOT/'dev-hub/bin/cognitive-memory-tiering.py')
E=loadmod('cmf_trigger',ROOT/'dev-hub/bin/cognitive_memory_trigger.py')
POL=json.loads((ROOT/'dev-hub/config/cognitive-memory-fabric.v1.json').read_text())
FAKE='''#!/usr/bin/env python3
import hashlib,json,os,shutil,sys
from pathlib import Path
req=json.load(sys.stdin);wd=Path(req['workspace']);meta=req['metadata'];root=Path(os.environ['FAKE_REMOTE_ROOT'])
if 'nas_storage' in meta:
 x=meta['nas_storage'];src=wd/x['local_path'];dst=root/x['remote_path'];dst.parent.mkdir(parents=True,exist_ok=True)
 if not dst.exists():shutil.copy2(src,dst)
 print(json.dumps({'status':'OK','summary':'FAKE_CREATE_ONLY'}));raise SystemExit(0)
x=meta['nas_readback'];src=root/x['remote_path'];dst=wd/x['local_path'];dst.parent.mkdir(parents=True,exist_ok=True)
h='sha256:'+hashlib.sha256(src.read_bytes()).hexdigest()
if h!=x['expected_sha256']:print(json.dumps({'status':'ERROR','summary':'HASH'}));raise SystemExit(2)
shutil.copy2(src,dst);print(json.dumps({'status':'OK','summary':'FAKE_READBACK'}))
'''

def mkdb(path:Path,value:str):
 db=sqlite3.connect(path);db.execute('create table if not exists t(v text)');db.execute('insert into t values(?)',(value,));db.commit();db.close()

def policy_for(root:Path,central:Path,ledger:Path):
 p=json.loads(json.dumps(POL));p['persistence']['agent_store_root']=str(root);p['existing_sources']={'central_memory_db':str(central)};p['tiering']['tiering_ledger']=str(ledger);p['tiering']['restore_probe_interval_cycles']=2;return p

def test_runtime_snapshots_agent_and_central_sqlite_and_restores_periodically():
 with tempfile.TemporaryDirectory() as td:
  base=Path(td);agents=base/'agents';agents.mkdir();a=agents/'agent.db';c=base/'central.db';mkdb(a,'a1');mkdb(c,'c1')
  ledger=base/'ledger.json';remote=base/'remote';fake=base/'adapter.py';fake.write_text(FAKE);fake.chmod(0o755);os.environ['FAKE_REMOTE_ROOT']=str(remote)
  p=policy_for(agents,c,ledger)
  first=T.plan(p,'INTERVAL',agents.resolve(),{'digests':{}});assert first['material_change'] is True and len(first['changed'])==2
  r1=T.shadow_execute(p,first,ledger,{'digests':{}},fake,fake);assert r1['archived']==2 and r1['restore_probe']['status']=='NOT_DUE'
  l1=json.loads(ledger.read_text());second=T.plan(p,'INTERVAL',agents.resolve(),l1);assert second['material_change'] is False
  r2=T.shadow_execute(p,second,ledger,l1,fake,fake);assert r2['archived']==0 and r2['restore_probe']['status']=='PASS' and r2['restore_probe']['workspace_disposed'] is True
  assert json.loads(ledger.read_text())['cycle_count']==2;assert len(list(remote.rglob('*.db')))==2

def test_sqlite_wal_participates_in_material_fingerprint():
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'x.db';db=sqlite3.connect(p);db.execute('pragma journal_mode=WAL');db.execute('create table t(v)');db.commit();before=T.source_fingerprint(p);db.execute('insert into t values(1)');db.commit();after=T.source_fingerprint(p);db.close();assert before!=after

def test_event_trigger_queue_is_deduplicated_and_fail_closed():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);a=E.emit('MEMORY_PROMOTED_TRUSTED','agent-memory-store','memory:m1',root);b=E.emit('MEMORY_PROMOTED_TRUSTED','agent-memory-store','memory:m1',root)
  assert a['status']=='QUEUED' and b['status']=='DEDUPLICATED' and len(list(root.glob('*.json')))==1
  try:E.emit('WHATEVER','x','y',root);raise AssertionError('expected block')
  except ValueError as ex:assert 'TRIGGER_NOT_ALLOWED' in str(ex)

def test_event_systemd_path_drains_pending_queue_and_remains_shadow_only():
 path=(ROOT/'dev-hub/systemd/chacha-dev-cognitive-memory-tiering-events.path').read_text();svc=(ROOT/'dev-hub/systemd/chacha-dev-cognitive-memory-tiering-events.service').read_text();policy=json.loads((ROOT/'dev-hub/config/cognitive-memory-fabric.v1.json').read_text())
 assert 'DirectoryNotEmpty=/opt/chacha-dev/runtime/knowledge/cognitive-memory-tiering-events/pending' in path
 assert 'cognitive-memory-tiering-event-drain.py' in svc
 assert policy['tiering']['event_runtime']=='SYSTEMD_PATH_DRAIN_SHADOW'
 assert policy['tiering']['production_activation_authorized'] is False and policy['tiering']['hot_purge_automatic'] is False

if __name__=='__main__':
 n=0
 for name,fn in sorted(globals().items()):
  if name.startswith('test_'):fn();print(name+'=PASS');n+=1
 print('CHACHA_DEV_COGNITIVE_MEMORY_RUNTIME_INTEGRATION=PASS');print('TEST_COUNT='+str(n));print('PRODUCTION_ACTIVATION=NO');print('HOT_PURGE=NO')
