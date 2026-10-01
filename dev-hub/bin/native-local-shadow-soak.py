#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,statistics,subprocess,tempfile,time
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/native-local-shadow-soak-policy/v1'

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT')
    return x

def percentile95(values:list[float])->float:
    if not values:return 0.0
    if len(values)==1:return values[0]
    return statistics.quantiles(values,n=20,method='inclusive')[18]

def execute_case(adapter:Path,runtime_policy:Path,case:dict[str,Any])->tuple[dict[str,Any],float]:
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);req=td/'request.json';out=td/'response.json'
        req.write_text(json.dumps({'schema':'chacha.dev/local-cognitive-request/v1','messages':[{'role':'user','content':case['prompt']}],'max_tokens':int(case.get('max_tokens') or 64)})+'\n')
        started=time.monotonic();p=subprocess.run(['python3',str(adapter),'--policy',str(runtime_policy),'request','--input',str(req),'--output',str(out)],capture_output=True,text=True)
        latency=time.monotonic()-started
        if p.returncode!=0:raise RuntimeError('ADAPTER_REQUEST_FAILED:'+p.stderr[-400:])
        return load(out),latency

def run(policy:dict[str,Any],adapter:Path,runtime_policy:Path)->dict[str,Any]:
    if policy.get('schema')!=SCHEMA:raise ValueError('POLICY_SCHEMA_INVALID')
    rows=[];errors=[];latencies=[];steady_latencies=[];cold_latencies=[];request_index=0
    for iteration in range(int(policy['iterations'])):
        for case in policy.get('cases') or []:
            request_index+=1;warmup=request_index<=int(policy.get('warmup_requests') or 0)
            try:
                response,latency=execute_case(adapter,runtime_policy,case);content=str(response.get('content') or '')
                expected=[str(x) for x in case.get('expected_substrings') or []]
                missing=[x for x in expected if x.lower() not in content.lower()]
                passed=response.get('status')=='PASS' and not missing
                rows.append({'iteration':iteration+1,'case_id':case['id'],'pass':passed,'latency_seconds':round(latency,3),'missing':missing,'warmup':warmup})
                latencies.append(latency);(cold_latencies if warmup else steady_latencies).append(latency)
            except Exception as exc:
                errors.append({'iteration':iteration+1,'case_id':case.get('id'),'error':type(exc).__name__+':'+str(exc)[:300]})
    total=len(rows)+len(errors);passed=sum(1 for r in rows if r['pass']);rate=(passed/total) if total else 0.0
    p95=percentile95(steady_latencies);cold=max(cold_latencies) if cold_latencies else 0.0
    ok=rate>=float(policy['minimum_pass_rate']) and len(errors)<=int(policy['maximum_error_count']) and p95<=float(policy['maximum_p95_latency_seconds']) and cold<=float(policy.get('maximum_cold_start_latency_seconds') or 1e9)
    return {'schema':'chacha.dev/native-local-shadow-soak-result/v1','status':'PASS' if ok else 'BLOCK','iterations':policy['iterations'],
            'sample_count':total,'passed':passed,'pass_rate':round(rate,4),'p95_latency_seconds':round(p95,3),'cold_start_latency_seconds':round(cold,3),'errors':errors,'samples':rows,
            'production_activation_authorized':False,'automatic_external_spend_eur':0}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--adapter',type=Path,required=True);ap.add_argument('--runtime-policy',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=run(load(a.policy),a.adapter,a.runtime_policy);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
    print('CHACHA_DEV_NATIVE_LOCAL_SHADOW_SOAK='+out['status']);print('PASS_RATE='+str(out['pass_rate']));print('P95_LATENCY_SECONDS='+str(out['p95_latency_seconds']))
    print('PRODUCTION_ACTIVATION_AUTHORIZED=NO');return 0 if out['status']=='PASS' else 20

if __name__=='__main__':raise SystemExit(main())
