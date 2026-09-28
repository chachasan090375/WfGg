#!/usr/bin/env python3
import importlib.util,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; BIN=ROOT/'dev-hub/bin'; CFG=ROOT/'dev-hub/config'
sys.path.insert(0,str(BIN))
def mod(name,path):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
selfm=mod('selfm',BIN/'autonomy-self-model.py'); sup=mod('sup',BIN/'autonomy-supervision-controller.py')
policy=json.load(open(CFG/'autonomy-supervision.v1.json'))
sp=json.load(open(CFG/'autonomy-self-model.v1.json'))
recovery=json.load(open(CFG/'recovery-orchestrator.v1.json'))
roles=json.load(open(CFG/'guardian-role-contracts.v1.json'))
role=next(x for x in roles['contracts'] if x.get('contract_id')=='role:autonomous-recovery-agent')
assert 'RESTART_SAFE_SERVICE' in role['allowed_actions'] and 'service-restart' in role['allowed_permissions'],role
lifecycle_role=next(x for x in roles['contracts'] if x.get('contract_id')=='role:branch-foundry-lifecycle')
assert 'RETIRE_EPHEMERAL_BRANCH' in lifecycle_role['allowed_actions'] and 'ephemeral-runtime-retire' in lifecycle_role['allowed_permissions'],lifecycle_role
assert 'DELETE_EPHEMERAL_WORKSPACE' in lifecycle_role['forbidden_actions'] and 'RETIRE_ACTIVE_EPHEMERAL_BRANCH' in lifecycle_role['forbidden_actions'],lifecycle_role
assert set(policy['runtime']['allowed_systemd_units'])>={'chacha-dev-autonomous-recovery-agent.service'}
assert policy['owner_actions']['RECOVER_SAFE_SERVICES']['owner']=='autonomous-recovery-agent'
assert policy['owner_actions']['RETIRE_STALE_EPHEMERAL_BRANCH']['owner']=='branch-foundry-lifecycle'
assert policy['owner_actions']['RETIRE_STALE_EPHEMERAL_BRANCH']['dispatch']['unit']=='chacha-dev-branch-foundry-lifecycle.service'
assert sp['issue_owners']['EPHEMERAL_BRANCH_STALE']['class']=='INTERNAL_DRIFT'
assert sp['issue_owners']['EPHEMERAL_BRANCH_TTL_EXCEEDED_ACTIVE']['class']=='HUMAN_BOUNDARY'
assert sp['issue_owners']['SERVICE_UNHEALTHY_SAFE_RESTART']['class']=='RUNTIME_HEALTH'
assert sp['issue_owners']['SERVICE_UNHEALTHY_HUMAN']['class']=='HUMAN_BOUNDARY'
svc=(ROOT/'dev-hub/systemd/chacha-dev-autonomous-recovery-agent.service').read_text()
assert 'autonomous-recovery-agent.py' in svc and 'ReadWritePaths=/opt/chacha-dev/runtime/autonomous-recovery' in svc
tmpfiles=(ROOT/'dev-hub/systemd/chacha-dev-autonomous-recovery.tmpfiles.conf').read_text(); installer=(ROOT/'dev-hub/bin/install-autonomous-recovery-agent.sh').read_text()
assert '/opt/chacha-dev/runtime/autonomous-recovery/work' in tmpfiles and 'systemd-tmpfiles --create' in installer
worker=(ROOT/'dev-hub/guardian/worker.js').read_text()
assert 'SAFE_RESTART_UNITS' in worker and 'SAFE_RESTART_UNIT_NOT_ALLOWLISTED' in worker
assert '"chacha-dev-direct-operator.service"' in worker and '"chacha-dev-cockpit-state.service"' in worker
assert 'EPHEMERAL_RETIRE_PERMISSION_REQUIRED' in worker and 'EPHEMERAL_RETIRE_WORKSPACE_DELETE_FORBIDDEN' in worker
assert 'ttl_expired' in worker and 'runtime_inactive' in worker and 'persistent_state_preserved' in worker
branch_svc=(ROOT/'dev-hub/systemd/chacha-dev-branch-foundry-lifecycle.service').read_text()
assert 'ephemeral_branch_lifecycle.py --mode reconcile' in branch_svc
assert '/opt/chacha-dev/platform/releases' not in branch_svc and 'NoNewPrivileges=true' in branch_svc
safe={x['unit'] for x in recovery['service_health']['safe_restart']}; human={x['unit'] for x in recovery['service_health']['human_boundary']}
assert safe=={'chacha-dev-direct-operator.service','chacha-dev-cockpit-state.service'}
assert {'chacha-dev-emergency-stop-surface.service','chacha-dev-emergency-control-bridge.service'}<=human
with tempfile.TemporaryDirectory() as td:
    t=Path(td); state=t/'state.json'; calls=t/'systemctl.log'; events=t/'guardian.log'
    state.write_text(json.dumps({'chacha-dev-direct-operator.service':'inactive','chacha-dev-cockpit-state.service':'active','chacha-dev-emergency-stop-surface.service':'inactive','chacha-dev-emergency-control-bridge.service':'active'}))
    systemctl=t/'systemctl'; systemctl.write_text(f'''#!/usr/bin/env python3
import json,sys,pathlib
p=pathlib.Path({str(state)!r}); log=pathlib.Path({str(calls)!r}); x=json.loads(p.read_text()); cmd=sys.argv[1]; u=sys.argv[2]
if cmd=="is-active": print(x.get(u,"inactive")); raise SystemExit(0 if x.get(u)=="active" else 3)
if cmd=="restart": log.write_text((log.read_text() if log.exists() else "")+u+"\\n"); x[u]="active"; p.write_text(json.dumps(x)); raise SystemExit(0)
raise SystemExit(2)
'''); systemctl.chmod(0o755)
    guardian=t/'guardian.py'; guardian.write_text(f'''#!/usr/bin/env python3
import json,sys,pathlib
p=pathlib.Path(sys.argv[sys.argv.index("--event")+1]); x=json.loads(p.read_text()); log=pathlib.Path({str(events)!r}); log.write_text((log.read_text() if log.exists() else "")+x["phase"]+":"+x["context"]["service_unit"]+"\\n"); print(json.dumps({{"schema":"chacha.dev/guardian-verdict/v3","verdict":"PASS","severity":"INFO","reason_codes":[]}}))
'''); guardian.chmod(0o755)
    rec=t/'recovery.py'; rec.write_text('''#!/usr/bin/env python3
import json,sys,pathlib
out=pathlib.Path(sys.argv[sys.argv.index("--output")+1]); out.write_text(json.dumps({"schema":"chacha.dev/recovery-decision/v1","action":"RESTART_SAFE_SERVICE","autonomous":True,"rerun_acceptance":True,"feed_learning":True})+"\\n")
'''); rec.chmod(0o755)
    issues=selfm.service_health_issues(ROOT,systemctl); codes={(x['code'],x['subject']) for x in issues}
    assert ('SERVICE_UNHEALTHY_SAFE_RESTART','chacha-dev-direct-operator.service') in codes,codes
    assert ('SERVICE_UNHEALTHY_HUMAN','chacha-dev-emergency-stop-surface.service') in codes,codes
    mapped=[selfm.issue_view(x,sp) for x in issues]
    plan=sup.plan({'reconciliation':{'issue_count':1,'issues':[next(x for x in mapped if x['code']=='SERVICE_UNHEALTHY_SAFE_RESTART')]}},policy)
    assert plan['next_state']=='DELEGATE' and plan['actions'][0]['owner']=='autonomous-recovery-agent',plan
    human_issue=next(x for x in mapped if x['code']=='SERVICE_UNHEALTHY_HUMAN')
    hp=sup.plan({'reconciliation':{'issue_count':1,'issues':[human_issue]}},policy)
    assert hp['next_state']=='AWAIT_HUMAN' and not hp['actions'],hp
    runtime=t/'runtime'; (runtime/'control').mkdir(parents=True); (runtime/'control/emergency-stop.json').write_text(json.dumps({'active':False}))
    cmd=[sys.executable,str(BIN/'autonomous-recovery-agent.py'),'--repo-root',str(ROOT),'--runtime-root',str(runtime),'--systemctl-bin',str(systemctl),'--guardian-client',str(guardian),'--guardian-policy',str(t/'dummy.json'),'--recovery-orchestrator',str(rec)]
    p=subprocess.run(cmd,text=True,capture_output=True); assert p.returncode==0,(p.stdout,p.stderr)
    assert calls.read_text().splitlines()==['chacha-dev-direct-operator.service'],calls.read_text()
    assert events.read_text().splitlines()==['PRE_ACTION:chacha-dev-direct-operator.service','POST_ACTION:chacha-dev-direct-operator.service'],events.read_text()
    latest=json.load(open(runtime/'autonomous-recovery/latest.json')); assert latest['actions'][0]['status']=='VERIFIED',latest
    x=json.loads(state.read_text()); x['chacha-dev-direct-operator.service']='inactive'; state.write_text(json.dumps(x)); before=calls.read_text()
    (runtime/'control/emergency-stop.json').write_text(json.dumps({'active':True}))
    p=subprocess.run(cmd,text=True,capture_output=True); assert p.returncode==0,(p.stdout,p.stderr); assert calls.read_text()==before
print('CHACHA_DEV_AUTONOMY_SERVICE_HEALTH_CLASSIFICATION=PASS')
print('CHACHA_DEV_AUTONOMY_RECOVERY_OWNER_GOVERNED=PASS')
print('CHACHA_DEV_AUTONOMY_UNSAFE_SERVICE_HUMAN_BOUNDARY=PASS')
print('CHACHA_DEV_AUTONOMY_RECOVERY_STOP_INVARIANT=PASS')
