#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,shutil,time
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/live-ui-publisher-policy/v1"
HANDOFF_SCHEMA="chacha.dev/live-ui-publish-handoff/v1"
WORKFLOW_RECEIPT_SCHEMA="chacha.dev/exact-sha-workflow-receipt/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+".tmp-"+str(os.getpid()))
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,p)

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def validate_receipts(policy:dict[str,Any],revision:str,receipts:list[dict[str,Any]])->None:
    required=set(str(x) for x in policy.get("required_workflows") or [])
    passed=set()
    for r in receipts:
        if r.get("schema")!=WORKFLOW_RECEIPT_SCHEMA:continue
        if str(r.get("head_sha") or "")!=revision:continue
        if r.get("conclusion")!="success" or r.get("exact_sha_verified") is not True:continue
        passed.add(str(r.get("workflow_name") or ""))
    missing=sorted(required-passed)
    if missing:raise ValueError("LIVE_UI_EXACT_SHA_GATES_MISSING:"+",".join(missing))

def validate_handoff(h:dict[str,Any],revision:str)->None:
    checks={
      "schema":h.get("schema")==HANDOFF_SCHEMA,
      "actor":h.get("actor")=="central-orchestrator",
      "revision":h.get("revision")==revision,
      "publish_authorized":h.get("publish_authorized") is True,
      "scope":h.get("scope")=="CHACHA_LIVE_UI_ONLY",
      "native_update_forbidden":h.get("native_update_authorized") is False,
      "apk_install_forbidden":h.get("apk_install_authorized") is False,
      "systemd_mutation_forbidden":h.get("systemd_mutation_authorized") is False,
      "rollback_required":h.get("rollback_required") is True,
      "single_use":h.get("single_use") is True,
      "zero_spend":float(h.get("automatic_external_spend_eur") or 0)==0,
    }
    bad=sorted(k for k,v in checks.items() if not v)
    if bad:raise ValueError("LIVE_UI_HANDOFF_INVALID:"+",".join(bad))

def collect_bundle(repo:Path,policy:dict[str,Any])->tuple[Path,Path]:
    ui=(repo/str(policy.get("source_ui_root") or "")).resolve()
    cfg=(repo/str(policy.get("source_app_config") or "")).resolve()
    root=repo.resolve()
    if not str(ui).startswith(str(root)+os.sep) or not str(cfg).startswith(str(root)+os.sep):
        raise ValueError("LIVE_UI_SOURCE_ESCAPE")
    if not (ui/"index.html").is_file():raise ValueError("LIVE_UI_INDEX_MISSING")
    if not cfg.is_file():raise ValueError("LIVE_UI_APP_CONFIG_MISSING")
    return ui,cfg

def manifest_for(release:Path,revision:str)->dict[str,Any]:
    files={}
    for p in sorted(release.rglob("*")):
        if p.is_file():
            rel=str(p.relative_to(release))
            files[rel]={"sha256":sha256_file(p),"bytes":p.stat().st_size}
    return {"schema":"chacha.dev/live-ui-release-manifest/v1","revision":revision,
            "files":files,"file_count":len(files),"automatic_external_spend_eur":0}

def atomic_link(link:Path,target_name:str)->None:
    tmp=link.with_name(link.name+".next-"+str(os.getpid()))
    try:tmp.unlink()
    except FileNotFoundError:pass
    os.symlink(target_name,tmp)
    os.replace(tmp,link)

def prune(root:Path,current_target:str,keep:int)->None:
    releases=root/"releases"
    rows=sorted([p for p in releases.iterdir() if p.is_dir()],key=lambda p:p.stat().st_mtime,reverse=True)
    kept=0
    for p in rows:
        if p.name==current_target:continue
        kept+=1
        if kept>=max(1,keep):continue
        # The newest previous release is intentionally retained.
    protected={current_target}
    previous=[p.name for p in rows if p.name!=current_target][:max(0,keep-1)]
    protected.update(previous)
    for p in rows:
        if p.name not in protected:shutil.rmtree(p)

