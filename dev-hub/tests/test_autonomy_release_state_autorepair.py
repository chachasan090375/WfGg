#!/usr/bin/env python3
import importlib.util,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; BIN=ROOT/'dev-hub/bin'; CFG=ROOT/'dev-hub/config'; SYSTEMD=ROOT/'dev-hub/systemd'
sys.path.insert(0,str(BIN))
def mod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
wrap=mod('governed_release_state',BIN/'guardian-governed-release-state-reconciler.py')
self_policy=json.loads((CFG/'autonomy-self-model.v1.json').read_text()); sup=json.loads((CFG/'autonomy-supervision.v1.json').read_text())
guard=json.loads((CFG/'guardian-role-contracts.v1.json').read_text()); reg=json.loads((CFG/'canonical-component-registry.v1.json').read_text())
contracts={x['contract_id']:x for x in guard['contracts']}
for cid in ('component:release-state-reconciler','role:release-state-reconciler'):
 c=contracts[cid]; assert 'RECONCILE_ACTIVE_RELEASE_METADATA' in c['allowed_actions']; assert 'PRODUCTION_DEPLOY' in c['forbidden_actions']; assert 'DELETE_RELEASE' in c['forbidden_actions']
release_engineer=contracts['role:release-engineer']; assert set(release_engineer['allowed_permissions'])=={'read','plan'}; assert 'DISPATCH_TASK' in release_engineer['allowed_actions']; assert 'PRODUCTION_DEPLOY' in release_engineer['forbidden_actions']; assert 'MUTATE_RUNTIME' in release_engineer['forbidden_actions']
assert reg['classification_overrides']['release-state-reconciler']=='CORE_PLATFORM_COMPONENT'
assert self_policy['issue_owners']['ACTIVE_RELEASE_METADATA_DRIFT']['owner']=='release-state-reconciler'
spec=sup['owner_actions']['RECONCILE_RUNTIME_RELEASE_STATE']; assert spec['requires_human'] is False; assert spec['dispatch']['unit']=='chacha-dev-release-state-reconciler.service'
assert spec['dispatch']['unit'] in sup['runtime']['allowed_systemd_units']
unit=(SYSTEMD/'chacha-dev-release-state-reconciler.service').read_text(); assert 'ProtectSystem=strict' in unit; assert 'ReadWritePaths=/opt/chacha-dev/platform/releases' in unit
with tempfile.TemporaryDirectory(prefix='chacha-release-autorepair-') as td:
 td=Path(td); platform=td/'platform'; releases=platform/'releases'; runtime=td/'runtime'; release=releases/'r1'; release.mkdir(parents=True); (runtime/'control').mkdir(parents=True); (runtime/'release-gates').mkdir(parents=True)
 rev='a'*40; tree='b'*40; (release/'.revision').write_text(rev+'\n'); (release/'.tree').write_text(tree+'\n')
 prep={'schema':'chacha.dev/release-preparation/v1','candidate_revision':rev,'candidate_tree':tree,'human_production_approval_present':True,'guardian_pre_action':'PASS','sentinel_exact_revision':'PASS','automatic_external_spend_eur':0,'activation_status':'ACTIVE_PENDING_VALIDATION','other_preserved':'YES'}
 (release/'.release-preparation.json').write_text(json.dumps(prep)+'\n'); (platform/'current').symlink_to(release,target_is_directory=True); (runtime/'control/emergency-stop.json').write_text(json.dumps({'active':False})+'\n')
 health=td/'health.json'; health.write_text(json.dumps({'status':'PASS'})+'\n'); dummy_policy=td/'policy.json'; dummy_policy.write_text('{}\n')
 guardian=td/'guardian.py'; guardian.write_text("#!/usr/bin/env python3\nimport json,sys\np=sys.argv[sys.argv.index('--event')+1];e=json.load(open(p));print(json.dumps({'schema':'chacha.dev/guardian-verdict/v3','event_id':e['event_id'],'action_id':e['action_id'],'verdict':'PASS','stop_recommended':False}))\n")
 os.chmod(guardian,0o755); out=td/'result.json'
 cmd=['python3',str(BIN/'guardian-governed-release-state-reconciler.py'),'--platform-root',str(platform),'--runtime-root',str(runtime),'--guardian-client',str(guardian),'--guardian-policy',str(dummy_policy),'--core-reconciler',str(BIN/'release_state_reconciler.py'),'--health-url',health.as_uri(),'--output',str(out)]
 before_target=(platform/'current').resolve(); before_rev=(release/'.revision').read_text(); before_tree=(release/'.tree').read_text()
 r=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE); assert r.returncode==0,(r.stdout,r.stderr)
 result=json.load(open(out)); after=json.load(open(release/'.release-preparation.json'))
 assert result['status']=='PASS' and result['applied'] is True,result; assert after['activation_status']=='ACTIVE'; assert after['other_preserved']=='YES'
 assert (platform/'current').resolve()==before_target; assert (release/'.revision').read_text()==before_rev; assert (release/'.tree').read_text()==before_tree
 proof=json.load(open(result['install_proof'])); assert proof['schema']=='chacha.dev/platform-install-pass/v1' and proof['revision']==rev and proof['release']==str(release.resolve()) and proof['status']=='PASS'
 # Missing Sentinel evidence must fail closed before mutation.
 after['activation_status']='ACTIVE_PENDING_VALIDATION'; after['sentinel_exact_revision']='FAIL'; (release/'.release-preparation.json').write_text(json.dumps(after)+'\n')
 try: wrap.active_attestation(platform,runtime,health.as_uri()); raise AssertionError('missing sentinel accepted')
 except RuntimeError as e: assert 'SENTINEL_EXACT_REVISION_MISSING' in str(e),e
 assert json.load(open(release/'.release-preparation.json'))['activation_status']=='ACTIVE_PENDING_VALIDATION'
print('CHACHA_DEV_RELEASE_STATE_AUTOREPAIR=PASS')
print('CHACHA_DEV_RELEASE_STATE_EXACT_INSTALL_PROOF=PASS')
print('CHACHA_DEV_RELEASE_STATE_CURRENT_IMMUTABLE=PASS')
print('CHACHA_DEV_RELEASE_STATE_FAIL_CLOSED=PASS')
print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
