#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/domain-readiness-auto-remediation/v1'
POLICY_SCHEMA='chacha.dev/adapter-auto-remediation/v1'
DYNAMIC_SCHEMA='chacha.dev/dynamic-component-registry/v1'
RESULT_SCHEMA='chacha.dev/task-result/v1'
HEALTH_SCHEMA='chacha.dev/provider-health-snapshot/v1'

def now_iso()->str:return datetime.now(timezone.utc).isoformat()
def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(path))
    return x
def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');os.replace(tmp,path)
def digest(x:Any)->str:
    raw=json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode();return 'sha256:'+hashlib.sha256(raw).hexdigest()
def file_digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return 'sha256:'+h.hexdigest()
def run(argv:list[str],cwd:Path,timeout:int=90)->subprocess.CompletedProcess[str]:
    return subprocess.run(argv,cwd=str(cwd),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,shell=False,timeout=timeout)
def evidence(status:str,source:str,details:dict[str,Any])->dict[str,Any]:return {'status':status,'source':source,'observed_at':now_iso(),'details':details}

ATTEST_SCHEMA='chacha.dev/provider-zero-cost-attestation/v1'

def economics_blockers(profile:dict[str,Any],provider:str)->list[str]:
    if profile.get('zero_cost_attestation_required') is not True:return []
    raw=str(profile.get('zero_cost_attestation') or '').strip()
    if not raw:return ['ZERO_COST_ATTESTATION_PATH_MISSING']
    path=Path(raw)
    if not path.is_file():return ['ZERO_COST_ATTESTATION_MISSING']
    try:x=load(path)
    except Exception:return ['ZERO_COST_ATTESTATION_INVALID']
    if x.get('schema')!=ATTEST_SCHEMA or x.get('provider_id')!=provider:return ['ZERO_COST_ATTESTATION_INVALID']
    if x.get('status')!='PASS':
        reasons=[str(v) for v in (x.get('reason_codes') or [])]
        if 'PROVIDER_MODEL_QUOTA_EXHAUSTED' in reasons:return ['PROVIDER_MODEL_QUOTA_EXHAUSTED']
        return ['ZERO_COST_ATTESTATION_INVALID']
    try:spend=float(x.get('automatic_external_spend_eur'))
    except Exception:spend=-1
    if spend!=0:return ['ZERO_COST_ATTESTATION_NONZERO_SPEND']
    cost=str(x.get('cost_class') or '').lower();allowed={str(v).lower() for v in (profile.get('allowed_zero_cost_classes') or ['free','owned','included','local'])}
    if cost not in allowed:return ['COST_CLASS_NOT_AUTOMATIC_ZERO']
    if cost=='quota':
        if x.get('quota_available') is not True:return ['FREE_QUOTA_NOT_CONFIRMED']
        try:expiry=datetime.fromisoformat(str(x.get('valid_until') or '').replace('Z','+00:00'))
        except Exception:return ['ZERO_COST_ATTESTATION_EXPIRED']
        if expiry<=datetime.now(timezone.utc):return ['ZERO_COST_ATTESTATION_EXPIRED']
    return []

