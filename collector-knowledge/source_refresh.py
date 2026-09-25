#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

REFRESH_VERSION = "1.0.0"

def now_ts() -> int:
    return int(time.time())

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def atomic_replace_dir(stage: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True,exist_ok=True)
    old=dest.with_name(dest.name+".old")
    if old.exists():
        shutil.rmtree(old,ignore_errors=True)
    if dest.exists():
        dest.rename(old)
    stage.rename(dest)
    shutil.rmtree(old,ignore_errors=True)

def download(url: str, target: Path, allowed_hosts: set[str]) -> None:
    u=urllib.parse.urlparse(url)
    if u.scheme!="https":
        raise ValueError("SOURCE_REFRESH_HTTPS_REQUIRED")
    if u.hostname not in allowed_hosts:
        raise ValueError("SOURCE_REFRESH_HOST_NOT_ALLOWED:"+str(u.hostname))
    req=urllib.request.Request(url,headers={"User-Agent":"WfGg-Collector-Knowledge/1.0"})
    target.parent.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen(req,timeout=180) as r, target.open("wb") as f:
        shutil.copyfileobj(r,f,1024*1024)

def extract_tarball(archive: Path, destination: Path, strip_top_level: bool=True) -> None:
    with tempfile.TemporaryDirectory(prefix="collector-refresh-tar-") as td:
        tmp=Path(td)
        with tarfile.open(archive,"r:*") as tf:
            members=tf.getmembers()
            for m in members:
                name=Path(m.name)
                if name.is_absolute() or ".." in name.parts:
                    raise ValueError("SOURCE_REFRESH_TAR_PATH_INVALID")
            tf.extractall(tmp,filter="data")
        children=[p for p in tmp.iterdir()]
        source=tmp
        if strip_top_level and len(children)==1 and children[0].is_dir():
            source=children[0]
        stage=destination.with_name(destination.name+".stage")
        shutil.rmtree(stage,ignore_errors=True)
        shutil.copytree(source,stage,symlinks=False)
        atomic_replace_dir(stage,destination)

def extract_lastwar_lwlf(xapk: Path, destination_dir: Path) -> dict:
    destination_dir.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="collector-refresh-xapk-") as td:
        tmp=Path(td)
        nested=tmp/"install_time_pack.apk"
        with zipfile.ZipFile(xapk) as z:
            matches=[n for n in z.namelist() if n.endswith("install_time_pack.apk")]
            if len(matches)!=1:
                raise ValueError("SOURCE_REFRESH_INSTALL_TIME_PACK_MATCH_COUNT:"+str(len(matches)))
            with z.open(matches[0]) as src,nested.open("wb") as dst:
                shutil.copyfileobj(src,dst,1024*1024)
        lwlf=tmp/"LWScripts.data"
        with zipfile.ZipFile(nested) as z:
            member="assets/lwScripts/LWScripts.data"
            if member not in z.namelist():
                raise ValueError("SOURCE_REFRESH_LWSCRIPTS_MISSING")
            with z.open(member) as src,lwlf.open("wb") as dst:
                shutil.copyfileobj(src,dst,1024*1024)
        if lwlf.read_bytes()[:4]!=b"LWLF":
            raise ValueError("SOURCE_REFRESH_LWLF_MAGIC_INVALID")
        stage=destination_dir.with_name(destination_dir.name+".stage")
        shutil.rmtree(stage,ignore_errors=True)
        stage.mkdir(parents=True)
        shutil.copy2(lwlf,stage/"LWScripts.data")
        meta={
            "xapkSha256":sha256_file(xapk),
            "nestedApkSha256":sha256_file(nested),
            "lwlfSha256":sha256_file(lwlf),
            "lwlfBytes":lwlf.stat().st_size,
        }
        (stage/"SOURCE_METADATA.json").write_text(json.dumps(meta,indent=2)+"\n")
        atomic_replace_dir(stage,destination_dir)
        return meta

def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"sources":{}}

def save_state(path: Path,state: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state,indent=2,sort_keys=True)+"\n")
    os.replace(tmp,path)

def refresh_one(spec: dict, state: dict, cache_dir: Path, allowed_hosts: set[str], force: bool=False) -> dict:
    name=str(spec["name"])
    enabled=bool(spec.get("enabled",True))
    if not enabled:
        return {"name":name,"status":"DISABLED"}
    interval=max(60,int(spec.get("refreshSeconds",21600)))
    previous=(state.get("sources") or {}).get(name,{})
    if not force and now_ts()-int(previous.get("lastSuccessEpoch",0))<interval:
        return {"name":name,"status":"FRESH","lastSuccessEpoch":previous.get("lastSuccessEpoch")}
    url=str(spec["url"])
    kind=str(spec["kind"])
    dest=Path(spec["destination"])
    cache_dir.mkdir(parents=True,exist_ok=True)
    suffix=".xapk" if kind=="LASTWAR_XAPK_LWLF" else ".tar.gz"
    archive=cache_dir/(name+suffix)
    part=cache_dir/(name+suffix+".part")
    part.unlink(missing_ok=True)
    download(url,part,allowed_hosts)
    os.replace(part,archive)
    digest=sha256_file(archive)
    result={"name":name,"status":"UPDATED","archiveSha256":digest,"kind":kind}
    if kind=="GITHUB_TARBALL":
        extract_tarball(archive,dest,bool(spec.get("stripTopLevel",True)))
    elif kind=="LASTWAR_XAPK_LWLF":
        result.update(extract_lastwar_lwlf(archive,dest))
    else:
        raise ValueError("SOURCE_REFRESH_KIND_UNSUPPORTED:"+kind)
    state.setdefault("sources",{})[name]={
        "lastSuccessEpoch":now_ts(),
        "archiveSha256":digest,
        "kind":kind,
        "destination":str(dest),
        "url":url,
    }
    return result

def refresh_all(config: dict, force: bool=False) -> list[dict]:
    specs=config.get("refreshSources") or []
    if not specs:
        return []
    allowed=set(config.get("allowedRefreshHosts") or [])
    if not allowed:
        raise ValueError("SOURCE_REFRESH_ALLOWED_HOSTS_REQUIRED")
    state_path=Path(config.get("refreshState","/opt/wfgg-radar/data/collector-knowledge/source-refresh.json"))
    cache_dir=Path(config.get("refreshCache","/opt/wfgg-radar/data/collector-knowledge/downloads"))
    state=load_state(state_path)
    results=[]
    for spec in specs:
        try:
            results.append(refresh_one(spec,state,cache_dir,allowed,force))
        except Exception as exc:
            results.append({"name":str(spec.get("name","?")),"status":"FAILED","error":f"{type(exc).__name__}:{exc}"})
    save_state(state_path,state)
    return results

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True)
    ap.add_argument("--force",action="store_true")
    args=ap.parse_args()
    cfg=json.loads(Path(args.config).read_text())
    print(json.dumps({"refreshVersion":REFRESH_VERSION,"results":refresh_all(cfg,args.force)},indent=2))
