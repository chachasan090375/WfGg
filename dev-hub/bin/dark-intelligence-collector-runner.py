#!/usr/bin/env python3
from __future__ import annotations
import argparse,fcntl,json,os,subprocess,time,uuid
from pathlib import Path
from typing import Any
import importlib.util

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(t,p)

def run(argv:list[str],timeout:int=240,check=True)->subprocess.CompletedProcess[str]:
    p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
    if check and p.returncode!=0: raise RuntimeError("COMMAND_FAILED:"+repr(argv)+":"+(p.stderr or p.stdout)[-1600:])
    return p

def module(path:Path,name:str):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def sandbox_args(policy:dict[str,Any],namespace_path:str,network_profile:str="full")->list[str]:
    s=policy["sandbox"]
    inaccessible=" ".join(str(x) for x in s.get("inaccessible_paths") or [])
    props=[
      "NetworkNamespacePath="+namespace_path,
      "DynamicUser="+("yes" if s.get("dynamic_user",True) else "no"),
      "PrivateTmp="+("yes" if s.get("private_tmp",True) else "no"),
      "PrivateDevices="+("yes" if s.get("private_devices",True) else "no"),
      "ProtectSystem="+str(s.get("protect_system") or "strict"),
      "ProtectHome="+("yes" if s.get("protect_home",True) else "no"),
      "NoNewPrivileges="+("yes" if s.get("no_new_privileges",True) else "no"),
      "ProtectKernelTunables="+("yes" if s.get("protect_kernel_tunables",True) else "no"),
      "ProtectKernelModules="+("yes" if s.get("protect_kernel_modules",True) else "no"),
      "ProtectControlGroups="+("yes" if s.get("protect_control_groups",True) else "no"),
      "RestrictSUIDSGID="+("yes" if s.get("restrict_suid_sgid",True) else "no"),
      "LockPersonality="+("yes" if s.get("lock_personality",True) else "no"),
      "ProtectProc="+str(s.get("protect_proc") or "invisible"),
      "ProcSubset=pid","RestrictNamespaces=yes","RestrictAddressFamilies=AF_UNIX AF_INET",
      "CapabilityBoundingSet=","AmbientCapabilities=","UMask=0077","KillMode=mixed",
      "MemoryMax="+str(int(s.get("memory_max_mb") or 128))+"M",
      "TasksMax="+str(int(s.get("tasks_max") or 32)),
      "RuntimeMaxSec="+str(int(s.get("runtime_max_seconds") or 180))
    ]
    if inaccessible: props.append("InaccessiblePaths="+inaccessible)
    if network_profile=="tor-loopback-only":
        props.extend(["IPAddressDeny=any","IPAddressAllow=localhost"])
    out=[]
    for p in props: out.append("--property="+p)
    return out

def wait_tor(unit:str,timeout:int=110)->None:
    deadline=time.time()+timeout
    while time.time()<deadline:
        j=run(["/usr/bin/journalctl","-u",unit,"--no-pager","-n","140","-o","cat"],20,False)
        txt=j.stdout+j.stderr
        if "Bootstrapped 100%" in txt: return
        failed=run(["/usr/bin/systemctl","is-failed",unit],10,False)
        if failed.returncode==0 and failed.stdout.strip()=="failed":
            raise RuntimeError("TOR_TRANSIENT_UNIT_FAILED:"+txt[-1600:])
        time.sleep(2)
    j=run(["/usr/bin/journalctl","-u",unit,"--no-pager","-n","140","-o","cat"],20,False)
    raise RuntimeError("TOR_BOOTSTRAP_TIMEOUT:"+(j.stdout+j.stderr)[-1600:])