def refresh_zero_cost_attestation(repo:Path,runtime:Path,profile:dict[str,Any],provider:str,work:Path)->dict[str,Any]:
    probe=profile.get('zero_cost_attestation_probe') if isinstance(profile.get('zero_cost_attestation_probe'),dict) else {}
    if probe.get('enabled') is not True:return {'status':'NOT_CONFIGURED'}
    if probe.get('non_generative') is not True or float(probe.get('automatic_external_spend_eur') or 0)!=0:return {'status':'BLOCKED','reason':'ECONOMICS_PROBE_NOT_ZERO_SPEND'}
    tool=repo/str(probe.get('tool') or '')
    output=Path(str(profile.get('zero_cost_attestation') or ''))
    if not tool.is_file() or not str(output):return {'status':'BLOCKED','reason':'ECONOMICS_PROBE_CONTRACT_INVALID'}
    cmd=[sys.executable,str(tool),'--provider',provider,'--runtime-root',str(runtime),'--output',str(output),'--valid-seconds',str(int(probe.get('valid_seconds') or 300)),'--minimum-remaining-fraction',str(float(probe.get('minimum_remaining_fraction') or 0.01))]
    proc=run(cmd,repo,90)
    att=load(output) if output.is_file() else None
    row={'status':'PASS' if proc.returncode==0 and isinstance(att,dict) and att.get('status')=='PASS' else 'BLOCK','returncode':proc.returncode,'attestation':str(output),'stdout_digest':'sha256:'+hashlib.sha256(proc.stdout.encode()).hexdigest(),'stderr_digest':'sha256:'+hashlib.sha256(proc.stderr.encode()).hexdigest(),'automatic_external_spend_eur':0}
    if isinstance(att,dict):row.update({'quota_available':att.get('quota_available'),'quota_remaining_fraction':att.get('quota_remaining_fraction'),'valid_until':att.get('valid_until'),'auth_mode':att.get('auth_mode'),'overage_enabled':att.get('overage_enabled'),'reason_codes':att.get('reason_codes') or [],'resume_at':att.get('resume_at'),'model':att.get('model')})
    save(work/(provider+'.zero-cost-attestation-refresh.json'),row);return row

def selected_targets(readiness:dict[str,Any])->list[tuple[str,str,str]]:
    out=[];seen=set();actionable={'ADAPTER_ENABLEMENT_REQUIRED','PROVIDER_HEALTH_PROBE_REQUIRED'}
    for task in readiness.get('tasks') or []:
        if not isinstance(task,dict) or task.get('gate') not in actionable:continue
        c=task.get('selected_candidate') if isinstance(task.get('selected_candidate'),dict) else {}
        key=(str(c.get('adapter_id') or ''),str(c.get('provider') or task.get('selected_provider') or ''),str(task.get('gate') or ''))
        if all(key) and key not in seen:seen.add(key);out.append(key)
    return out

def eligibility(adapter:str,provider:str,registry:dict[str,Any],provisioning:dict[str,Any],policy:dict[str,Any])->tuple[bool,list[str],dict[str,Any]]:
    blockers=[];profile=(policy.get('profiles') or {}).get(adapter);a=(registry.get('adapters') or {}).get(adapter);p=(registry.get('providers') or {}).get(provider)
    if not isinstance(profile,dict) or profile.get('enabled') is not True:blockers.append('AUTO_REMEDIATION_PROFILE_NOT_ENABLED')
    if not isinstance(a,dict):blockers.append('ADAPTER_NOT_REGISTERED');a={}
    if not isinstance(p,dict) or p.get('adapter')!=adapter:blockers.append('PROVIDER_BINDING_MISMATCH');p={}
    prod=set(policy.get('production_permissions') or [])
    if set(a.get('supports') or []) & prod:blockers.append('PRODUCTION_CAPABLE_ADAPTER_REQUIRES_HUMAN_APPROVAL')
    if p.get('execution')!='vps':blockers.append('LOCAL_GOVERNED_EXECUTION_REQUIRED')
    if adapter not in (provisioning.get('adapters') or {}):blockers.append('PROVISIONING_CONTRACT_MISSING')
    if isinstance(profile,dict):
        if provider not in set(str(x) for x in profile.get('provider_allowlist') or []):blockers.append('PROVIDER_NOT_IN_AUTO_REMEDIATION_ALLOWLIST')
        if profile.get('non_destructive_probe') is not True:blockers.append('NON_DESTRUCTIVE_PROBE_NOT_ATTESTED')
        if float(profile.get('automatic_external_spend_eur') or 0)!=0:blockers.append('AUTOMATIC_EXTERNAL_SPEND_NONZERO')
        blockers.extend(economics_blockers(profile,provider))
    return not blockers,sorted(set(blockers)),profile or {}

