#!/usr/bin/env python3
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'dev-hub/bin'))
import roadmap_live_reassessment as rlr
road=json.loads((ROOT/'dev-hub/config/autonomy-gap-roadmap.v1.json').read_text())
policy=json.loads((ROOT/'dev-hub/config/roadmap-live-reassessment.v1.json').read_text())
with tempfile.TemporaryDirectory(prefix='roadmap-live-') as td:
    rt=Path(td)
    out=rlr.reassess(road,policy,ROOT,rt)
    rows={x['id']:x for x in out['gaps']}
    expected={'incident-remediation':85,'foundries':95,'learning':90,'provider-independence':50,'persistent-missions':90,'self-evolution':90,'constitution':95,'resilience-ha':40}
    for k,v in expected.items():assert rows[k]['progress']==v,(k,rows[k])
    assert rows['provider-independence']['status']=='RED'
    assert rows['resilience-ha']['status']=='RED'
    assert out['score_percent']==85,out['score_percent']
    (rt/'local-cognitive-fallback').mkdir();(rt/'local-cognitive-fallback/readiness.json').write_text('{"status":"PASS"}\n')
    (rt/'ha').mkdir();(rt/'ha/standby-readiness.json').write_text('{"status":"PASS"}\n')
    upgraded=rlr.reassess(road,policy,ROOT,rt);rows2={x['id']:x for x in upgraded['gaps']}
    assert rows2['provider-independence']['progress']==100 and rows2['provider-independence']['status']=='GREEN'
    assert rows2['resilience-ha']['progress']==100 and rows2['resilience-ha']['status']=='GREEN'
    assert upgraded['score_percent']==95,upgraded['score_percent']
print('CHACHA_DEV_ROADMAP_LIVE_REASSESSMENT=PASS')
