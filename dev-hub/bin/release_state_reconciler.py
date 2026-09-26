#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/release-state-reconciliation/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def install_proof(gates:Path,revision:str,active:Path)->tuple[Path|None,dict[str,Any]|None]:
    for p in sorted(gates.glob('*install-pass.json')):
        try:x=load(p)
        except Exception:continue
        if str(x.get('revision') or '')!=revision:continue
        if str(x.get('status') or '').upper()!='PASS':continue
        if x.get('guardian_realtime') not in (None,'PASS'):continue
        if x.get('direct_operator_health') not in (None,'PASS'):continue
        release=str(x.get('release') or '')
        if release and Path(release).resolve()!=active.resolve():continue
        return p,x
    return None,None

def reconcile(platform_root:Path,gates:Path,apply:bool)->dict[str,Any]:
    current=platform_root/'current'
    if not current.exists():raise ValueError('CURRENT_RELEASE_MISSING')
    active=current.resolve();revision=(active/'.revision').read_text().strip()
    prep_path=active/'.release-preparation.json'
    prep=load(prep_path)
    proof_path,proof=install_proof(gates,revision,active)
    declared=str(prep.get('activation_status') or '')
    required=declared not in {'ACTIVE','ACTIVATED'}
    if required and proof is None:raise ValueError('ACTIVE_RELEASE_INSTALL_PROOF_MISSING')
    changed=False
    if required and apply:
        prep['activation_status']='ACTIVE'
        prep['activated_at']=str((proof or {}).get('installed_at') or now_iso())
        prep['activation_evidence']=str(proof_path)
        save(prep_path,prep);changed=True
    return {'schema':SCHEMA,'status':'PASS','active_release':str(active),'revision':revision,
            'declared_before':declared,'reconciliation_required':required,'applied':changed,
            'install_proof':str(proof_path) if proof_path else None,'automatic_external_spend_eur':0}
def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--platform-root',type=Path,default=Path('/opt/chacha-dev/platform'))
    ap.add_argument('--release-gates',type=Path,default=Path('/opt/chacha-dev/runtime/release-gates'))
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--apply',action='store_true')
    a=ap.parse_args();out=reconcile(a.platform_root,a.release_gates,a.apply);save(a.output,out)
    print('CHACHA_DEV_RELEASE_STATE_RECONCILIATION=PASS')
    print('RECONCILIATION_REQUIRED='+('YES' if out['reconciliation_required'] else 'NO'))
    print('APPLIED='+('YES' if out['applied'] else 'NO'))
    print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
    return 0

if __name__=='__main__':raise SystemExit(main())
