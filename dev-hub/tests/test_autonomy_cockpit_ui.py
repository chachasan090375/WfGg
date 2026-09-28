#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
html=(ROOT/'dev-hub/direct-operator-ui/index.html').read_text(encoding='utf-8')
road=json.load(open(ROOT/'dev-hub/config/autonomy-gap-roadmap.v1.json'))
service=(ROOT/'dev-hub/systemd/chacha-dev-cockpit-state.service').read_text(encoding='utf-8')
publisher=(ROOT/'dev-hub/bin/cockpit-state.py').read_text(encoding='utf-8')
assert 'id="enginePanel"' in html and 'Moteur & progression' in html
assert 'id="cockpitCard"' in html and 'Cockpit ChaCha DEV' in html
assert 'Écarts à combler' in html and 'id="gapList"' in html
assert "foldIds=['enginePanel','cockpitCard','humanProfilePanel']" in html
assert 'localStorage.getItem(\'chacha-fold-\'+id)' in html
assert 'c.autonomy?.gaps' in html
assert road['schema']=='chacha.dev/autonomy-gap-roadmap/v1'
items=road.get('gaps') or []
assert len(items)>=10,len(items)
assert {x.get('status') for x in items}<={'GREEN','ORANGE','RED'}
assert any(x.get('status')=='GREEN' for x in items)
assert any(x.get('status')=='RED' for x in items)
assert 0<=int(road.get('score_percent'))<=100
assert 'autonomy_gaps' in publisher and 'autonomy-gap-roadmap.v1.json' in publisher
assert 'ReadWritePaths=/opt/chacha-dev/runtime/live-ui/current/ui /opt/chacha-dev/runtime/cockpit' in service
print('CHACHA_DEV_AUTONOMY_COCKPIT_FOLDS=PASS')
print('CHACHA_DEV_AUTONOMY_GAP_TRAFFIC_LIGHTS=PASS')
print('CHACHA_DEV_AUTONOMY_GAP_ROADMAP=PASS')
print('CHACHA_DEV_AUTONOMY_COCKPIT_DURABLE_SOURCE=PASS')
