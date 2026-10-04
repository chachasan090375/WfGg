#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
master=json.loads((ROOT/'dev-hub/config/master-roadmap.v1.json').read_text())
hist_path=ROOT/master['historical_train_catalog']['authority']
h=json.loads(hist_path.read_text())
rows=[]
for era in h['eras']:
    rows.extend(era.get('trains') or [])
nums={int(r['train']) for r in rows if isinstance(r.get('train'),int)}
assert set(range(1,15)).issubset(nums), sorted(nums)
by={int(r['train']):r for r in rows if isinstance(r.get('train'),int)}
assert by[1]['state']=='PROMOTED_FINALIZED'
assert by[2]['state']=='PROMOTED_FINALIZED'
assert by[3]['state'].startswith('PROMOTED_FINALIZED')
assert by[4]['state']=='QUALIFIED_HOLD_NOT_PROMOTED'
assert by[5]['state']=='PREPARED_SHADOW_NOT_PROMOTED'
for n in range(6,13):
    assert 'ABSORBED' in by[n]['state'] or 'CONVOY_CLOSURE' in by[n]['state']
assert master['historical_train_catalog']['numbering_warning'].startswith('HISTORICAL_RELEASE_TRAIN_NUMBERS')
assert h['retention_rule'].startswith('Never drop a historical train')
print('CHACHA_DEV_MASTER_ROADMAP_TRAIN_HISTORY=PASS')
print('HISTORICAL_TRAINS_01_14_PRESENT=PASS')
print('HISTORICAL_AND_CURRENT_NUMBERING_SEPARATED=PASS')
