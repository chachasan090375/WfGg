#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/object-factory-plan/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def slug(v:str)->str:
    s=re.sub(r"[^a-z0-9]+","-",v.casefold()).strip("-")
    return s or "object"

def normalized_contract(obj:dict[str,Any])->dict[str,Any]:
    fields=[]
    for f in obj.get("fields") or []:
        fields.append({
          "name":str(f.get("name") or ""),
          "type":str(f.get("type") or "string"),
          "required":bool(f.get("required",False)),
          "sensitive":bool(f.get("sensitive",False)),
          "unique":bool(f.get("unique",False))
        })
    rels=[]
    for r in obj.get("relationships") or []:
        rels.append({
          "target":str(r.get("target") or ""),
          "type":str(r.get("type") or "many-to-one"),
          "required":bool(r.get("required",False))
        })
    return {
      "object_id":str(obj.get("id") or slug(str(obj.get("name") or "object"))),
      "name":str(obj.get("name") or ""),
      "purpose":str(obj.get("purpose") or ""),
      "fields":fields,
      "relationships":rels,
      "persistence":str(obj.get("persistence") or "none"),
      "api_exposed":bool(obj.get("api_exposed",False)),
      "ui_visible":bool(obj.get("ui_visible",False)),
      "events":sorted(set(str(x) for x in obj.get("events") or [] if str(x))),
    }

def fingerprint(contract:dict[str,Any])->str:
    raw=json.dumps(contract,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()

def reusable(contract:dict[str,Any],registry:dict[str,Any])->dict[str,Any]|None:
    fp=fingerprint(contract)
    for row in registry.get("objects") or []:
        if row.get("state")=="QUALIFIED" and row.get("contract_fingerprint")==fp:
            return row
    return None

def plan(project_id:str,obj:dict[str,Any],registry:dict[str,Any])->dict[str,Any]:
    c=normalized_contract(obj)
    if not c["name"]:raise ValueError("OBJECT_NAME_REQUIRED")
    if not c["fields"]:raise ValueError("OBJECT_FIELDS_REQUIRED:"+c["object_id"])
    names=[f["name"] for f in c["fields"]]
    if any(not x for x in names) or len(names)!=len(set(names)):
        raise ValueError("OBJECT_FIELD_NAMES_INVALID:"+c["object_id"])
    hit=reusable(c,registry)
    action="REUSE" if hit else "BUILD"
    return {
      "schema":SCHEMA,"project_id":project_id,"object_id":c["object_id"],
      "action":action,"contract":c,"contract_fingerprint":fingerprint(c),
      "selected_existing":hit,
      "outputs_required":{
        "json_schema":True,"domain_contract":True,"validation_contract":True,
        "api_contract":c["api_exposed"],"ui_contract":c["ui_visible"],
        "storage_mapping":c["persistence"]!="none","relationship_contract":bool(c["relationships"]),
        "tests":True
      },
      "component_factory_handoff_required":action=="BUILD",
      "capability_foundry_only_if_gap":True,
      "technology_provider_selection_authorized":False,
      "production_change_authorized":False,
      "automatic_external_spend_eur":0
    }

def plans_from_intent(intent:dict[str,Any],registry:dict[str,Any])->dict[str,Any]:
    project=str((intent.get("identity") or {}).get("slug") or "project")
    rows=[plan(project,o,registry) for o in intent.get("domain_objects") or []]
    return {
      "schema":"chacha.dev/object-factory-plan-index/v1",
      "project_id":project,"object_count":len(rows),"plans":rows,
      "all_contracts_explicit":all(bool(x["contract"]["fields"]) for x in rows),
      "production_change_authorized":False,"automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--intent",type=Path,required=True)
    ap.add_argument("--registry",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    out=plans_from_intent(load(a.intent),load(a.registry))
    a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_OBJECT_FACTORY=PASS")
    print("OBJECT_COUNT="+str(out["object_count"]))
    return 0

if __name__=="__main__":raise SystemExit(main())