def materialize_effective(repo:Path,runtime:Path,work:Path)->Path:
    out=work/'effective-provider-adapters.v1.json';report=work/'runtime-adapter-reconciliation.json'
    state=runtime/'registries/provider-adapter-runtime-state.v1.json';base=repo/'dev-hub/config/provider-adapters.v1.json'
    proc=run([sys.executable,str(repo/'dev-hub/bin/runtime-adapter-registry.py'),'effective','--base',str(base),'--state',str(state),'--output',str(out),'--report',str(report)],repo)
    if proc.returncode!=0 or not out.is_file():raise RuntimeError('RUNTIME_ADAPTER_REGISTRY_RECONCILIATION_FAILED')
    return out

def persist_state(repo:Path,runtime:Path,registry:Path,adapter:str,work:Path,evidence_refs:list[str])->None:
    entry=((load(registry).get('adapters') or {}).get(adapter) or {});status=str(entry.get('status') or '');exe=entry.get('executable');ed=file_digest(Path(exe)) if isinstance(exe,str) and Path(exe).is_file() else None
    out=work/(adapter+'.runtime-state-receipt.json');cmd=[sys.executable,str(repo/'dev-hub/bin/runtime-adapter-registry.py'),'set','--base',str(repo/'dev-hub/config/provider-adapters.v1.json'),'--state',str(runtime/'registries/provider-adapter-runtime-state.v1.json'),'--adapter',adapter,'--status',status,'--output',str(out)]
    if exe:cmd+=['--executable',str(exe)]
    if ed:cmd+=['--executable-digest',ed]
    for ref in evidence_refs:cmd+=['--evidence-ref',ref]
    proc=run(cmd,repo)
    if proc.returncode!=0:raise RuntimeError('RUNTIME_ADAPTER_STATE_PERSIST_FAILED:'+adapter)

def ensure_umg(repo:Path,runtime:Path,adapter:str,entry:dict[str,Any],work:Path)->dict[str,Any]:
    dynamic=runtime/'canonical-registry/dynamic-components.json';cid='integration:'+adapter
    state=load(dynamic) if dynamic.is_file() else {'schema':DYNAMIC_SCHEMA,'registrations':[],'history':[]}
    prior=next((x for x in state.get('registrations') or [] if isinstance(x,dict) and x.get('component_id')==cid),None)
    if prior:return {'status':'ALREADY_REGISTERED','component_id':cid,'component_state':prior.get('status')}
    manifest={'component_id':adapter,'governance_class':'CONNECTOR_ADAPTER','owner_foundry':'capability-foundry','materialization_gate_required':True,'purpose':'Governed provider adapter '+adapter,'scope':'PLATFORM','permissions':entry.get('supports') or [],'health_contract':'NON_DESTRUCTIVE_RUNTIME_PROBE','compatibility':'ADAPTER_CONTRACT_AND_PROVIDER_HEALTH_REQUIRED','lifecycle':'MATERIALIZING','automatic_external_spend_eur':0}
    mp=work/(adapter+'.umg-manifest.json');rp=work/(adapter+'.umg-register.json');save(mp,manifest)
    proc=run([sys.executable,str(repo/'dev-hub/bin/universal-materialization-gate.py'),'--mode','register','--manifest',str(mp),'--policy',str(repo/'dev-hub/config/canonical-component-registry.v1.json'),'--operator-directives',str(repo/'dev-hub/config/operator-directives.v1.json'),'--dynamic-registry',str(dynamic),'--output',str(rp)],repo)
    if proc.returncode!=0 or not rp.is_file():raise RuntimeError('UMG_REGISTER_FAILED:'+adapter)
    return load(rp)

def static_contract(repo:Path,registry:Path,adapter:str,work:Path)->Path:
    report=work/(adapter+'.static-contract.json');proc=run([sys.executable,str(repo/'dev-hub/bin/adapter-contract-harness.py'),'--registry',str(registry),'--policy',str(repo/'dev-hub/config/adapter-contract.v1.json'),'--report',str(report),'--adapter',adapter],repo)
    x=load(report) if report.is_file() else {}
    if proc.returncode!=0 or ((x.get('static') or {}).get('status')!='PASS'):raise RuntimeError('STATIC_CONTRACT_FAILED:'+adapter)
    return report

