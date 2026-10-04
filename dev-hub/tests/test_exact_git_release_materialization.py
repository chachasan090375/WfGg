#!/usr/bin/env python3
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))
import exact_git_release as egr
import promotion_transaction as ptx
spec=importlib.util.spec_from_file_location('gpp_exact',BIN/'governed-platform-promotion.py')
gpp=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpp)

def run(*a,cwd=None,binary=False):
    p=subprocess.run(list(a),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    return p.stdout if binary else p.stdout.decode().strip()

def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x)+'\n')

def expect(fn,needle):
    try:
        fn()
        raise AssertionError('expected '+needle)
    except ValueError as e:
        assert needle in str(e),(needle,e)

with tempfile.TemporaryDirectory() as td:
    t=Path(td)
    repo=t/'repo'
    repo.mkdir()
    run('git','init','-q',cwd=repo)
    run('git','config','user.email','test@chacha.invalid',cwd=repo)
    run('git','config','user.name','ChaCha Test',cwd=repo)
    stop=t/'stop.json'
    save(stop,{'active':False})
    (repo/'dev-hub/config').mkdir(parents=True)
    save(repo/'dev-hub/config/emergency-stop.v1.json',{'schema':'chacha.dev/emergency-stop/v1','state_file':str(stop)})
    (repo/'CHECKSUMS.sha256').write_text('canonical-checksum-manifest\n')
    (repo/'app.txt').write_text('exact payload\n')
    (repo/'nested/deep').mkdir(parents=True)
    (repo/'nested/deep/payload.txt').write_text('recursive payload\n')
    run('git','add','.',cwd=repo)
    run('git','commit','-q','-m','fixture exact release',cwd=repo)
    rev=run('git','rev-parse','HEAD',cwd=repo)
    tree=run('git','rev-parse','HEAD^{tree}',cwd=repo)
    old=t/'old'
    old.mkdir()
    prep=t/'prep.json'
    save(prep,{'candidate_revision':rev,'candidate_tree':tree,'human_production_approval_present':True,'platform_qualification':'PASS','guardian_pre_action':'PASS','sentinel_exact_revision':'PASS','rollback_path':str(old),'automatic_external_spend_eur':0})
    rel=t/'release'
    mat=t/'materialization.json'
    m=egr.materialize(repo,rev,rel,prep,mat)
    assert m['status']=='PASS' and (rel/'CHECKSUMS.sha256').read_text()=='canonical-checksum-manifest\n',m
    v=egr.verify_release(rel,repo,rev,tree)
    assert v['status']=='PASS' and v['mismatch_count']==0 and v['missing_count']==0 and v['extra_payload_count']==0,v
    assert v['checked_blobs']==v['tracked_blob_count'] and v['tracked_blob_count']>=4,v
    assert (rel/'nested/deep/payload.txt').read_text()=='recursive payload\n'
    print('CHACHA_DEV_EXACT_GIT_MATERIALIZATION=PASS')

    meta_now=json.load(open(rel/'.release-preparation.json'))
    no_source=dict(meta_now);no_source.pop('source_git_root',None)
    expect(lambda:gpp.validate_preparation(no_source),'SOURCE_GIT_ROOT_REQUIRED')
    print('CHACHA_DEV_EXACT_GIT_PROVENANCE_REQUIRED=PASS')

    runtime=t/'runtime'
    runtime.mkdir()
    current=t/'current'
    current.symlink_to(old,target_is_directory=True)
    acq=ptx.acquire(runtime,'exact-git-promotion','governed-platform-promotion',rev,300)
    token=acq['lease_token']

    (rel/'CHECKSUMS.sha256').write_text('regenerated-release-checksums\n')
    expect(lambda:gpp.activate(rel,current,runtime,t/'activate-mutated.json','exact-git-promotion',token),'EXACT_GIT_RELEASE_VERIFICATION_FAILED:TRACKED_BLOB_MISMATCH')
    assert current.resolve()==old.resolve()
    print('CHACHA_DEV_EXACT_GIT_TRACKED_MUTATION_BLOCKED_BEFORE_ACTIVATE=PASS')

    raw=run('git','show',rev+':CHECKSUMS.sha256',cwd=repo,binary=True)
    (rel/'CHECKSUMS.sha256').write_bytes(raw)
    (rel/'injected.bin').write_bytes(b'x')
    expect(lambda:gpp.activate(rel,current,runtime,t/'activate-extra.json','exact-git-promotion',token),'UNTRACKED_RELEASE_PAYLOAD_FORBIDDEN')
    assert current.resolve()==old.resolve()
    (rel/'injected.bin').unlink()
    print('CHACHA_DEV_EXACT_GIT_EXTRA_PAYLOAD_BLOCKED_BEFORE_ACTIVATE=PASS')

    a=gpp.activate(rel,current,runtime,t/'activate.json','exact-git-promotion',token)
    assert a['status']=='PASS' and current.resolve()==rel.resolve(),a
    ev=a['exact_git_release_verification']
    assert ev['status']=='PASS' and ev['checked_blobs']==ev['tracked_blob_count'] and ev['mismatch_count']==0,ev
    print('CHACHA_DEV_EXACT_GIT_ACTIVATE_GATE=PASS')

policy=json.load(open(ROOT/'dev-hub/config/platform-promotion-transaction.v1.json'))
assert policy['invariants']['release_payload_must_match_exact_candidate_git_blobs_before_activate'] is True
assert policy['invariants']['tracked_git_payload_mutation_after_materialization_forbidden'] is True
assert policy['future_component_contract']['exact_git_release_materialization_required'] is True
ops=json.load(open(ROOT/'dev-hub/config/operator-directives.v1.json'))
d=next(x for x in ops['directives'] if x['directive_id']=='opdir-exact-git-release-materialization')
assert d['status']=='ACTIVE' and d['scope']=='PLATFORM_GLOBAL' and d['backfill_required'] is True
print('CHACHA_DEV_EXACT_GIT_RELEASE_PERMANENT_INVARIANT=PASS')
sinks=json.load(open(ROOT/'dev-hub/config/operator-directive-sinks.v1.json'))['sinks']
assert all(x in sinks for x in d['required_sinks'])
sentinel=json.load(open(ROOT/'dev-hub/config/sentinel-technical-policy.v1.json'))
assert 'promotion-exact-git-release-before-activate' in sentinel['blocking_checks']
assert any(x.get('path')=='dev-hub/tests/test_exact_git_release_materialization.py' and x.get('blocking') is True for x in sentinel['mandatory_platform_tests'])
print('CHACHA_DEV_EXACT_GIT_RELEASE_PROPAGATION=VERIFIED')
