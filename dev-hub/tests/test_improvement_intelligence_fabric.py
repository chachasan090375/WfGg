#!/usr/bin/env python3
import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; BIN=ROOT/'dev-hub/bin'; CFG=ROOT/'dev-hub/config'
s=importlib.util.spec_from_file_location('iif',BIN/'improvement_intelligence_fabric.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
p=json.load(open(CFG/'improvement-intelligence-fabric.v1.json'))
# Cross-agent corroboration creates one axis, not duplicate value inflation.
signals=[
 {'signal_id':'a','source_agent':'technology-watch','capability':'durable-execution','claim':'Checkpoint long tasks','confidence':90,'evidence_refs':['e1'],'source_timestamp':'2026-10-04T00:00:00Z','provenance_verified':True,'architecture_fit':True,'global_value_score':80,'value_dimensions':{'reliability':20}},
 {'signal_id':'b','source_agent':'sentinel','capability':'durable-execution','claim':'Checkpoint long tasks','confidence':95,'evidence_refs':['e2'],'source_timestamp':'2026-10-04T00:00:00Z','provenance_verified':True,'runtime_local_signal':True,'architecture_fit':True,'global_value_score':85,'value_dimensions':{'reliability':20}}
]
canon=[]
for i,x in enumerate(signals):canon+=m.canonical_signal({'schema':'chacha.dev/improvement-signal/v1',**x},Path(f'/tmp/{i}.json'),p)
out=m.synthesize(canon,p);assert out['axis_count']==1,out;assert out['items'][0]['recommendation']=='IMPROVEMENT_CANDIDATE',out
print('test_cross_agent_fusion_one_axis=PASS')
# Dark intelligence alone can never become candidate.
d=m.canonical_signal({'schema':'chacha.dev/improvement-signal/v1','signal_id':'d','source_agent':'dark-intelligence','capability':'sandbox','claim':'Novel sandbox','confidence':99,'evidence_refs':['dark1'],'source_timestamp':'2026-10-04T00:00:00Z','provenance_verified':True,'architecture_fit':True,'global_value_score':95,'value_dimensions':{'security':15}},Path('/tmp/d.json'),p)
o=m.synthesize(d,p);assert o['items'][0]['recommendation']!='IMPROVEMENT_CANDIDATE',o
print('test_dark_requires_independent_corroboration=PASS')
# Novelty with no measurable platform value is rejected.
n=m.canonical_signal({'schema':'chacha.dev/improvement-signal/v1','signal_id':'n','source_agent':'competitive-watch','capability':'novel-widget','claim':'New shiny widget','confidence':90,'evidence_refs':['n1'],'source_timestamp':'2026-10-04T00:00:00Z','provenance_verified':True,'architecture_fit':True,'global_value_score':10,'value_dimensions':{}},Path('/tmp/n.json'),p)
o=m.synthesize(n,p);assert o['items'][0]['recommendation']=='IGNORE',o
print('test_novelty_without_global_value_rejected=PASS')
print('CHACHA_DEV_IMPROVEMENT_INTELLIGENCE_TESTS=3/3 PASS')