def promote(repo:Path,registry:Path,adapter:str,target:str,evidence_path:Path,work:Path,executable:str|None=None)->Path:
    receipt=work/(adapter+'.'+target.casefold()+'.promotion-receipt.json');cmd=[sys.executable,str(repo/'dev-hub/bin/adapter-promotion.py'),'--registry',str(registry),'--contract',str(repo/'dev-hub/config/adapter-contract.v1.json'),'--policy',str(repo/'dev-hub/config/adapter-promotion.v1.json'),'--evidence',str(evidence_path),'apply','--adapter',adapter,'--target',target,'--actor','capability-foundry:auto-remediator','--receipt',str(receipt),'--apply']
    if executable:cmd+=['--executable',executable]
    proc=run(cmd,repo)
    if proc.returncode!=0:raise RuntimeError('PROMOTION_FAILED:'+adapter+':'+target+':'+proc.stdout[-500:]+proc.stderr[-500:])
    return receipt

def ensure_contract_ok(repo:Path,registry:Path,adapter:str,work:Path)->list[str]:
    entry=((load(registry).get('adapters') or {}).get(adapter) or {});refs=[]
    report=static_contract(repo,registry,adapter,work);refs.append(str(report))
    if entry.get('status')!='DESIGNED':return refs
    static=(load(report).get('static') or {});ep=work/(adapter+'.contract-ok-evidence.json')
    save(ep,{'schema':'chacha.dev/adapter-promotion-evidence/v1','adapter':adapter,'observed_at':now_iso(),'evidence':{'static-contract-pass':evidence('PASS',str(report),{'static_status':static.get('status'),'failures':static.get('failures')})},'approvals':[]})
    refs += [str(ep),str(promote(repo,registry,adapter,'CONTRACT_OK',ep,work))];return refs

def provision(repo:Path,adapter:str,work:Path)->dict[str,Any]:
    receipt=work/(adapter+'.provisioning-receipt.json');proc=run([sys.executable,str(repo/'dev-hub/bin/adapter-provision.py'),'--policy',str(repo/'dev-hub/config/adapter-provisioning.v1.json'),'apply','--adapter',adapter,'--actor','capability-foundry:auto-remediator','--receipt',str(receipt),'--apply'],repo,120)
    if proc.returncode!=0 or not receipt.is_file():raise RuntimeError('PROVISIONING_FAILED:'+adapter+':'+proc.stderr[-600:])
    verify=run([sys.executable,str(repo/'dev-hub/bin/adapter-provision.py'),'--policy',str(repo/'dev-hub/config/adapter-provisioning.v1.json'),'verify','--adapter',adapter,'--receipt',str(receipt)],repo,60);x=load(receipt)
    if verify.returncode!=0 or ((x.get('probe') or {}).get('status')!='PASS'):raise RuntimeError('PROVISIONING_VERIFY_FAILED:'+adapter)
    return x

def runtime_probe_fixture(repo:Path,adapter:str,provider:str)->dict[str,Any]:
    spec=((load(repo/'dev-hub/config/adapter-provisioning.v1.json').get('adapters') or {}).get(adapter) or {})
    fixture=((spec.get('probe') or {}).get('input'))
    if not isinstance(fixture,dict):raise RuntimeError('PROVISIONING_PROBE_FIXTURE_MISSING:'+adapter)
    fixture=json.loads(json.dumps(fixture))
    bindings=fixture.get('bindings') if isinstance(fixture.get('bindings'),list) else []
    if not any(isinstance(x,dict) and x.get('provider')==provider and x.get('adapter')==adapter for x in bindings):
        bindings.append({'provider':provider,'adapter':adapter,'health_state':'HEALTHY','fallback_used':False})
    fixture['bindings']=bindings
    return fixture

