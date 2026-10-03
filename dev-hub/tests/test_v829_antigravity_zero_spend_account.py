#!/usr/bin/env python3
from __future__ import annotations
import contextlib,importlib.util,io,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin';AD=ROOT/'dev-hub/adapters'
def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(mod);return mod
def fake_backend(path:Path,gemini_remaining:float=1.0,third_party_remaining:float=1.0,credits:bool=False,mutate:bool=False):
    body='''#!/usr/bin/env python3
import json,sys
args=sys.argv[1:]
if "models" in args:
 print("gemini-3.8-flash-medium\\tGemini 3.8 Flash (Medium)")
 print("claude-sonnet-4-6\\tClaude Sonnet 4.6 (Thinking)")
 print("gpt-oss-120b-medium\\tGPT-OSS 120B (Medium)")
 raise SystemExit(0)
cmd="config" if "/config" in args else "usage" if "/usage" in args else None
credits=__CREDITS__;gemini_remaining=__GEMINI__;third_party_remaining=__THIRD__;mutate=__MUTATE__
if cmd=="config": data={"config":{"useG1Credits":credits,"modelProvider":""}}
elif cmd=="usage": data={"groups":[{"name":"Gemini Models","buckets":[{"remaining_fraction":gemini_remaining,"reset_time":"2099-01-01T00:00:00Z"}]},{"name":"Claude and GPT models","buckets":[{"remaining_fraction":third_party_remaining,"reset_time":"2099-01-02T00:00:00Z"}]}]}
elif "--print" in args:
 if mutate and "--add-dir" in args:
  from pathlib import Path
  ws=Path(args[args.index("--add-dir")+1]);(ws/"generated-v829.txt").write_text("V829_CODE_EDIT_OK\\n")
 print(json.dumps({"status":"SUCCESS","model":args[args.index("--model")+1] if "--model" in args else None}));raise SystemExit(0)
else: print(json.dumps({"status":"ERROR"}));raise SystemExit(1)
print(json.dumps({"status":"SUCCESS","num_turns":0,"usage":{"total_tokens":0},"command":{"name":cmd,"data":data}}))
'''.replace('__CREDITS__','True' if credits else 'False').replace('__GEMINI__',repr(gemini_remaining)).replace('__THIRD__',repr(third_party_remaining)).replace('__MUTATE__','True' if mutate else 'False')
    path.write_text(body);path.chmod(0o755)

