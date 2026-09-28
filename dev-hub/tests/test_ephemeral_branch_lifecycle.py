from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; BIN=ROOT/'dev-hub/bin'

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
mod=loadmod('ephemeral_branch_lifecycle',BIN/'ephemeral_branch_lifecycle.py')
with tempfile.TemporaryDirectory() as td:
    td=Path(td);runtime=td/'runtime';caps=runtime/'capsules';caps.mkdir(parents=True);(runtime/'control').mkdir();(runtime/'control/emergency-stop.json').write_text('{"active":false}\n')
    rows=[]
    for branch,cid in [('p:graphics:primary',None),('p:qa:review','runtime:p-qa-review')]:
        token=__import__('hashlib').sha256(branch.encode()).hexdigest()[:16];ws=caps/token;ws.mkdir();(ws/'evidence.txt').write_text('KEEP')
        rows.append({'schema':'chacha.dev/runtime-capsule-manifest/v1','branch_id':branch,'unit':mod.unit_for(branch),'workspace':str(ws),'state':'ACTIVE','ttl_seconds':60,'created_at':'2026-01-01T00:00:00Z','materialization_component_id':cid})
    (caps/'registry.json').write_text(json.dumps({'schema':'chacha.dev/runtime-capsule-registry/v1','capsules':rows})+'\n')
    fake_systemctl=td/'systemctl.py';fake_systemctl.write_text('#!/usr/bin/env python3\nimport sys\nprint("inactive")\nsys.exit(3)\n');fake_systemctl.chmod(0o755)
    fake_guardian=td/'guardian.py';fake_guardian.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps({"verdict":"PASS"}))\n');fake_guardian.chmod(0o755)
    fake_gate=td/'gate.py';fake_gate.write_text('#!/usr/bin/env python3\nimport json,sys,pathlib\na=sys.argv;out=pathlib.Path(a[a.index("--output")+1]);out.write_text(json.dumps({"status":"PASS","component_state":"RETIRED"})+"\\n");pathlib.Path(__file__).with_suffix(".calls").open("a").write(" ".join(a)+"\\n")\n');fake_gate.chmod(0o755)
    policy=td/'policy.json';policy.write_text('{}\n');dyn=td/'dynamic.json';dyn.write_text('{"schema":"chacha.dev/dynamic-component-registry/v1","registrations":[],"history":[]}\n')
    before=mod.observe(runtime,json.load(open(ROOT/'dev-hub/config/branch-foundry.v1.json')),fake_systemctl)
    assert before['issue_count']==2,before
    assert {x['code'] for x in before['issues']}=={'EPHEMERAL_BRANCH_STALE'},before
    out=mod.reconcile(ROOT,runtime,fake_systemctl,fake_guardian,policy,fake_gate,policy,dyn)
    assert out['status']=='PASS' and len(out['actions'])==2,out
    assert all(x['status']=='VERIFIED' for x in out['actions']),out
    reg=json.load(open(caps/'registry.json'))
    assert all(x['state']=='RETIRED' for x in reg['capsules']),reg
    assert all(Path(x['workspace']).is_dir() for x in reg['capsules']),reg
    assert all((Path(x['workspace'])/'evidence.txt').read_text()=='KEEP' for x in reg['capsules'])
    assert (fake_gate.with_suffix('.calls')).read_text().count('--mode retire')==1
    after=mod.observe(runtime,json.load(open(ROOT/'dev-hub/config/branch-foundry.v1.json')),fake_systemctl)
    assert after['issue_count']==0,after
    # Active beyond TTL is deliberately not auto-retired.
    branch='p:live:primary';token=__import__('hashlib').sha256(branch.encode()).hexdigest()[:16];ws=caps/token;ws.mkdir()
    (caps/'registry.json').write_text(json.dumps({'schema':'chacha.dev/runtime-capsule-registry/v1','capsules':[{'branch_id':branch,'unit':mod.unit_for(branch),'workspace':str(ws),'state':'ACTIVE','ttl_seconds':60,'created_at':'2026-01-01T00:00:00Z'}]})+'\n')
    active_systemctl=td/'active-systemctl.py';active_systemctl.write_text('#!/usr/bin/env python3\nprint("active")\n');active_systemctl.chmod(0o755)
    live=mod.observe(runtime,json.load(open(ROOT/'dev-hub/config/branch-foundry.v1.json')),active_systemctl)
    assert [x['code'] for x in live['issues']]==['EPHEMERAL_BRANCH_TTL_EXCEEDED_ACTIVE'],live
print('CHACHA_DEV_EPHEMERAL_BRANCH_LIFECYCLE_TEST=PASS')
