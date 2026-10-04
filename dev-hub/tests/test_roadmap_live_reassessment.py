#!/usr/bin/env python3
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'dev-hub/bin'))
import roadmap_live_reassessment as rlr
road=json.loads((ROOT/'dev-hub/config/autonomy-gap-roadmap.v1.json').read_text())
policy=json.loads((ROOT/'dev-hub/config/roadmap-live-reassessment.v1.json').read_text())
NEW_MARKERS={
 'dev-hub/bin/adaptive-cognitive-router.py',
 'dev-hub/config/adaptive-cognitive-routing.v1.json',
 'dev-hub/config/adaptive-cognitive-gateways.v1.json',
 'dev-hub/bin/ha-standby-manifest-builder.py',
 'dev-hub/config/ha-standby-profile.v1.json',
}
def rows(out): return {x['id']:x for x in out['gaps']}
def score(out):
    vals=[int(x.get('progress') or 0) for x in out.get('gaps') or []]
    return round(sum(vals)/len(vals)) if vals else 0
def touch(root:Path,rel:str):
    p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
def materialize_baseline(root:Path):
    for rule in policy['rules'].values():
        for stage in rule.get('stages') or []:
            for rel in stage.get('required_release_paths') or []:
                if rel not in NEW_MARKERS: touch(root,rel)
    (root/'.revision').write_text('candidate-sha\n')
def materialize_train03(root:Path):
    for rel in NEW_MARKERS: touch(root,rel)
with tempfile.TemporaryDirectory(prefix='roadmap-live-release-') as rd, tempfile.TemporaryDirectory(prefix='roadmap-live-runtime-') as td:
    rel=Path(rd);rt=Path(td);materialize_baseline(rel)
    base=rlr.reassess(road,policy,rel,rt);r=rows(base)
    assert base['score_percent']==score(base),base['score_percent']
    source_provider=next(x for x in road['gaps'] if x['id']=='provider-independence')
    assert r['provider-independence']['progress']==50,r['provider-independence']
    assert r['provider-independence']['progress']>=source_provider['progress']
    assert r['provider-independence']['reassessment']['applied_stages'][-1]['target_progress']==50
    source_memory=next(x for x in road['gaps'] if x['id']=='cognitive-memory-fabric')
    assert r['cognitive-memory-fabric']['progress']==source_memory['progress']
    assert r['resilience-ha']['progress']==40
    materialize_train03(rel)
    adaptive=rlr.reassess(road,policy,rel,rt);r=rows(adaptive)
    assert r['provider-independence']['progress']==70,r['provider-independence']
    assert r['resilience-ha']['progress']==65,r['resilience-ha']
    assert adaptive['score_percent']==score(adaptive),adaptive['score_percent']
    (rt/'ha').mkdir();(rt/'ha/standby-readiness.json').write_text(json.dumps({'status':'PASS','platform_revision':'stale-sha'}))
    stale=rlr.reassess(road,policy,rel,rt);assert rows(stale)['resilience-ha']['progress']==65
    (rt/'ha/standby-readiness.json').write_text(json.dumps({'status':'PASS','platform_revision':'candidate-sha'}))
    ready=rlr.reassess(road,policy,rel,rt);rr=rows(ready)
    assert rr['resilience-ha']['progress']==80 and rr['resilience-ha']['status']=='ORANGE'
    assert ready['score_percent']==score(ready),ready['score_percent']
    (rt/'local-cognitive-fallback').mkdir();(rt/'local-cognitive-fallback/readiness.json').write_text('{"status":"PASS"}\n')
    (rt/'ha/failover-pilot.json').write_text(json.dumps({'status':'PASS','platform_revision':'candidate-sha'}))
    full=rlr.reassess(road,policy,rel,rt);rf=rows(full)
    assert rf['provider-independence']['progress']==100 and rf['provider-independence']['status']=='GREEN'
    assert rf['resilience-ha']['progress']==100 and rf['resilience-ha']['status']=='GREEN'
    assert full['score_percent']==score(full),full['score_percent']
print('CHACHA_DEV_ROADMAP_LIVE_REASSESSMENT_V2=PASS')
