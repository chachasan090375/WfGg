#!/usr/bin/env python3
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'bin/native-local-resource-admission.py'
s=importlib.util.spec_from_file_location('adm',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
POL=json.load(open(ROOT/'config/native-local-resource-admission.v1.json'))
RUN=json.load(open(ROOT/'config/local-cognitive-runtime.v1.json'))

def test_healthy_snapshot_passes():
    x=m.decide(POL,RUN,{'available_memory_mb':1200,'free_disk_mb':10000,'cpu_count':2,'load1':0.4})
    assert x['status']=='PASS' and x['fallback_required'] is False
    assert x['production_activation_authorized'] is False

def test_memory_pressure_blocks():
    x=m.decide(POL,RUN,{'available_memory_mb':700,'free_disk_mb':10000,'cpu_count':2,'load1':0.2})
    assert x['status']=='BLOCK' and 'MEMORY_HEADROOM_INSUFFICIENT' in x['reasons']

def test_cpu_pressure_blocks():
    x=m.decide(POL,RUN,{'available_memory_mb':1200,'free_disk_mb':10000,'cpu_count':2,'load1':4.0})
    assert x['status']=='BLOCK' and 'CPU_LOAD_TOO_HIGH' in x['reasons']

def test_parallelism_is_bounded():
    run=json.loads(json.dumps(RUN));run['limits']['parallel_slots']=2
    x=m.decide(POL,run,{'available_memory_mb':1200,'free_disk_mb':10000,'cpu_count':2,'load1':0.2})
    assert 'PARALLEL_SLOTS_EXCEED_POLICY' in x['reasons']