def publish(repo:Path,policy:dict[str,Any],revision:str,handoff:dict[str,Any],receipts:list[dict[str,Any]],runtime_root:Path|None=None)->dict[str,Any]:
    validate_handoff(handoff,revision);validate_receipts(policy,revision,receipts)
    ui,cfg=collect_bundle(repo,policy)
    root=(runtime_root or Path(str(policy.get("runtime_root") or ""))).resolve()
    releases=root/"releases";releases.mkdir(parents=True,exist_ok=True)
    stamp=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())
    name=stamp+"-"+revision[:12]
    final=releases/name
    if final.exists():raise ValueError("LIVE_UI_RELEASE_ALREADY_EXISTS:"+name)
    staging=releases/("."+name+".staging")
    if staging.exists():shutil.rmtree(staging)
    (staging/"ui").mkdir(parents=True)
    for src in ui.rglob("*"):
        rel=src.relative_to(ui);dst=staging/"ui"/rel
        if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
        elif src.is_file():
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    shutil.copy2(cfg,staging/"app-config.json")
    m=manifest_for(staging,revision);save(staging/"manifest.json",m)
    previous=None
    link=root/str(policy.get("current_symlink") or "current")
    if link.is_symlink():previous=os.readlink(link)
    os.replace(staging,final)
    atomic_link(link,"releases/"+name)
    prune(root,name,int(policy.get("retention") or 3))
    receipt={"schema":"chacha.dev/live-ui-publish-receipt/v1","status":"PASS","revision":revision,
      "release":name,"current_target":"releases/"+name,"previous_target":previous,
      "manifest_sha256":sha256_file(final/"manifest.json"),"handoff_id":handoff.get("handoff_id"),
      "rollback_available":bool(previous),"native_update_performed":False,"apk_installed":False,
      "automatic_external_spend_eur":0}
    return receipt

def rollback(policy:dict[str,Any],receipt:dict[str,Any],runtime_root:Path|None=None)->dict[str,Any]:
    root=(runtime_root or Path(str(policy.get("runtime_root") or ""))).resolve()
    previous=str(receipt.get("previous_target") or "")
    if not previous:raise ValueError("LIVE_UI_NO_PREVIOUS_RELEASE")
    target=(root/previous).resolve()
    releases=(root/"releases").resolve()
    if not str(target).startswith(str(releases)+os.sep) or not target.is_dir():
        raise ValueError("LIVE_UI_ROLLBACK_TARGET_INVALID")
    atomic_link(root/str(policy.get("current_symlink") or "current"),previous)
    return {"schema":"chacha.dev/live-ui-rollback-receipt/v1","status":"PASS",
            "restored_target":previous,"rolled_back_release":receipt.get("current_target"),
            "automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--policy",type=Path,required=True)
    sub=ap.add_subparsers(dest="cmd",required=True)
    pub=sub.add_parser("publish");pub.add_argument("--revision",required=True);pub.add_argument("--handoff",type=Path,required=True);pub.add_argument("--receipt",type=Path,action="append",required=True);pub.add_argument("--output",type=Path,required=True);pub.add_argument("--apply",action="store_true")
    rb=sub.add_parser("rollback");rb.add_argument("--publish-receipt",type=Path,required=True);rb.add_argument("--output",type=Path,required=True);rb.add_argument("--apply",action="store_true")
    a=ap.parse_args();policy=load(a.policy)
    if policy.get("schema")!=POLICY_SCHEMA:raise SystemExit("LIVE_UI_POLICY_SCHEMA_INVALID")
    if not a.apply:raise SystemExit("LIVE_UI_APPLY_FLAG_REQUIRED")
    if a.cmd=="publish":
        out=publish(a.repo_root.resolve(),policy,a.revision,load(a.handoff),[load(x) for x in a.receipt])
    else:out=rollback(policy,load(a.publish_receipt))
    save(a.output,out);print(json.dumps(out,ensure_ascii=False));return 0

if __name__=="__main__":raise SystemExit(main())
