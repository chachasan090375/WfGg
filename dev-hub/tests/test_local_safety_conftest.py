"""Real Conftest/OPA checks and adversarial evidence mutations, local only."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FILES=['dev-hub/bin/stop_state.py','dev-hub/bin/autonomous-project-orchestrator.py',
       'dev-hub/bin/run-controller.py','dev-hub/bin/guardian-stop-latch-reconciler.py']

def binding():
    return {'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'source_files':{x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in FILES},
            'working_tree_modified':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())}

def main():
    p=argparse.ArgumentParser();p.add_argument('--conftest',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    before=binding()
    subprocess.run([sys.executable,'-B',str(ROOT/'dev-hub/bin/local-safety-evidence.py'),
                    '--repo-root',str(ROOT),'--output',str(out/'evidence.json')],check=True)
    if binding()!=before:raise RuntimeError('SOURCE_CHANGED_DURING_COLLECTION')
    expected={'expected':before}
    (out/'expected.json').write_text(json.dumps(expected,indent=2)+'\n')
    evidence=json.loads((out/'evidence.json').read_text())
    cases=[('valid_local_evidence',evidence,None)]

    def add(name, mutate, expected_code):
        value=copy.deepcopy(evidence);mutate(value);cases.append((name,value,expected_code))

    def stop(v,name):return next(x for x in v['stop_cases'] if x['name']==name)
    def action(v,name):return next(x for x in v['action_cases'] if x['name']==name)
    def inventory(v,name):return next(x for x in v['inventory_cases'] if x['name']==name)
    add('missing_stop_allowed',lambda v:stop(v,'missing').update(blocked=False),'STOP_BEHAVIOR_INVALID_OR_INCOMPLETE')
    add('corrupted_stop_claimed_clear',lambda v:stop(v,'corrupted').update(state='CLEAR',blocked=False),'STOP_BEHAVIOR_INVALID_OR_INCOMPLETE')
    add('missing_stop_coverage',lambda v:v['stop_cases'].pop(),'STOP_BEHAVIOR_INVALID_OR_INCOMPLETE')
    add('missing_post',lambda v:action(v,'nonzero')['phases'].pop(),'ACTION_LIFECYCLE_INVALID_OR_INCOMPLETE')
    add('post_identity_drift',lambda v:action(v,'success')['action_ids'].__setitem__(1,'stage-other'),'ACTION_LIFECYCLE_INVALID_OR_INCOMPLETE')
    add('failed_child_claimed_success',lambda v:action(v,'nonzero').update(result_returned=True),'ACTION_LIFECYCLE_INVALID_OR_INCOMPLETE')
    add('execution_after_pre_denial',lambda v:action(v,'pre_denied').update(child_calls=1),'ACTION_LIFECYCLE_INVALID_OR_INCOMPLETE')
    add('success_after_post_denial',lambda v:action(v,'post_denied').update(result_returned=True),'ACTION_LIFECYCLE_INVALID_OR_INCOMPLETE')
    add('timeout_replayed',lambda v:action(v,'timeout').update(child_calls=2),'ACTION_LIFECYCLE_INVALID_OR_INCOMPLETE')
    add('saturated_inventory_accepted',lambda v:inventory(v,'at_limit').update(accepted=True),'INVENTORY_BEHAVIOR_INVALID_OR_INCOMPLETE')
    add('malformed_inventory_accepted',lambda v:inventory(v,'malformed').update(accepted=True),'INVENTORY_BEHAVIOR_INVALID_OR_INCOMPLETE')
    add('missing_inventory_coverage',lambda v:v['inventory_cases'].pop(),'INVENTORY_BEHAVIOR_INVALID_OR_INCOMPLETE')
    add('wrong_revision',lambda v:v.update(source_revision='0'*40),'SOURCE_BINDING_INVALID')
    add('wrong_module_hash',lambda v:v['source_files'].__setitem__(FILES[0],'0'*64),'SOURCE_BINDING_INVALID')
    add('hidden_working_tree_changes',lambda v:v.update(working_tree_modified=not before['working_tree_modified']),'SOURCE_BINDING_INVALID')
    add('expired_evidence',lambda v:v.update(observed_at=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()),'EVIDENCE_STALE_FUTURE_OR_INVALID')
    add('future_evidence',lambda v:v.update(observed_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()),'EVIDENCE_STALE_FUTURE_OR_INVALID')
    add('missing_timestamp',lambda v:v.pop('observed_at'),'EVIDENCE_STALE_FUTURE_OR_INVALID')
    add('production_scope_claim',lambda v:v.update(scope='PRODUCTION'),'LOCAL_SCOPE_REQUIRED')
    add('production_authority_claim',lambda v:v.update(production_authorized=True),'PRODUCTION_AUTHORITY_FORBIDDEN')
    add('wrong_schema',lambda v:v.update(schema='unknown'),'SCHEMA_INVALID')
    cases.append(('empty_self_reported_pass',{'reported_status':'PASS'},'SCHEMA_INVALID'))
    cases.append(('null_document',None,'INPUT_OBJECT_REQUIRED'))
    records=[]
    for name,value,wanted in cases:
        path=out/(name+'.json');path.write_text(json.dumps(value,indent=2)+'\n')
        r=subprocess.run([str(args.conftest.resolve()),'test',str(path),'--policy',str(ROOT/'dev-hub/policy/local-safety.rego'),
                          '--data',str(out/'expected.json'),'--output','json','--strict','--show-builtin-errors'],
                         capture_output=True,text=True,timeout=20)
        try:result=json.loads(r.stdout)
        except ValueError:raise RuntimeError('CONFTEST_EXECUTION_ERROR:'+r.stderr[:1000])
        failures=[item['msg'] for row in result for item in row.get('failures',[])]
        if wanted is None:
            if r.returncode!=0 or failures:raise AssertionError((name,r.returncode,failures,r.stderr))
        elif r.returncode==0 or wanted not in failures:
            raise AssertionError((name,wanted,r.returncode,failures,r.stderr))
        records.append({'case':name,'expected':'ACCEPT' if wanted is None else 'DENY',
                        'returncode':r.returncode,'failures':failures,'verification':'PASS'})
        (out/(name+'.conftest.json')).write_text(json.dumps(result,indent=2)+'\n')
    summary={'schema':'chacha.dev/local-safety-independent-check/v1','scope':'LOCAL_FIXTURES_ONLY',
             'production_qualification':False,'observed_at':datetime.now(timezone.utc).isoformat(),
             'conftest_version':subprocess.check_output([str(args.conftest.resolve()),'--version'],text=True).strip(),
             'binary_sha256':hashlib.sha256(args.conftest.read_bytes()).hexdigest(),
             'policy_sha256':hashlib.sha256((ROOT/'dev-hub/policy/local-safety.rego').read_bytes()).hexdigest(),
             **before,'status':'PASS','case_count':len(records),'cases':records}
    (out/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('INDEPENDENT_LOCAL_CONTROL=PASS')
    print('CASE_COUNT='+str(len(records)))
    print('PRODUCTION_QUALIFICATION=NO')

if __name__=='__main__':main()
