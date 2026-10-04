#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
from typing import Any

def load(p:Path,default=None):
    if not p.is_file(): return {} if default is None else default
    x=json.loads(p.read_text(encoding="utf-8")); assert isinstance(x,dict); return x
def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def dg(x:Any)->str:return "sha256:"+hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
def seal_recipe(recipe:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    req=((policy.get("recipe") or {}).get("required_fields") or [])
    missing=[k for k in req if k not in recipe or recipe.get(k) in (None,"")]
    if missing: raise ValueError("TRAIN_RECIPE_REQUIRED:"+",".join(missing))
    out={"schema":"chacha.dev/update-train-recipe/v1",**recipe,"sealed":True,"sealed_digest":None,"automatic_external_spend_eur":0}
    out["sealed_digest"]=dg({k:v for k,v in out.items() if k!="sealed_digest"}); return out
def shelf(registry:dict[str,Any],train_id:str,reason:str,recipe:dict[str,Any],active:bool=False)->dict[str,Any]:
    if not reason.strip(): raise ValueError("SHELVE_REASON_REQUIRED")
    if active: raise ValueError("ACTIVE_TRAIN_REQUIRES_GOVERNED_ROLLBACK_OR_DEACTIVATION")
    rows=registry.setdefault("items",{}); row=rows.setdefault(train_id,{"train_id":train_id})
    row.update({"state":"SHELVED","shelved_reason":reason,"recipe_digest":recipe.get("sealed_digest"),"title":recipe.get("title") or recipe.get("train_id") or train_id,"functional_summary":recipe.get("functional_summary"),"platform_value":recipe.get("platform_value"),"source_revision":recipe.get("source_revision"),"source_tree":recipe.get("source_tree"),"reactivation_available":True,"physical_retirement_authorized":False,"intendant_retirement_eligible":True,"production_mutation":False})
    registry.update({"schema":"chacha.dev/update-train-lifecycle-registry/v1","automatic_external_spend_eur":0}); return registry
def mark_recipe_only(registry:dict[str,Any],train_id:str,retirement_receipt:str)->dict[str,Any]:
    row=(registry.get("items") or {}).get(train_id)
    if not row or row.get("state")!="SHELVED": raise ValueError("TRAIN_NOT_SHELVED")
    if not retirement_receipt: raise ValueError("GOVERNED_RETIREMENT_RECEIPT_REQUIRED")
    row.update({"state":"SHELVED_RECIPE_ONLY","physical_train_present":False,"retirement_receipt":retirement_receipt,"reactivation_available":True}); return registry
def rehydrate_request(registry:dict[str,Any],train_id:str)->dict[str,Any]:
    row=(registry.get("items") or {}).get(train_id)
    if not row or row.get("state") not in {"SHELVED","SHELVED_RECIPE_ONLY"}: raise ValueError("TRAIN_NOT_REHYDRATABLE")
    return {"schema":"chacha.dev/update-train-rehydration-request/v1","train_id":train_id,"recipe_digest":row.get("recipe_digest"),"state":"REHYDRATION_REQUESTED","reconstruct_from_exact_git":True,"current_policy_revalidation_required":True,"production_authority":False,"automatic_external_spend_eur":0}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--registry',type=Path,required=True);sub=ap.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('seal-recipe');s.add_argument('--recipe',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
    sh=sub.add_parser('shelve');sh.add_argument('--train-id',required=True);sh.add_argument('--reason',required=True);sh.add_argument('--recipe',type=Path,required=True);sh.add_argument('--active',action='store_true')
    r=sub.add_parser('rehydrate-request');r.add_argument('--train-id',required=True);r.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();p=load(a.policy);reg=load(a.registry,{"schema":"chacha.dev/update-train-lifecycle-registry/v1","items":{}})
    if a.cmd=='seal-recipe': out=seal_recipe(load(a.recipe),p);save(a.output,out);print('CHACHA_DEV_UPDATE_RECIPE_SEAL=PASS');return
    if a.cmd=='shelve': out=shelf(reg,a.train_id,a.reason,load(a.recipe),a.active);save(a.registry,out);print('CHACHA_DEV_UPDATE_SHELVE=PASS');return
    out=rehydrate_request(reg,a.train_id);save(a.output,out);print('CHACHA_DEV_UPDATE_REHYDRATION_REQUEST=PASS')
if __name__=='__main__':main()
