#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
from typing import Any

def load(p:Path,default=None):
    if not p.is_file(): return {} if default is None else default
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict): raise ValueError('JSON_ROOT_NOT_OBJECT')
    return x

def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def digest(x:Any)->str:
    raw=json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode();return 'sha256:'+hashlib.sha256(raw).hexdigest()

def validate_manifest(m:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    req=(policy.get('manifest') or {}).get('required_fields') or []
    missing=[k for k in req if k not in m or m.get(k) in ('',None)]
    if missing: raise ValueError('PLUGIN_MANIFEST_REQUIRED:'+','.join(missing))
    cls=str(m.get('plugin_class') or '')
    if cls not in set(policy.get('classes') or []): raise ValueError('PLUGIN_CLASS_INVALID')
    locked=set((policy.get('core_locked') or {}).get('component_ids') or [])
    if cls!='CORE_LOCKED' and str(m.get('plugin_id')) in locked: raise ValueError('CORE_COMPONENT_CANNOT_BE_PLUGINIZED')
    if cls=='CORE_LOCKED' and str(m.get('plugin_id')) not in locked: raise ValueError('CORE_LOCKED_ID_NOT_CANONICAL')
    out={"schema":"chacha.dev/plugin-manifest/v1",**m,"manifest_digest":None,"sealed":True,"automatic_external_spend_eur":0}
    out['manifest_digest']=digest({k:v for k,v in out.items() if k!='manifest_digest'})
    return out

def register(reg:dict[str,Any],manifest:dict[str,Any],state='QUALIFIED_RECIPE_ONLY')->dict[str,Any]:
    rows=reg.setdefault('items',{});pid=manifest['plugin_id']
    rows[pid]={"plugin_id":pid,"title":manifest.get('title'),"plugin_class":manifest.get('plugin_class'),"version":manifest.get('version'),"state":state,
      "functional_summary":manifest.get('functional_summary'),"platform_value":manifest.get('platform_value'),"source_revision":manifest.get('source_revision'),
      "source_tree":manifest.get('source_tree'),"recipe_digest":manifest.get('recipe_digest'),"manifest_digest":manifest.get('manifest_digest'),
      "dependencies":manifest.get('dependencies') or [],"conflicts":manifest.get('conflicts') or [],"persistent_data":manifest.get('persistent_data') or [],
      "runtime_artifact_present":False,"production_authority":False,"automatic_external_spend_eur":0}
    reg.update({"schema":"chacha.dev/plugin-registry/v1","updated_at":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),"automatic_external_spend_eur":0});return reg

def request(reg:dict[str,Any],pid:str,action:str,policy:dict[str,Any])->dict[str,Any]:
    row=(reg.get('items') or {}).get(pid)
    if not isinstance(row,dict): raise ValueError('PLUGIN_NOT_FOUND')
    if row.get('plugin_class')=='CORE_LOCKED': raise ValueError('CORE_LOCKED_LIFECYCLE_ACTION_FORBIDDEN')
    action=action.upper();states={
      'INSTALL':({'QUALIFIED_RECIPE_ONLY','UNINSTALLED_RECIPE_ONLY','DISABLED'},'INSTALL_REQUESTED'),
      'DISABLE':({'ACTIVE'},'DISABLE_REQUESTED'),
      'UNINSTALL':({'DISABLED'},'UNINSTALL_REQUESTED'),
      'REINSTALL':({'UNINSTALLED_RECIPE_ONLY'},'REINSTALL_REQUESTED')}
    if action not in states: raise ValueError('PLUGIN_ACTION_INVALID')
    allowed,target=states[action]
    if row.get('state') not in allowed: raise ValueError('PLUGIN_STATE_ACTION_INVALID:'+str(row.get('state'))+':'+action)
    if action=='UNINSTALL' and not row.get('recipe_digest'): raise ValueError('PLUGIN_RECIPE_REQUIRED_BEFORE_UNINSTALL')
    return {"schema":"chacha.dev/plugin-lifecycle-request/v1","plugin_id":pid,"action":action,"from_state":row.get('state'),"requested_state":target,
      "dependency_graph_check_required":True,"guardian_required":True,"sentinel_required":True,"health_check_required":action in {'DISABLE','UNINSTALL'},
      "preserve_recipe":True,"preserve_git":True,"preserve_persistent_data":True,"intendant_required":action=='UNINSTALL',
      "production_authority":False,"destructive_authority":False,"automatic_external_spend_eur":0}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--registry',type=Path,required=True);sub=ap.add_subparsers(dest='cmd',required=True)
    m=sub.add_parser('register');m.add_argument('--manifest',type=Path,required=True);m.add_argument('--sealed-output',type=Path,required=True)
    r=sub.add_parser('request');r.add_argument('--plugin-id',required=True);r.add_argument('--action',required=True,choices=['INSTALL','DISABLE','UNINSTALL','REINSTALL']);r.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();p=load(a.policy);reg=load(a.registry,{"schema":"chacha.dev/plugin-registry/v1","items":{}})
    if a.cmd=='register':
        sealed=validate_manifest(load(a.manifest),p);save(a.sealed_output,sealed);save(a.registry,register(reg,sealed));print('CHACHA_DEV_PLUGIN_REGISTER=PASS');return
    out=request(reg,a.plugin_id,a.action,p);save(a.output,out);print('CHACHA_DEV_PLUGIN_LIFECYCLE_REQUEST=PASS')
if __name__=='__main__':main()
