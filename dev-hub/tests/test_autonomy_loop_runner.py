#!/usr/bin/env python3
import json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin';CFG=ROOT/'dev-hub/config'
sys.path.insert(0,str(BIN))
import agent_fleet_observatory as afo
import canonical_component_registry as ccr

def load(p):return json.loads(Path(p).read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
def run(cmd):return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=90)
with tempfile.TemporaryDirectory(prefix='autonomy-runner-') as raw:
 td=Path(raw);runtime=td/'runtime';platform=td/'platform';(runtime/'agent-evolution').mkdir(parents=True);(runtime/'control').mkdir(parents=True);(platform/'releases').mkdir(parents=True)
 # Three physical releases => no hygiene drift in this runner pilot.
 active=None
 for n in range(3):
  d=platform/'releases'/f'r{n}';d.mkdir();(d/'.revision').write_text(str(n)*40+'\n')
  if n==0:active=d
 (platform/'current').symlink_to(active)
 save(runtime/'control/emergency-stop.json',{'schema':'chacha.dev/emergency-stop-state/v1','active':False})
 routing=load(CFG/'agent-routing.v1.json');seven=load(CFG/'seven-agent-final-compromise.v1.json');project=load(ROOT/'dev-hub/projects/wfgg-radar/project-agent-registry.v1.json')
 canonical=ccr.build_registry(ROOT,load(CFG/'canonical-component-registry.v1.json'));expected_fleet_count=canonical['fleet_projection_count']
 old=afo.build_report(ROOT,runtime,load(CFG/'agent-fleet-observatory.v1.json'),load(CFG/'agent-evolution.v1.json'),routing,seven,[project])
 assert old['agent_count']==38,old['agent_count'];save(runtime/'agent-evolution/fleet-observatory-latest.json',old)
 calls=td/'systemctl-calls.txt';fake=td/'systemctl'
 fake.write_text(f'''#!/bin/sh
set -eu
echo "$2" >> "{calls}"
[ "$1" = start ]
if [ "$2" = chacha-dev-agent-fleet-observatory.service ]; then
  python3 "{BIN/'canonical_component_registry.py'}" --repo-root "{ROOT}" --policy "{CFG/'canonical-component-registry.v1.json'}" --output "{runtime/'canonical-registry/canonical-component-registry.json'}" >/dev/null
  python3 "{BIN/'agent_fleet_observatory.py'}" --repo-root "{ROOT}" --runtime-root "{runtime}" --policy "{CFG/'agent-fleet-observatory.v1.json'}" --evolution-policy "{CFG/'agent-evolution.v1.json'}" --routing "{CFG/'agent-routing.v1.json'}" --seven "{CFG/'seven-agent-final-compromise.v1.json'}" --project-registry "{ROOT/'dev-hub/projects/wfgg-radar/project-agent-registry.v1.json'}" --canonical-registry "{runtime/'canonical-registry/canonical-component-registry.json'}" --output "{runtime/'agent-evolution/fleet-observatory-latest.json'}" >/dev/null
  exit 0
fi
if [ "$2" = chacha-dev-intendant-hygiene.service ]; then
  rm -rf "{platform/'releases'/'r3'}"
  exit 0
fi
exit 7
''');fake.chmod(0o755)
 policy=td/'policy.json';save(policy,load(CFG/'autonomy-supervision.v1.json'))
 cmd=[sys.executable,str(BIN/'autonomy-loop-runner.py'),'--repo-root',str(ROOT),'--runtime-root',str(runtime),'--platform-root',str(platform),'--policy',str(policy),'--systemctl-bin',str(fake),'--test-mode']
 p=run(cmd);assert p.returncode==0,(p.stdout,p.stderr);assert 'CHACHA_DEV_AUTONOMY_LOOP=CONVERGED' in p.stdout,p.stdout
 assert load(runtime/'agent-evolution/fleet-observatory-latest.json')['agent_count']==expected_fleet_count
 rows=calls.read_text().splitlines();assert rows==['chacha-dev-agent-fleet-observatory.service'],rows
 # Second run sees a converged model and must not replay the verified owner action.
 p2=run(cmd);assert p2.returncode==0,(p2.stdout,p2.stderr);assert 'CHACHA_DEV_AUTONOMY_LOOP=CONVERGED' in p2.stdout,p2.stdout
 assert calls.read_text().splitlines()==rows,calls.read_text()
 # A new release-overage drift is delegated to the Intendant owner unit.
 extra=platform/'releases'/'r3';extra.mkdir();(extra/'.revision').write_text('3'*40+'\n')
 ph=run(cmd);assert ph.returncode==0,(ph.stdout,ph.stderr);assert 'CHACHA_DEV_AUTONOMY_LOOP=CONVERGED' in ph.stdout,ph.stdout
 rows2=calls.read_text().splitlines();assert rows2==rows+['chacha-dev-intendant-hygiene.service'],rows2
 assert not extra.exists()
 # A verified hygiene resolution is not replayed.
 ph2=run(cmd);assert ph2.returncode==0,(ph2.stdout,ph2.stderr);assert calls.read_text().splitlines()==rows2,calls.read_text()
 # Emergency STOP blocks before any owner dispatch.
 save(runtime/'control/emergency-stop.json',{'schema':'chacha.dev/emergency-stop-state/v1','active':True})
 p3=run(cmd);assert p3.returncode==0,(p3.stdout,p3.stderr);assert 'CHACHA_DEV_AUTONOMY_LOOP=STOPPED' in p3.stdout,p3.stdout
 assert calls.read_text().splitlines()==rows2,calls.read_text()
 state=load(runtime/'autonomy-core/loop-state.json');assert state['current_state']=='RESUME',state
 print('CHACHA_DEV_AUTONOMY_RUNNER_OWNER_DELEGATION=PASS')
 print('CHACHA_DEV_AUTONOMY_RUNNER_NO_REPLAY=PASS')
 print('CHACHA_DEV_AUTONOMY_RUNNER_INTENDANT_DELEGATION=PASS')
 print('CHACHA_DEV_AUTONOMY_RUNNER_EMERGENCY_STOP=PASS')
 print('CHACHA_DEV_AUTONOMY_RUNNER_DIRECT_MUTATION=NO')
 print('CHACHA_DEV_AUTONOMY_RUNNER_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
# Retry budget: an owner that returns success but does not resolve the issue must not loop forever.
with tempfile.TemporaryDirectory(prefix='autonomy-budget-') as raw:
 td=Path(raw);runtime=td/'runtime';platform=td/'platform';(runtime/'agent-evolution').mkdir(parents=True);(runtime/'control').mkdir(parents=True);(platform/'releases').mkdir(parents=True)
 active=None
 for n in range(3):
  d=platform/'releases'/f'r{n}';d.mkdir();(d/'.revision').write_text(str(n)*40+'\n');active=active or d
 (platform/'current').symlink_to(active);save(runtime/'control/emergency-stop.json',{'active':False})
 routing=load(CFG/'agent-routing.v1.json');seven=load(CFG/'seven-agent-final-compromise.v1.json');project=load(ROOT/'dev-hub/projects/wfgg-radar/project-agent-registry.v1.json')
 canonical=ccr.build_registry(ROOT,load(CFG/'canonical-component-registry.v1.json'));expected_fleet_count=canonical['fleet_projection_count']
 old=afo.build_report(ROOT,runtime,load(CFG/'agent-fleet-observatory.v1.json'),load(CFG/'agent-evolution.v1.json'),routing,seven,[project]);save(runtime/'agent-evolution/fleet-observatory-latest.json',old)
 calls=td/'calls';fake=td/'systemctl';fake.write_text(f'#!/bin/sh\necho "$2" >> "{calls}"\nexit 0\n');fake.chmod(0o755)
 pv=load(CFG/'autonomy-supervision.v1.json');pv['runtime']['retry_cooldown_seconds']=0;pv['runtime']['max_attempts_per_issue']=2;policy=td/'policy.json';save(policy,pv)
 cmd=[sys.executable,str(BIN/'autonomy-loop-runner.py'),'--repo-root',str(ROOT),'--runtime-root',str(runtime),'--platform-root',str(platform),'--policy',str(policy),'--systemctl-bin',str(fake),'--test-mode']
 p1=run(cmd);assert 'NEXT_STATE=RETRY_LATER' in p1.stdout,p1.stdout
 p2=run(cmd);assert 'NEXT_STATE=RETRY_LATER' in p2.stdout,p2.stdout
 p3=run(cmd);assert 'NEXT_STATE=AWAIT_HUMAN' in p3.stdout,p3.stdout
 # Two Fleet issues share one owner unit: one dispatch per run, never four.
 assert len(calls.read_text().splitlines())==2,calls.read_text()
 print('CHACHA_DEV_AUTONOMY_ATTEMPT_BUDGET=PASS')
 print('CHACHA_DEV_AUTONOMY_OWNER_DEDUPLICATION=PASS')
