#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any

def load(p:Path,default=None):
    if not p.is_file(): return {} if default is None else default
    x=json.loads(p.read_text(encoding='utf-8')); assert isinstance(x,dict); return x

def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def dg(x:Any)->str:return 'sha256:'+hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def is_digest(v:Any)->bool:return isinstance(v,str) and v.startswith('sha256:') and len(v)>7

def seal_recipe(recipe:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    req=((policy.get('recipe') or {}).get('required_fields') or [])
    missing=[k for k in req if k not in recipe or recipe.get(k) in (None,'')]
    if missing: raise ValueError('TRAIN_RECIPE_REQUIRED:'+','.join(missing))
    mode=str(recipe.get('reproducibility_mode') or '')
    allowed=set((policy.get('recipe') or {}).get('reproducibility_modes') or [])
    if mode not in allowed: raise ValueError('REPRODUCIBILITY_MODE_INVALID:'+mode)
    for k in ('dependency_lock_digest','build_environment_digest','sbom_digest'):
        if not is_digest(recipe.get(k)): raise ValueError('REPRODUCIBILITY_DIGEST_REQUIRED:'+k)
    ads=recipe.get('artifact_digests')
    if not isinstance(ads,list) or not ads or not all(is_digest(x) for x in ads): raise ValueError('ARTIFACT_DIGESTS_REQUIRED')
    out={'schema':'chacha.dev/update-train-recipe/v2',**recipe,'sealed':True,'state':'RECIPE_SEALED','sealed_digest':None,'automatic_external_spend_eur':0}
    out['sealed_digest']=dg({k:v for k,v in out.items() if k!='sealed_digest'})
    return out

def register_recipe_only(registry:dict[str,Any],train_id:str,recipe:dict[str,Any])->dict[str,Any]:
    if recipe.get('sealed') is not True or not is_digest(recipe.get('sealed_digest')): raise ValueError('SEALED_RECIPE_REQUIRED')
    rows=registry.setdefault('items',{});row=rows.setdefault(train_id,{'train_id':train_id})
    row.update({
      'state':'RECIPE_ONLY','recipe_digest':recipe['sealed_digest'],'title':recipe.get('title') or recipe.get('train_id') or train_id,
      'functional_summary':recipe.get('functional_summary'),'platform_value':recipe.get('platform_value'),'source_revision':recipe.get('source_revision'),
      'source_tree':recipe.get('source_tree'),'physical_train_present':False,'pre_release_artifact_retained':False,'rebuild_available':True,
      'reproducibility_mode':recipe.get('reproducibility_mode'),'reproducibility_status':'NOT_REBUILT','production_mutation':False,
      'cache_optional':True,'cache_is_source_of_truth':False,'physical_release_retirement_authorized':False
    })
    registry.update({'schema':'chacha.dev/update-train-lifecycle-registry/v2','automatic_external_spend_eur':0});return registry

def rebuild_request(registry:dict[str,Any],train_id:str)->dict[str,Any]:
    row=(registry.get('items') or {}).get(train_id)
    if not row or row.get('state') not in {'RECIPE_ONLY','RECIPE_SEALED','UNINSTALLED_RECIPE_ONLY'}: raise ValueError('TRAIN_NOT_REBUILDABLE')
    return {'schema':'chacha.dev/update-train-rebuild-request/v1','train_id':train_id,'recipe_digest':row.get('recipe_digest'),'state':'REBUILD_REQUESTED',
            'reconstruct_from_exact_git':True,'dependency_lock_required':True,'build_environment_match_required':True,'current_policy_revalidation_required':True,
            'reproducibility_verification_required':True,'human_promotion_gate_required':True,'production_authority':False,'automatic_external_spend_eur':0}

def verify_rebuild(registry:dict[str,Any],train_id:str,recipe:dict[str,Any],result:dict[str,Any])->dict[str,Any]:
    row=(registry.get('items') or {}).get(train_id)
    if not row: raise ValueError('TRAIN_UNKNOWN')
    if row.get('recipe_digest')!=recipe.get('sealed_digest'): raise ValueError('RECIPE_DIGEST_MISMATCH')
    common=(result.get('source_tree')==recipe.get('source_tree') and result.get('dependency_lock_digest')==recipe.get('dependency_lock_digest') and
            result.get('build_environment_digest')==recipe.get('build_environment_digest') and result.get('sbom_digest')==recipe.get('sbom_digest') and result.get('tests_passed') is True)
    mode=recipe.get('reproducibility_mode')
    if mode=='BINARY_EXACT':
        ok=common and sorted(result.get('artifact_digests') or [])==sorted(recipe.get('artifact_digests') or [])
    elif mode=='FUNCTIONAL_DETERMINISTIC':
        ok=common and result.get('functional_contract_verified') is True
    else: ok=False
    if not ok:
        row.update({'state':'BLOCKED','reproducibility_status':'MISMATCH','promotion_allowed':False,'rebuild_available':True})
        return {'schema':'chacha.dev/update-train-rebuild-verification/v1','status':'BLOCK','train_id':train_id,'state':'BLOCKED','reason':'REBUILD_NOT_REPRODUCIBLE','production_authority':False,'automatic_external_spend_eur':0}
    row.update({'state':'REPRODUCIBILITY_VERIFIED','reproducibility_status':'PASS','promotion_allowed':False,'rebuild_available':False,'observed_artifact_digests':result.get('artifact_digests') or []})
    return {'schema':'chacha.dev/update-train-rebuild-verification/v1','status':'PASS','train_id':train_id,'state':'REPRODUCIBILITY_VERIFIED','human_promotion_gate_required':True,'production_authority':False,'automatic_external_spend_eur':0}

def staging_request(registry:dict[str,Any],train_id:str)->dict[str,Any]:
    row=(registry.get('items') or {}).get(train_id)
    if not row or row.get('state')!='REPRODUCIBILITY_VERIFIED': raise ValueError('REPRODUCIBILITY_VERIFICATION_REQUIRED')
    return {'schema':'chacha.dev/update-train-staging-request/v1','train_id':train_id,'state':'STAGING','human_promotion_gate_required':True,'direct_current_switch':False,'production_authority':False,'automatic_external_spend_eur':0}

# Legacy compatibility only. New trains do not enter this path.
def shelf(registry:dict[str,Any],train_id:str,reason:str,recipe:dict[str,Any],active:bool=False)->dict[str,Any]:
    if not reason.strip(): raise ValueError('SHELVE_REASON_REQUIRED')
    if active: raise ValueError('ACTIVE_TRAIN_REQUIRES_GOVERNED_ROLLBACK_OR_DEACTIVATION')
    rows=registry.setdefault('items',{});row=rows.setdefault(train_id,{'train_id':train_id})
    row.update({'state':'SHELVED','legacy_state':True,'shelved_reason':reason,'recipe_digest':recipe.get('sealed_digest'),'rebuild_available':True,'production_mutation':False})
    return registry

def rehydrate_request(registry:dict[str,Any],train_id:str)->dict[str,Any]:
    row=(registry.get('items') or {}).get(train_id)
    if not row or row.get('state') not in {'SHELVED','SHELVED_RECIPE_ONLY'}: raise ValueError('TRAIN_NOT_REHYDRATABLE')
    return {'schema':'chacha.dev/update-train-rebuild-request/v1','train_id':train_id,'recipe_digest':row.get('recipe_digest'),'state':'REBUILD_REQUESTED','legacy_alias':'REHYDRATION_REQUESTED','reconstruct_from_exact_git':True,'current_policy_revalidation_required':True,'reproducibility_verification_required':True,'production_authority':False,'automatic_external_spend_eur':0}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--registry',type=Path,required=True);sub=ap.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('seal-recipe');s.add_argument('--recipe',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('register-recipe-only');q.add_argument('--train-id',required=True);q.add_argument('--recipe',type=Path,required=True)
    r=sub.add_parser('rebuild-request');r.add_argument('--train-id',required=True);r.add_argument('--output',type=Path,required=True)
    v=sub.add_parser('verify-rebuild');v.add_argument('--train-id',required=True);v.add_argument('--recipe',type=Path,required=True);v.add_argument('--result',type=Path,required=True);v.add_argument('--output',type=Path,required=True)
    st=sub.add_parser('stage-request');st.add_argument('--train-id',required=True);st.add_argument('--output',type=Path,required=True)
    sh=sub.add_parser('shelve');sh.add_argument('--train-id',required=True);sh.add_argument('--reason',required=True);sh.add_argument('--recipe',type=Path,required=True);sh.add_argument('--active',action='store_true')
    rh=sub.add_parser('rehydrate-request');rh.add_argument('--train-id',required=True);rh.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();p=load(a.policy);reg=load(a.registry,{'schema':'chacha.dev/update-train-lifecycle-registry/v2','items':{}})
    if a.cmd=='seal-recipe':out=seal_recipe(load(a.recipe),p);save(a.output,out);print('CHACHA_DEV_UPDATE_RECIPE_SEAL=PASS');return
    if a.cmd=='register-recipe-only':out=register_recipe_only(reg,a.train_id,load(a.recipe));save(a.registry,out);print('CHACHA_DEV_UPDATE_RECIPE_ONLY=PASS');return
    if a.cmd=='rebuild-request':out=rebuild_request(reg,a.train_id);save(a.output,out);print('CHACHA_DEV_UPDATE_REBUILD_REQUEST=PASS');return
    if a.cmd=='verify-rebuild':out=verify_rebuild(reg,a.train_id,load(a.recipe),load(a.result));save(a.registry,reg);save(a.output,out);print('CHACHA_DEV_UPDATE_REBUILD_VERIFY='+out['status']);return
    if a.cmd=='stage-request':out=staging_request(reg,a.train_id);save(a.output,out);print('CHACHA_DEV_UPDATE_STAGE_REQUEST=PASS');return
    if a.cmd=='shelve':out=shelf(reg,a.train_id,a.reason,load(a.recipe),a.active);save(a.registry,out);print('CHACHA_DEV_UPDATE_SHELVE_LEGACY=PASS');return
    out=rehydrate_request(reg,a.train_id);save(a.output,out);print('CHACHA_DEV_UPDATE_REHYDRATION_ALIAS=PASS')
if __name__=='__main__':main()