def run_positive_probe(repo:Path,adapter:str,provider:str,exe:str,work:Path,label:str)->Path:
    fixture=runtime_probe_fixture(repo,adapter,provider)
    proc=subprocess.run([exe],input=json.dumps(fixture,ensure_ascii=False),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,shell=False,timeout=30)
    try:x=json.loads(proc.stdout.strip())
    except Exception:raise RuntimeError('RUNTIME_PROBE_RESULT_INVALID:'+adapter)
    if proc.returncode!=0 or x.get('schema')!=RESULT_SCHEMA or x.get('status')!='OK' or x.get('producer')!=adapter:
        raise RuntimeError('RUNTIME_PROBE_RESULT_FAILED:'+adapter+':'+str(x.get('summary') or proc.returncode))
    p=work/(adapter+'.'+label+'.json');save(p,x);return p

def ensure_pilot(repo:Path,registry:Path,adapter:str,provider:str,profile:dict[str,Any],work:Path,prov:dict[str,Any])->tuple[str,list[str]]:
    entry=((load(registry).get('adapters') or {}).get(adapter) or {});exe=str(prov.get('executable_path') or '');refs=[]
    if entry.get('status')!='CONTRACT_OK':return str(entry.get('executable') or exe),refs
    if float(profile.get('automatic_external_spend_eur') or 0)!=0:raise RuntimeError('PILOT_NONZERO_EXTERNAL_SPEND:'+adapter)
    runtime_result=run_positive_probe(repo,adapter,provider,exe,work,'pilot-runtime-result')
    rx=load(runtime_result)
    details={'executable_path':exe,'executable_digest':prov.get('executable_digest'),'source_digest':prov.get('source_digest'),'installed_digest':prov.get('installed_digest'),'execution':'vps','non_destructive_probe':True,'automatic_external_spend_eur':0};ep=work/(adapter+'.pilot-evidence.json')
    save(ep,{'schema':'chacha.dev/adapter-promotion-evidence/v1','adapter':adapter,'observed_at':now_iso(),'evidence':{'runtime-contract-pass':evidence('PASS',str(runtime_result),{'status':rx.get('status'),'producer':rx.get('producer'),'verification_status':((rx.get('verification') or {}).get('status'))}),'sandbox-only':evidence('PASS','adapter-auto-remediation-policy',{'constrained_non_destructive_probe':True,'production_permissions':False,'external_network':profile.get('external_network'),'automatic_external_spend_eur':0}),'provisioning-pass':evidence('PASS',str(work/(adapter+'.provisioning-receipt.json')),details)},'approvals':[]})
    refs += [str(runtime_result),str(ep),str(promote(repo,registry,adapter,'PILOT',ep,work,exe))];return exe,refs

def repeatable_results(repo:Path,adapter:str,provider:str,exe:str,work:Path,global_health:Path|None=None)->tuple[list[Path],Path]:
    fixture=runtime_probe_fixture(repo,adapter,provider)
    policy=load(repo/'dev-hub/config/adapter-auto-remediation.v1.json')
    profile=((policy.get('profiles') or {}).get(adapter) or {})
    rp=profile.get('repeatability_probe') if isinstance(profile.get('repeatability_probe'),dict) else {}
    required=max(1,min(5,int(rp.get('required_successes') or 3)))
    transient_retries=max(0,min(3,int(rp.get('transient_retries_per_success') or 0)))
    retry_delay=max(0.0,min(5.0,float(rp.get('retry_delay_seconds') or 0.0)))
    success_spacing=max(0.0,min(5.0,float(rp.get('success_spacing_seconds') or 0.03)))
    transient_summaries={str(x) for x in rp.get('transient_summaries') or [] if str(x)}
    paths=[];last=None
    for i in range(required):
        x=None;failure_summary='UNKNOWN'
        for retry in range(transient_retries+1):
            proc=subprocess.run([exe],input=json.dumps(fixture,ensure_ascii=False),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,shell=False,timeout=30)
            try:x=json.loads(proc.stdout.strip())
            except Exception:raise RuntimeError('REPEATABILITY_RESULT_INVALID:'+adapter)
            valid=proc.returncode==0 and x.get('schema')==RESULT_SCHEMA and x.get('status')=='OK' and x.get('producer')==adapter
            if valid:break
            failure_summary=str(x.get('summary') or proc.returncode)
            transient=any(failure_summary==v or failure_summary.startswith(v+':') for v in transient_summaries)
            if not transient or retry>=transient_retries:raise RuntimeError('REPEATABILITY_RESULT_FAILED:'+adapter+':'+failure_summary)
            time.sleep(retry_delay*(retry+1))
        p=work/(adapter+f'.repeat-{i+1}.json');save(p,x);paths.append(p);last=x;time.sleep(success_spacing)
    health_row={'state':'HEALTHY','checked_at':str(last.get('observed_at') or now_iso()),'source':'governed-auto-remediation:'+adapter+':repeatable-runtime-probe','automatic_external_spend_eur':0}
    hp=work/(adapter+'.health.json');save(hp,{'schema':HEALTH_SCHEMA,'observed_at':now_iso(),'providers':{provider:health_row}})
    if global_health is not None:
        merged=load(global_health) if global_health.is_file() else {'schema':HEALTH_SCHEMA,'providers':{}}
        if merged.get('schema')!=HEALTH_SCHEMA:raise RuntimeError('GLOBAL_PROVIDER_HEALTH_SCHEMA_INVALID')
        merged.setdefault('providers',{})[provider]=health_row;merged['observed_at']=now_iso();save(global_health,merged)
    return paths,hp