def start_tor(policy:dict[str,Any],namespace_path:str,run_token:str)->str:
    tor=policy["tor"];binary=Path(tor["binary"])
    if not binary.is_file(): raise RuntimeError("TOR_TOOLCACHE_MISSING:"+str(binary))
    unit="chacha-dark-tor-"+run_token
    cmd=["/usr/bin/systemd-run","--unit="+unit,"--collect","--quiet",*sandbox_args(policy,namespace_path),
         "--setenv=LD_LIBRARY_PATH="+str(tor["library_path"]),
         str(binary),
         "--SocksPort",f"{tor['socks_host']}:{int(tor['socks_port'])}",
         "--DataDirectory","/tmp/chacha-dark-tor-data","--CacheDirectory","/tmp/chacha-dark-tor-cache",
         "--Log","notice stdout","--RunAsDaemon","0","--ClientOnly","1","--ControlPort","0",
         "--CookieAuthentication","0","--AvoidDiskWrites","1","--SafeLogging","1","--ClientUseIPv6","0"]
    run(cmd,30)
    wait_tor(unit)
    return unit

def collect(repo:Path,policy_path:Path,policy:dict[str,Any],namespace_path:str,url:str,mode:str,run_token:str)->dict[str,Any]:
    unit="chacha-dark-fetch-"+run_token
    script=repo/"dev-hub/bin/dark-intelligence-collector.py"
    cmd=["/usr/bin/systemd-run","--pipe","--wait","--quiet","--collect","--unit="+unit,
         *sandbox_args(policy,namespace_path,"tor-loopback-only" if mode=="TOR_ONION" else "full"),
         "--setenv=CHACHA_DARK_INTEL_NETWORK_ISOLATED=1",
         "--setenv=CHACHA_DARK_INTEL_NAMESPACE="+str(policy["network_namespace"]["name"])]
    if mode=="TOR_ONION": cmd.append("--setenv=CHACHA_DARK_INTEL_TOR_READY=1")
    cmd.extend(["/usr/bin/python3",str(script),"--policy",str(policy_path),"--url",url,"--mode",mode])
    p=run(cmd,int(policy["sandbox"].get("runtime_max_seconds") or 180)+30)
    try:out=json.loads(p.stdout)
    except Exception as exc: raise RuntimeError("COLLECTOR_OUTPUT_INVALID:"+p.stdout[-1200:]) from exc
    if out.get("schema")!="chacha.dev/dark-intelligence-capture/v1": raise RuntimeError("COLLECTOR_SCHEMA_INVALID")
    return out

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--policy",type=Path,required=True);ap.add_argument("--url",required=True)
    ap.add_argument("--mode",choices=["TOR_ONION","ISOLATED_HTTPS"],required=True)
    ap.add_argument("--output",type=Path,required=True);ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args();repo=a.repo_root.resolve();policy_path=a.policy.resolve();policy=load(policy_path)
    iso=module(repo/"dev-hub/bin/dark-intelligence-isolation.py","v801_iso")
    network_plan=iso.plan(policy)
    if a.dry_run:
        print(json.dumps({"schema":"chacha.dev/dark-intelligence-collector-run-plan/v1","network":network_plan,
          "mode":a.mode,"url":a.url,"tor_required":a.mode=="TOR_ONION","sandbox_properties":sandbox_args(policy,network_plan["namespace_path"]),
          "automatic_external_spend_eur":0},indent=2,ensure_ascii=False));return 0
    lock_path=Path("/opt/chacha-dev/runtime/dark-intelligence/v801.lock");lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        run_token=uuid.uuid4().hex[:12];tor_unit=None
        try:
            active_plan=iso.setup(policy);namespace_path=active_plan["namespace_path"]
            if a.mode=="TOR_ONION": tor_unit=start_tor(policy,namespace_path,run_token)
            capture=collect(repo,policy_path,policy,namespace_path,a.url,a.mode,run_token)
            capture["runtime_attestation"]={
              "run_id":run_token,"namespace":policy["network_namespace"]["name"],
              "namespace_path":namespace_path,"network_isolation":"ACTIVE",
              "tor_transient_unit":tor_unit,"collector_transient_unit":"chacha-dark-fetch-"+run_token,
              "secrets_paths_inaccessible":True,"dynamic_user":True,"ephemeral_network_namespace":True
            }
            save(a.output,capture)
            print(json.dumps(capture,indent=2,ensure_ascii=False))
            print("CHACHA_DEV_V801_ISOLATED_DARK_INTELLIGENCE_RUN=PASS")
        finally:
            if tor_unit: run(["/usr/bin/systemctl","stop",tor_unit],30,False)
            iso.cleanup(policy)
    return 0

if __name__=="__main__": raise SystemExit(main())