with tempfile.TemporaryDirectory(prefix='v829-zero-') as raw:
    td=Path(raw);token=td/'oauth';token.write_text('fixture');runtime=td/'runtime';runtime.mkdir();backend=td/'agy';out=td/'attestation.json';fake_backend(backend)
    p=subprocess.run([sys.executable,str(BIN/'provider-zero-cost-attestor.py'),'--runtime-root',str(runtime),'--output',str(out),'--backend',str(backend),'--oauth-token',str(token)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,p.stderr;x=json.load(open(out));assert x['status']=='PASS' and x['quota_available'] is True,x
    assert x['auth_mode']=='account-oauth' and x['baseline_quota_only'] is True and x['overage_enabled'] is False,x
    assert x['automatic_external_spend_eur']==0 and x['config_probe_zero_tokens'] and x['usage_probe_zero_tokens'],x
    fake_backend(backend,gemini_remaining=0.0,third_party_remaining=0.0);out2=td/'noquota.json'
    q=subprocess.run([sys.executable,str(BIN/'provider-zero-cost-attestor.py'),'--runtime-root',str(runtime),'--output',str(out2),'--backend',str(backend),'--oauth-token',str(token)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert q.returncode!=0;z=json.load(open(out2));assert 'ACCOUNT_BASELINE_QUOTA_INSUFFICIENT' in z['reason_codes'],z
    fake_backend(backend,gemini_remaining=0.0,third_party_remaining=1.0);fallback=td/'fallback.json'
    q=subprocess.run([sys.executable,str(BIN/'provider-zero-cost-attestor.py'),'--runtime-root',str(runtime),'--output',str(fallback),'--backend',str(backend),'--oauth-token',str(token)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert q.returncode==0,q.stderr;z=json.load(open(fallback));assert z['selected_model']=='claude-sonnet-4-6' and z['selected_quota_group']=='claude and gpt models',z
    fake_backend(backend,gemini_remaining=1.0,third_party_remaining=1.0,credits=True);out3=td/'credits.json'
    q=subprocess.run([sys.executable,str(BIN/'provider-zero-cost-attestor.py'),'--runtime-root',str(runtime),'--output',str(out3),'--backend',str(backend),'--oauth-token',str(token)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert q.returncode!=0;z=json.load(open(out3));assert 'AI_CREDIT_OVERAGE_NOT_DISABLED' in z['reason_codes'],z
    os.environ['CHACHA_PROVIDER_QUOTA_CIRCUIT_STATE']=str(td/'quota-circuit.json')
    fake_backend(backend,1.0,1.0,False);ag=loadmod('v829_ag',AD/'antigravity-adapter.py');ag.BACKEND=backend;ag.ACCOUNT_HOME=runtime/'provider-economics/antigravity-account-home';ag.ATTESTATION=out
    ok,reason,quota=ag.live_zero_cost_gate();assert ok and quota['selected_model']=='gemini-3.8-flash-medium',(reason,quota)
    ag.pqc.open_circuit('antigravity','gemini-3.8-flash-medium','RESOURCE_EXHAUSTED Resets in 1h','test')
    ok,reason,quota=ag.live_zero_cost_gate();assert ok and quota['selected_model']=='claude-sonnet-4-6',(reason,quota)
    eco,reason,att=ag.economics();assert eco and reason=='ZERO_COST_ATTESTED',(reason,att)
src=(AD/'antigravity-adapter.py').read_text();assert "BACKEND=Path('/usr/local/bin/agy')" in src;assert '/usr/local/bin/agy-dev' not in src;assert "env.pop('GEMINI_API_KEY',None)" in src
cfg=json.loads((ROOT/'dev-hub/config/adapter-auto-remediation.v1.json').read_text())['profiles']['antigravity-adapter'];probe=cfg['zero_cost_attestation_probe']
assert probe['non_generative'] is True and probe['automatic_external_spend_eur']==0 and probe['baseline_quota_only'] is True and probe['overage_must_be_disabled'] is True
remediator_src=(BIN/'domain-readiness-auto-remediator.py').read_text()
assert 'refresh_zero_cost_attestation' in remediator_src
assert "refresh=refresh_zero_cost_attestation(repo,runtime,profile,provider,root) if probe.get('enabled') is True else None" in remediator_src
# Positive maturity is monotone: an automatic retry may not demote the same governed source.
runtime_registry=loadmod('v829_runtime_registry',BIN/'runtime-adapter-registry.py')
with tempfile.TemporaryDirectory(prefix='v829-monotone-') as raw:
    td=Path(raw);repo=td/'repo';cfg=repo/'dev-hub/config';ad=repo/'dev-hub/adapters';cfg.mkdir(parents=True);ad.mkdir(parents=True)
    src=ad/'a.py';src.write_text('#!/usr/bin/env python3\n');src.chmod(0o755)
    base=cfg/'provider-adapters.v1.json';base.write_text(json.dumps({'schema':'chacha.dev/provider-adapters/v1','providers':{'p':{'adapter':'a','execution':'vps'}},'adapters':{'a':{'status':'DESIGNED','executable':None,'supports':['workspace-write']}}}))
    (cfg/'adapter-provisioning.v1.json').write_text(json.dumps({'adapters':{'a':{'source':'dev-hub/adapters/a.py','version':'1.1.0'}}}))
    exe=td/'adapter';exe.write_text('#!/bin/sh\nexit 0\n');exe.chmod(0o755);state=td/'state.json'
    enabled=runtime_registry.persist(base,state,'a','ENABLED',str(exe),runtime_registry.digest_file(exe),['enabled-proof'])
    preserved=runtime_registry.persist(base,state,'a','CONTRACT_OK',None,None,['retry-proof'])
    assert preserved['status']=='ENABLED' and preserved['executable']==str(exe),preserved
    st=json.load(open(state));assert st['adapters']['a']['status']=='ENABLED',st
    assert st['history'][-1]['event']=='STATE_REGRESSION_IGNORED' and st['history'][-1]['reason']=='MATURITY_REGRESSION',st['history'][-1]
# Quota-backed READY state requires a fresh economics attestation immediately before dispatch.
readiness_mod=loadmod('v829_readiness',BIN/'domain-toolchain-readiness.py')
with tempfile.TemporaryDirectory(prefix='v829-readiness-economics-') as raw:
    td=Path(raw);att=td/'att.json';exe=td/'adapter';exe.write_text('#!/bin/sh\nexit 0\n');exe.chmod(0o755)
    profile={'zero_cost_attestation_required':True,'zero_cost_attestation':str(att),'allowed_zero_cost_classes':['quota']}
    base={'schema':'chacha.dev/provider-zero-cost-attestation/v1','provider_id':'antigravity','status':'PASS','automatic_external_spend_eur':0,'cost_class':'quota','quota_available':True}
    expired=dict(base,valid_until='2000-01-01T00:00:00Z');att.write_text(json.dumps(expired))
    args=(Path('/'),{'id':'antigravity','status':'ADOPT'},{'antigravity':{'adapter':'antigravity-adapter','execution':'vps'}},{'antigravity-adapter':{'status':'ENABLED','executable':str(exe)}},{'antigravity':{}},{},{'antigravity':{'state':'HEALTHY','source':'test','checked_at':'now'}},{'antigravity-adapter':profile})
    row=readiness_mod.provider_candidate(*args);assert row['gate']=='PROVIDER_HEALTH_PROBE_REQUIRED' and 'ZERO_COST_ATTESTATION_EXPIRED' in row['reason'],row
    fresh=dict(base,valid_until='2099-01-01T00:00:00Z');att.write_text(json.dumps(fresh));row=readiness_mod.provider_candidate(*args);assert row['gate']=='READY' and row['economics_attestation_status']=='PASS',row
remediator_contract=(BIN/'domain-readiness-auto-remediator.py').read_text();assert 'REFRESH_EXISTING_ENABLED_PROVIDER' in remediator_contract
adapter_src=(AD/'antigravity-adapter.py').read_text();assert '--dangerously-skip-permissions' in adapter_src and 'GOVERNED_WORKSPACE_REMOTE_FORBIDDEN' in adapter_src
assert "provider_timeout=max(30,governed_timeout-60)" in adapter_src and "adapter_timeout=min(governed_timeout-10,provider_timeout+30)" in adapter_src
assert "economics_attestation_fresh':True" in adapter_src
assert "live_economics_recheck_required_before_generation':True" in adapter_src
run_policy=json.loads((ROOT/'dev-hub/config/run-controller.v1.json').read_text());assert run_policy['dispatch']['capability_timeout_seconds']['code-edit']==900
assert probe['valid_seconds']==1200
prov=json.loads((ROOT/'dev-hub/config/adapter-provisioning.v1.json').read_text());assert prov['adapters']['antigravity-adapter']['version']=='1.1.7';assert prov['adapters']['antigravity-adapter']['probe_timeout_seconds']==45
run_controller=loadmod('v829_run_controller',BIN/'run-controller.py')
env=run_controller.prepare_envelope('r',1,{'project':'p','transition':'X','permission':'workspace-write'},{'id':'t','kind':'domain-capability','capabilities':['code-edit'],'permission':'workspace-write'},[],run_policy,None)
assert env['policy_context']['timeout_seconds']==900,env['policy_context']
normal=run_controller.prepare_envelope('r',1,{'project':'p','transition':'X','permission':'read'},{'id':'t2','kind':'domain-capability','capabilities':['documentation'],'permission':'read'},[],run_policy,None)
assert normal['policy_context']['timeout_seconds']==300,normal['policy_context']
HEADLESS_WORKSPACE_PERMISSION_CONTRACT=True
# ChaCha DEV development workspaces receive an isolated source baseline, never an empty branch.
central=loadmod('v829_central',BIN/'central-interface-controller-core.py')
with tempfile.TemporaryDirectory(prefix='v829-baseline-') as raw:
    td=Path(raw);repo=td/'repo';runtime_root=td/'runtime';repo.mkdir();runtime_root.mkdir();(repo/'.revision').write_text('baseline-rev\n');(repo/'source.py').write_text('print("baseline")\n')
    ws=runtime_root/'projects'/'exec-project'/'branches'/'development';receipt=td/'materialization.json'
    graph={'tasks':[{'id':'capability:domain-development:code-edit','capabilities':['code-edit'],'permission':'workspace-write','metadata':{'branch_workspace':str(ws)}}]}
    mx=central.materialize_development_workspaces(repo,runtime_root,'chacha-dev-platform',graph,receipt)
    assert mx['status']=='PASS' and mx['rows'][0]['status']=='MATERIALIZED',mx
    copied=ws/'source.py';assert copied.is_file() and copied.read_text()=='print("baseline")\n';assert not copied.is_symlink();assert not (ws/'.revision').exists()
    assert (ws/'.git').is_dir() and mx['rows'][0]['isolated_git']['initialized'] is True,mx
    assert mx['rows'][0]['isolated_git']['remote_count']==0,mx
    gs=subprocess.run(['git','-C',str(ws),'status','--porcelain'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False);assert gs.returncode==0 and not gs.stdout.strip(),gs.stderr
    gr=subprocess.run(['git','-C',str(ws),'remote'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False);assert gr.returncode==0 and not gr.stdout.strip(),gr.stdout
# code-edit cannot self-certify: it must mutate the workspace and expose local digest-verifiable evidence.
with tempfile.TemporaryDirectory(prefix='v829-code-edit-') as raw:
    td=Path(raw);runtime=td/'runtime';runtime.mkdir();token=td/'oauth';token.write_text('fixture');backend=td/'agy';att=td/'attestation.json';fake_backend(backend,mutate=True)
    q=subprocess.run([sys.executable,str(BIN/'provider-zero-cost-attestor.py'),'--runtime-root',str(runtime),'--output',str(att),'--backend',str(backend),'--oauth-token',str(token)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False);assert q.returncode==0,q.stderr
    ag=loadmod('v829_ag_edit',AD/'antigravity-adapter.py');ag.BACKEND=backend;ag.ACCOUNT_HOME=runtime/'provider-economics/antigravity-account-home';ag.ATTESTATION=att;ag.EVIDENCE_ROOT=td/'evidence';ag.GOVERNED_WORKSPACE_ROOT=td
    ws=td/'workspace';ws.mkdir();(ws/'source.py').write_text('print("before")\n');subprocess.run(['git','-C',str(ws),'init','-q'],check=True);subprocess.run(['git','-C',str(ws),'add','-A'],check=True);subprocess.run(['git','-C',str(ws),'-c','user.name=Test','-c','user.email=test@local.invalid','commit','-qm','baseline'],check=True)
    req={'schema':'chacha.dev/dispatch-envelope/v1','project':'p','run_id':'r','workspace':str(ws),'task':{'id':'t','capabilities':['code-edit'],'permission':'workspace-write','outputs':[{'type':'domain-capability-result','id':'domain:development:code-edit'}]},'metadata':{'intent_excerpt':'modify safely'}}
    buf=io.StringIO()
    with contextlib.redirect_stdout(buf):rc=ag.execute_capability(req,req['task'],'code-edit','workspace-write')
    result=json.loads(buf.getvalue());assert rc==0 and result['status']=='OK',result
    assert (ws/'generated-v829.txt').read_text()=='V829_CODE_EDIT_OK\n'
    local=[e for e in result['evidence'] if Path(str(e.get('source') or '')).is_absolute()];assert len(local)>=2,result
    for e in local:
        ep=Path(e['source']);assert ep.is_file(),e;assert ag.file_sha(ep)==e['digest'],e
    fake_backend(backend,mutate=False);ag.BACKEND=backend;noop=td/'noop';noop.mkdir();(noop/'source.py').write_text('same\n');subprocess.run(['git','-C',str(noop),'init','-q'],check=True);subprocess.run(['git','-C',str(noop),'add','-A'],check=True);subprocess.run(['git','-C',str(noop),'-c','user.name=Test','-c','user.email=test@local.invalid','commit','-qm','baseline'],check=True);req['run_id']='r-noop';req['workspace']=str(noop)
    buf=io.StringIO()
    with contextlib.redirect_stdout(buf):rc=ag.execute_capability(req,req['task'],'code-edit','workspace-write')
    nores=json.loads(buf.getvalue());assert rc==2 and nores['status']=='BLOCKED' and nores['summary']=='WORKSPACE_WRITE_NO_MUTATION',nores
# A provider may return exit 1 without surfacing its 429 in stdout/stderr. A zero-token
# post-failure /usage probe must still classify an exhausted selected pool semantically.
with tempfile.TemporaryDirectory(prefix='v829-post-failure-quota-') as raw:
    td=Path(raw);backend=td/'agy';backend.write_text('#!/bin/sh\nexit 1\n');backend.chmod(0o755)
    att=td/'att.json';att.write_text(json.dumps({'schema':'chacha.dev/provider-zero-cost-attestation/v1','provider_id':'antigravity','status':'PASS','cost_class':'quota','quota_available':True,'auth_mode':'account-oauth','baseline_quota_only':True,'overage_enabled':False,'valid_until':'2099-01-01T00:00:00Z','automatic_external_spend_eur':0,'minimum_remaining_fraction':0.01,'selected_model':'claude-sonnet-4-6','selected_quota_group':'claude and gpt models'}))
    agq=loadmod('v829_ag_post_failure',AD/'antigravity-adapter.py');agq.BACKEND=backend;agq.ATTESTATION=att;agq.ACCOUNT_HOME=td/'home';agq.GOVERNED_WORKSPACE_ROOT=td;agq.EVIDENCE_ROOT=td/'evidence'
    agq.live_zero_cost_gate=lambda:(True,'ACCOUNT_BASELINE_QUOTA_AVAILABLE',{'selected_model':'claude-sonnet-4-6','selected_quota_group':'claude and gpt models','remaining_fraction':1.0,'reset_time':'2099-01-01T00:00:00Z'})
    usage={'status':'SUCCESS','num_turns':0,'usage':{'total_tokens':0},'command':{'name':'usage','data':{'groups':[{'name':'Claude and GPT models','buckets':[{'remaining_fraction':0.0,'reset_time':'2099-01-08T00:00:00Z'}]}]}}}
    agq.slash_probe=lambda command:(usage,None) if command=='/usage' else (None,'UNEXPECTED_PROBE')
    if agq.pqc is not None:os.environ['CHACHA_PROVIDER_QUOTA_CIRCUIT_STATE']=str(td/'provider-circuit.json')
    ws=td/'workspace';ws.mkdir();(ws/'source.py').write_text('before\n');subprocess.run(['git','-C',str(ws),'init','-q'],check=True);subprocess.run(['git','-C',str(ws),'add','-A'],check=True);subprocess.run(['git','-C',str(ws),'-c','user.name=Test','-c','user.email=test@local.invalid','commit','-qm','baseline'],check=True)
    req={'schema':'chacha.dev/dispatch-envelope/v1','project':'p','run_id':'r-quota','workspace':str(ws),'task':{'id':'t-quota','capabilities':['code-edit'],'permission':'workspace-write','outputs':[]},'metadata':{'intent_excerpt':'change safely'},'policy_context':{'timeout_seconds':120}}
    buf=io.StringIO()
    with contextlib.redirect_stdout(buf):rc=agq.execute_capability(req,req['task'],'code-edit','workspace-write')
    qres=json.loads(buf.getvalue());assert rc==2 and qres['status']=='BLOCKED' and qres['summary']=='PROVIDER_MODEL_QUOTA_EXHAUSTED',qres
    details={}
    for ev in qres['evidence']:
        if isinstance(ev.get('details'),dict):details.update(ev['details'])
    assert details['model']=='claude-sonnet-4-6' and details['remaining_fraction']==0.0,details
    assert details['usage_probe_zero_tokens'] is True and details['automatic_paid_upgrade'] is False and details['automatic_external_spend_eur']==0,details
    assert details['resume_at']=='2099-01-08T00:00:05Z',details
    receipts=[e for e in qres['evidence'] if e.get('kind')=='provider-execution-receipt']
    assert len(receipts)==1,qres
    re=receipts[0];rp=Path(re['source']);assert rp.is_file() and agq.file_sha(rp)==re['digest'],re
    rx=json.load(open(rp));assert rx['provider_exit_code']==1 and rx['execution_status']=='FAILED',rx
    assert rx['automatic_external_spend_eur']==0 and rx['provider_stdout_digest'].startswith('sha256:') and rx['provider_stderr_digest'].startswith('sha256:'),rx
    assert rx['workspace_before'].startswith('sha256:') and rx['workspace_after'].startswith('sha256:'),rx
    assert rx['added']==[] and rx['modified']==[] and rx['deleted']==[],rx

print('CHACHA_DEV_V829_ANTIGRAVITY_ACCOUNT_OAUTH=PASS')
print('CHACHA_DEV_V829_BASELINE_QUOTA_GATE=PASS')
print('CHACHA_DEV_V829_MULTI_POOL_ZERO_COST_FALLBACK=PASS')
print('CHACHA_DEV_V829_MODEL_QUOTA_CIRCUIT_FALLBACK=PASS')
print('CHACHA_DEV_V829_AI_CREDIT_OVERAGE_DISABLED=PASS')
print('CHACHA_DEV_V829_ZERO_TOKEN_ECONOMICS_PROBE=PASS')
print('CHACHA_DEV_V829_API_KEY_CODE_EDIT_PATH=FORBIDDEN')
print('CHACHA_DEV_V829_RUNTIME_ADAPTER_MATURITY_MONOTONE=PASS')
print('CHACHA_DEV_V829_PRE_REMEDIATION_ATTESTATION_REFRESH=PASS')
print('CHACHA_DEV_V829_PRE_DISPATCH_ECONOMICS_FRESHNESS=PASS')
print('CHACHA_DEV_V829_ENABLED_PROVIDER_REFRESH_NO_REPROVISION=PASS')
print('CHACHA_DEV_V829_DEVELOPMENT_BASELINE_MATERIALIZATION=PASS')
print('CHACHA_DEV_V829_ISOLATED_GIT_BASELINE_NO_REMOTE=PASS')
print('CHACHA_DEV_V829_CODE_EDIT_NOOP_FORBIDDEN=PASS')
print('CHACHA_DEV_V829_LOCAL_CODE_EDIT_EVIDENCE=PASS')
print('CHACHA_DEV_V829_HEADLESS_WORKSPACE_PERMISSION=PASS')
print('CHACHA_DEV_V829_WORKSPACE_REMOTE_FORBIDDEN=PASS')
print('CHACHA_DEV_V829_CAPABILITY_AWARE_TIMEOUT=PASS')
print('CHACHA_DEV_V829_ADAPTER_SPECIFIC_PROBE_TIMEOUT=PASS')
print('CHACHA_DEV_V829_LONG_RUN_ECONOMICS_WINDOW=PASS')
print('CHACHA_DEV_V829_REPEATABILITY_USES_FRESH_ATTESTATION=PASS')
print('CHACHA_DEV_V829_GENERATION_LIVE_ECONOMICS_GATE_PRESERVED=PASS')
print('CHACHA_DEV_V829_POST_FAILURE_ZERO_TOKEN_QUOTA_CLASSIFICATION=PASS')
print('CHACHA_DEV_V829_PROVIDER_FAILURE_LOCAL_EVIDENCE=PASS')
print('CHACHA_DEV_V829_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