def ensure_enabled(repo:Path,registry:Path,adapter:str,provider:str,exe:str,work:Path,global_health:Path|None=None)->list[str]:
    entry=((load(registry).get('adapters') or {}).get(adapter) or {});refs=[]
    if entry.get('status')!='PILOT':return refs
    results,health=repeatable_results(repo,adapter,provider,exe,work,global_health);ep=work/(adapter+'.enablement-evidence.json');cmd=[sys.executable,str(repo/'dev-hub/bin/adapter-enablement-evidence.py'),'--adapter',adapter,'--provider',provider,'--health',str(health),'--rollbacks',str(repo/'dev-hub/config/adapter-rollbacks.v1.json'),'--output',str(ep)]
    for p in results:cmd+=['--result',str(p)]
    proc=run(cmd,repo)
    if proc.returncode!=0:raise RuntimeError('ENABLEMENT_EVIDENCE_FAILED:'+adapter+':'+proc.stdout[-500:])
    refs += [*(str(p) for p in results),str(health),str(ep),str(promote(repo,registry,adapter,'ENABLED',ep,work,exe))];return refs

def activate_umg(repo:Path,runtime:Path,adapter:str,work:Path)->dict[str,Any]:
    dynamic=runtime/'canonical-registry/dynamic-components.json';cid='integration:'+adapter;state=load(dynamic);row=next((x for x in state.get('registrations') or [] if x.get('component_id')==cid),None)
    if row and row.get('status')=='ACTIVE':return {'status':'ALREADY_ACTIVE','component_id':cid}
    out=work/(adapter+'.umg-activate.json');proc=run([sys.executable,str(repo/'dev-hub/bin/universal-materialization-gate.py'),'--mode','activate','--component-id',cid,'--policy',str(repo/'dev-hub/config/canonical-component-registry.v1.json'),'--operator-directives',str(repo/'dev-hub/config/operator-directives.v1.json'),'--dynamic-registry',str(dynamic),'--output',str(out)],repo)
    if proc.returncode!=0 or not out.is_file():raise RuntimeError('UMG_ACTIVATE_FAILED:'+adapter)
    return load(out)

