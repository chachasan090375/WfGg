#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,shutil,subprocess,tempfile
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def run(argv:list[str],cwd:Path|None=None,env=None,check=True):
    p=subprocess.run(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    if check and p.returncode!=0: raise RuntimeError("COMMAND_FAILED:"+repr(argv)+":"+(p.stderr or p.stdout)[-1200:])
    return p

def verify(policy:dict[str,Any])->dict[str,Any]:
    root=Path(policy["tor"]["toolcache_root"]);binary=Path(policy["tor"]["binary"])
    if not binary.is_file(): return {"status":"MISSING","binary":str(binary)}
    env=dict(os.environ);env["LD_LIBRARY_PATH"]=str(policy["tor"]["library_path"])
    p=run([str(binary),"--version"],env=env,check=False)
    m=re.search(r"Tor version ([0-9.]+)",p.stdout+"\n"+p.stderr)
    return {"status":"PASS" if p.returncode==0 and m else "INVALID","binary":str(binary),"version":m.group(1) if m else None}

def provision(policy:dict[str,Any])->dict[str,Any]:
    if not policy["tor"].get("system_service_install_forbidden",True): raise RuntimeError("TOR_SYSTEM_INSTALL_POLICY_INVALID")
    target=Path(policy["tor"]["toolcache_root"])
    with tempfile.TemporaryDirectory(prefix="chacha-tor-v801-") as td:
        td=Path(td);stage=td/"root";stage.mkdir()
        packages=["tor","libevent-2.1-7t64","tor-geoipdb"]
        run(["/usr/bin/apt-get","download",*packages],cwd=td)
        debs=sorted(td.glob("*.deb"))
        if len(debs)<2: raise RuntimeError("TOR_TOOLCACHE_PACKAGES_INCOMPLETE")
        for deb in debs: run(["/usr/bin/dpkg-deb","-x",str(deb),str(stage)])
        binary=stage/"usr/bin/tor"
        if not binary.is_file(): raise RuntimeError("TOR_BINARY_NOT_EXTRACTED")
        env=dict(os.environ);env["LD_LIBRARY_PATH"]=str(stage/"usr/lib/x86_64-linux-gnu")
        p=run([str(binary),"--version"],env=env)
        m=re.search(r"Tor version ([0-9.]+)",p.stdout+"\n"+p.stderr)
        if not m: raise RuntimeError("TOR_VERSION_UNVERIFIED")
        backup=target.with_name(target.name+".previous")
        if backup.exists(): shutil.rmtree(backup)
        if target.exists(): target.rename(backup)
        try:
            stage.rename(target)
        except Exception:
            if target.exists(): shutil.rmtree(target)
            if backup.exists(): backup.rename(target)
            raise
        if backup.exists(): shutil.rmtree(backup)
    out=verify(policy)
    out.update({"schema":"chacha.dev/dark-intelligence-tor-toolcache/v1","install_mode":"APT_DOWNLOAD_EXTRACT_ONLY",
                "system_package_install":False,"system_service_install":False,"automatic_external_spend_eur":0})
    return out

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True);ap.add_argument("command",choices=["verify","provision"])
    a=ap.parse_args();policy=load(a.policy);out=verify(policy) if a.command=="verify" else provision(policy)
    print(json.dumps(out,indent=2,ensure_ascii=False))
    if out.get("status")!="PASS": return 2
    print("CHACHA_DEV_V801_TOR_TOOLCACHE="+a.command.upper()+"_PASS")
    return 0

if __name__=="__main__": raise SystemExit(main())
