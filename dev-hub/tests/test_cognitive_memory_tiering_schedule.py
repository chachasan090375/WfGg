from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('tier',ROOT/'dev-hub/bin/cognitive-memory-tiering.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
POL=json.loads((ROOT/'dev-hub/config/cognitive-memory-fabric.v1.json').read_text())

def test_schedule_is_three_hour_plus_events_without_hot_purge():
 t=POL['tiering'];assert t['interval_seconds']==10800;assert t['schedule_mode']=='INTERVAL_PLUS_EVENTS'
 assert t['hot_purge_automatic'] is False;assert t['hot_demote_automatic'] is False
 assert 'MISSION_ACCEPTED_COMPLETE' in t['event_triggers'];assert 'AGENT_SPECIALIST_CORPUS_UPDATED' in t['event_triggers']
def test_plan_only_archives_material_change():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);(root/'a.db').write_bytes(b'a');p=m.plan(POL,'INTERVAL',root,{'digests':{}});assert p['material_change'] is True and len(p['changed'])==1
  p2=m.plan(POL,'INTERVAL',root,{'digests':p['observed_digests']});assert p2['material_change'] is False and p2['changed']==[]
def test_ledger_tracks_all_observed_digests():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);(root/'a.db').write_bytes(b'a');(root/'b.db').write_bytes(b'b')
  p=m.plan(POL,'MEMORY_PROMOTED_TRUSTED',root,{'digests':{str(root/'a.db'):m.sha(root/'a.db')}})
  assert len(p['observed_digests'])==2 and len(p['changed'])==1
def test_unknown_trigger_fails_closed():
 with tempfile.TemporaryDirectory() as td:
  try:m.plan(POL,'WHATEVER',Path(td),{'digests':{}});raise AssertionError('expected block')
  except ValueError as e:assert 'TRIGGER_NOT_ALLOWED' in str(e)
def test_systemd_timer_is_three_hours_and_shadow_execute():
 timer=(ROOT/'dev-hub/systemd/chacha-dev-cognitive-memory-tiering.timer').read_text();svc=(ROOT/'dev-hub/systemd/chacha-dev-cognitive-memory-tiering.service').read_text()
 assert 'OnUnitActiveSec=3h' in timer;assert '--shadow-execute' in svc
if __name__=='__main__':
 n=0
 for name,fn in sorted(globals().items()):
  if name.startswith('test_'):fn();print(name+'=PASS');n+=1
 print('CHACHA_DEV_COGNITIVE_MEMORY_TIERING_SCHEDULE=PASS');print('TEST_COUNT='+str(n));print('HOT_PURGE_AUTOMATIC=NO')