def remediate(repo:Path,runtime:Path,readiness_path:Path,policy_path:Path,output:Path)->dict[str,Any]:
    readiness=load(readiness_path);policy=load(policy_path);provisioning=load(repo/'dev-hub/config/adapter-provisioning.v1.json')
    if policy.get('schema')!=POLICY_SCHEMA:raise ValueError('AUTO_REMEDIATION_POLICY_INVALID')
    root=runtime/'adapter-auto-remediation'/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+os.urandom(3).hex());root.mkdir(parents=True,exist_ok=True);registry=materialize_effective(repo,runtime,root);global_health=Path(str(readiness.get('provider_health_snapshot') or '')) if readiness.get('provider_health_snapshot') else None
    rows=[];changed=False
    for adapter,provider,requested_gate in selected_targets(readiness):
        entry=((load(registry).get('adapters') or {}).get(adapter) or {});profile=((policy.get('profiles') or {}).get(adapter) or {})
        probe=profile.get('zero_cost_attestation_probe') if isinstance(profile.get('zero_cost_attestation_probe'),dict) else {}
        refresh=refresh_zero_cost_attestation(repo,runtime,profile,provider,root) if probe.get('enabled') is True else None
        ok,blockers,profile=eligibility(adapter,provider,load(registry),provisioning,policy);row={'adapter':adapter,'provider':provider,'requested_gate':requested_gate,'initial_status':entry.get('status'),'eligible':ok,'blockers':blockers,'economics_attestation_refresh':refresh,'automatic_external_spend_eur':0}
        if not ok:row['status']='DEFERRED';rows.append(row);continue
        refs=[]
        try:
            row['umg_registration']=ensure_umg(repo,runtime,adapter,entry,root);refs+=ensure_contract_ok(repo,registry,adapter,root)
            if requested_gate=='PROVIDER_HEALTH_PROBE_REQUIRED' and str(entry.get('status'))=='ENABLED' and isinstance(entry.get('executable'),str) and Path(str(entry.get('executable'))).is_file():
                exe=str(entry.get('executable'));health_results,health_path=repeatable_results(repo,adapter,provider,exe,root,global_health);refs += [*(str(p) for p in health_results),str(health_path)];final='ENABLED';row['lifecycle_action']='REFRESH_EXISTING_ENABLED_PROVIDER'
            else:
                prov=provision(repo,adapter,root);refs.append(str(root/(adapter+'.provisioning-receipt.json')));exe,pilot_refs=ensure_pilot(repo,registry,adapter,provider,profile,root,prov);refs+=pilot_refs;refs+=ensure_enabled(repo,registry,adapter,provider,exe,root,global_health);final=((load(registry).get('adapters') or {}).get(adapter) or {}).get('status');row['lifecycle_action']='MATERIALIZE_OR_PROMOTE'
            if final!='ENABLED':raise RuntimeError('FINAL_ADAPTER_STATUS_NOT_ENABLED:'+str(final))
            persist_state(repo,runtime,registry,adapter,root,refs);row['umg_activation']=activate_umg(repo,runtime,adapter,root);row['status']='REMEDIATED';row['final_status']=final;row['executable']=exe;changed=changed or str(entry.get('status'))!=final or requested_gate=='PROVIDER_HEALTH_PROBE_REQUIRED'
        except Exception as exc:
            try:persist_state(repo,runtime,registry,adapter,root,refs)
            except Exception:pass
            row['status']='BLOCKED';row['blockers']=sorted(set(row.get('blockers') or [])|{type(exc).__name__+':'+str(exc)[:600]})
        rows.append(row)
    blockers=[r for r in rows if r.get('status')!='REMEDIATED'];result={'schema':SCHEMA,'observed_at':now_iso(),'source_readiness':str(readiness_path),'source_readiness_digest':digest(readiness),'status':'REMEDIATED' if rows and not blockers else 'PARTIAL' if any(r.get('status')=='REMEDIATED' for r in rows) else 'NO_SAFE_REMEDIATION','changed':changed,'remediations':rows,'work_dir':str(root),'runtime_state':str(runtime/'registries/provider-adapter-runtime-state.v1.json'),'guardian_bypass':False,'sentinel_bypass':False,'automatic_external_spend_eur':0};save(output,result);return result

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--runtime-root',type=Path,required=True);ap.add_argument('--readiness',type=Path,required=True);ap.add_argument('--policy',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();repo=a.repo_root.resolve();runtime=a.runtime_root.resolve();policy=(a.policy or repo/'dev-hub/config/adapter-auto-remediation.v1.json').resolve();result=remediate(repo,runtime,a.readiness.resolve(),policy,a.output.resolve());print(json.dumps(result,indent=2,ensure_ascii=False));return 0 if result.get('status')=='REMEDIATED' else 2
if __name__=='__main__':raise SystemExit(main())
