import importlib.util,json,pathlib,tempfile,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cut',ROOT/'bin/learning-lineage-cutover-gate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
policy=json.loads((ROOT/'config/learning-lineage-cutover-gate.v1.json').read_text())
def ledger(path,history):
    path.write_text(json.dumps({'schema':'chacha.dev/evidence-ledger/v1','project':'p','history':history}));return path
def ev(ts,ctx):
    return {'event':'task-result-ingested','result_status':'OK','verification_status':'VERIFIED','result_digest':'sha256:x','learning_context':ctx,'observed_at':ts}
def goodctx():return {'component_lineage':{'schema':'chacha.dev/component-lineage/v1','components':[{'kind':'agent','component_id':'x','version':'1'}]}}
def test_historical_quarantine_passes():
    with tempfile.TemporaryDirectory() as raw:
        td=pathlib.Path(raw);lp=ledger(td/'l.json',[ev('2026-09-26T00:00:00+00:00',None),ev('2026-09-28T00:00:00+00:00',goodctx())]);cov={'results':[{'ledger':str(lp),'project_id':'p'}],'missing_context_count':1};out=m.gate(policy,cov,ROOT.parent);assert out['status']=='PASS' and out['historical_missing_quarantined']==1 and out['missing_after_cutover']==0
def test_post_cutover_missing_holds():
    with tempfile.TemporaryDirectory() as raw:
        td=pathlib.Path(raw);lp=ledger(td/'l.json',[ev('2026-09-28T00:00:00+00:00',None)]);cov={'results':[{'ledger':str(lp),'project_id':'p'}],'missing_context_count':1};out=m.gate(policy,cov,ROOT.parent);assert out['status']=='HOLD' and 'MISSING_CONTEXT_AFTER_CUTOVER' in out['blockers']
def test_invalid_timestamp_holds():
    with tempfile.TemporaryDirectory() as raw:
        td=pathlib.Path(raw);lp=ledger(td/'l.json',[ev('bad',None)]);cov={'results':[{'ledger':str(lp),'project_id':'p'}],'missing_context_count':0};out=m.gate(policy,cov,ROOT.parent);assert out['status']=='HOLD' and 'INVALID_TIMESTAMP_EVENTS' in out['blockers']
if __name__=='__main__':
    for n,f in sorted(globals().items()):
        if n.startswith('test_'):f();print(n+'=PASS')
