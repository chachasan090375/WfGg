#!/usr/bin/env python3
import json,tempfile,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'dev-hub/bin'))
import improvement_intelligence_fabric as iif, improvement_intelligence_cycle as cyc
POL=json.load(open(ROOT/'dev-hub/config/improvement-intelligence-fabric.v1.json'))
truth={'schema':'chacha.dev/technology-truth-score/v1','technology_id':'durable-execution','version':'1.2.3','technical_truth_score':96,'architecture_fit_score':90,'recommendation_class':'ADOPT'}
with tempfile.TemporaryDirectory() as td:
    t=Path(td);tp=t/'truth.json';tp.write_text(json.dumps(truth)+'\n')
    ts=iif.canonical_signal(truth,tp,POL);one=iif.synthesize(ts,POL)
    assert one['axis_count']==1 and one['items'][0]['recommendation']!='IMPROVEMENT_CANDIDATE',one
    assert 'GLOBAL_VALUE_SCORE_TOO_LOW' in one['items'][0]['reason_codes'],one
    comparative={'schema':'chacha.dev/improvement-signal/v1','signal_id':'benchmark:durable','source_agent':'benchmark-fabric','capability':'durable-execution','mechanism_id':'external-durable-ledger','claim':'Measured reduction of failed long-running tasks','confidence':94,'evidence_refs':['benchmark:1'],'source_timestamp':'2026-10-04T00:00:00Z','provenance_verified':True,'architecture_fit':True,'global_value_score':92,'value_dimensions':{'reliability':20,'autonomy':20},'source_strategy':'OWNED_REIMPLEMENTATION','target_component_id':'central-orchestrator','candidate_owner':'branch-foundry'}
    cs=iif.canonical_signal(comparative,t/'benchmark.json',POL);both=iif.synthesize(ts+cs,POL)
    assert both['axis_count']==1,both
    axis=both['items'][0];assert axis['recommendation']=='IMPROVEMENT_CANDIDATE' and axis['improvement_request_authorized'] is True,axis
    assert {'technology-truth','benchmark-fabric'}<=set(axis['source_agents']),axis
print('test_truth_alone_is_not_product_value=PASS')
print('test_truth_plus_measured_global_gain_can_create_candidate=PASS')

# Prove bounded live runtime truth files are automatically ingested by the central cycle.
with tempfile.TemporaryDirectory() as td:
    tmp=Path(td);repo=tmp/'repo';shutil.copytree(ROOT/'dev-hub',repo/'dev-hub');runtime=tmp/'runtime'
    d=runtime/'technology-watch/example/evaluation';d.mkdir(parents=True);(d/'technology-truth-score.json').write_text(json.dumps(truth)+'\n')
    sigdir=runtime/'improvement-intelligence/signals';sigdir.mkdir(parents=True);(sigdir/'benchmark.json').write_text(json.dumps(comparative)+'\n')
    out=cyc.run(repo,runtime);assert out['runtime_source_ingested_count']==1,out
    assert out['improvement_candidate_count']==1 and out['new_reassessment_request_count']==1,out
    reqs=list((runtime/'platform-evolution/reassessment-queue').glob('improvement-*.json'));assert len(reqs)==1,reqs
    req=json.loads(reqs[0].read_text());assert req['shadow_required'] is True and req['production_authority'] is False and req['self_promotion'] is False,req
print('test_live_truth_runtime_ingests_into_shadow_evolution_queue=PASS')
print('CHACHA_DEV_TECHNOLOGY_TRUTH_IMPROVEMENT_FUSION=3/3 PASS')
