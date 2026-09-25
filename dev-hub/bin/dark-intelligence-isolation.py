#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x

def run(argv:list[str],check=True,input_text:str|None=None)->subprocess.CompletedProcess[str]:
    p=subprocess.run(argv,input=input_text,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    if check and p.returncode!=0: raise RuntimeError("COMMAND_FAILED:"+repr(argv)+":"+(p.stderr or p.stdout)[-1000:])
    return p

def default_iface()->str:
    p=run(["/usr/sbin/ip","route","show","default"])
    for line in p.stdout.splitlines():
        parts=line.split()
        if "dev" in parts:
            return parts[parts.index("dev")+1]
    raise RuntimeError("DEFAULT_ROUTE_INTERFACE_NOT_FOUND")

def global_ipv4s()->list[str]:
    p=run(["/usr/sbin/ip","-4","-o","addr","show","scope","global"])
    out=[]
    for line in p.stdout.splitlines():
        parts=line.split()
        if "inet" in parts:
            out.append(parts[parts.index("inet")+1].split("/",1)[0]+"/32")
    return sorted(set(out))

def names(policy:dict[str,Any])->dict[str,str]:
    n=policy["network_namespace"]
    return {
      "namespace":str(n["name"]),"host_veth":str(n["host_veth"]),"namespace_veth":str(n["namespace_veth"]),
      "filter_table":"chacha_dark_v801_filter","nat_table":"chacha_dark_v801_nat"
    }

def nft_rules(policy:dict[str,Any],out_iface:str,host_ips:list[str])->str:
    n=policy["network_namespace"];nm=names(policy)
    blocked=[str(x) for x in n.get("block_private_and_metadata_cidrs") or []]+host_ips
    blocked_set=", ".join(blocked)
    return f"""table inet {nm['filter_table']} {{
  chain input {{
    type filter hook input priority 0; policy accept;
    iifname "{nm['host_veth']}" counter drop
  }}
  chain output {{
    type filter hook output priority 0; policy accept;
    oifname "{nm['host_veth']}" counter drop
  }}
  chain forward {{
    type filter hook forward priority 0; policy accept;
    iifname "{nm['host_veth']}" ip daddr {{ {blocked_set} }} counter drop
    iifname "{nm['host_veth']}" oifname != "{out_iface}" counter drop
    iifname "{nm['host_veth']}" oifname "{out_iface}" counter accept
    oifname "{nm['host_veth']}" ct state established,related counter accept
    oifname "{nm['host_veth']}" counter drop
  }}
}}
table ip {nm['nat_table']} {{
  chain postrouting {{
    type nat hook postrouting priority srcnat; policy accept;
    ip saddr {n['subnet']} oifname "{out_iface}" masquerade
  }}
}}
"""

def cleanup(policy:dict[str,Any])->None:
    nm=names(policy)
    run(["/usr/sbin/nft","delete","table","inet",nm["filter_table"]],check=False)
    run(["/usr/sbin/nft","delete","table","ip",nm["nat_table"]],check=False)
    run(["/usr/sbin/ip","netns","del",nm["namespace"]],check=False)
    run(["/usr/sbin/ip","link","del",nm["host_veth"]],check=False)

def plan(policy:dict[str,Any])->dict[str,Any]:
    n=policy["network_namespace"];nm=names(policy);iface=default_iface();host_ips=global_ipv4s()
    return {
      "schema":"chacha.dev/dark-intelligence-network-isolation-plan/v1","namespace":nm["namespace"],
      "namespace_path":"/run/netns/"+nm["namespace"],"outbound_interface":iface,
      "host_veth":nm["host_veth"],"namespace_veth":nm["namespace_veth"],
      "namespace_cidr":n["namespace_cidr"],"host_cidr":n["host_cidr"],
      "blocked_cidrs":list(n.get("block_private_and_metadata_cidrs") or []),
      "blocked_host_global_ipv4s":host_ips,"host_input_blocked":True,"host_output_to_namespace_blocked":True,
      "nat_scope":n["subnet"],"ipv6_disabled":bool(n.get("disable_ipv6")),
      "automatic_external_spend_eur":0
    }

def setup(policy:dict[str,Any])->dict[str,Any]:
    n=policy["network_namespace"];nm=names(policy);p=plan(policy)
    forwarding=Path("/proc/sys/net/ipv4/ip_forward").read_text().strip()
    if forwarding!="1": raise RuntimeError("HOST_IP_FORWARDING_REQUIRED_BUT_NOT_ENABLED")
    cleanup(policy)
    run(["/usr/sbin/ip","netns","add",nm["namespace"]])
    try:
        run(["/usr/sbin/ip","link","add",nm["host_veth"],"type","veth","peer","name",nm["namespace_veth"]])
        run(["/usr/sbin/ip","link","set",nm["namespace_veth"],"netns",nm["namespace"]])
        run(["/usr/sbin/ip","addr","add",str(n["host_cidr"]),"dev",nm["host_veth"]])
        run(["/usr/sbin/ip","link","set",nm["host_veth"],"up"])
        run(["/usr/sbin/ip","netns","exec",nm["namespace"],"/usr/sbin/ip","link","set","lo","up"])
        run(["/usr/sbin/ip","netns","exec",nm["namespace"],"/usr/sbin/ip","addr","add",str(n["namespace_cidr"]),"dev",nm["namespace_veth"]])
        run(["/usr/sbin/ip","netns","exec",nm["namespace"],"/usr/sbin/ip","link","set",nm["namespace_veth"],"up"])
        run(["/usr/sbin/ip","netns","exec",nm["namespace"],"/usr/sbin/ip","route","add","default","via",str(n["host_gateway"])])
        if n.get("disable_ipv6",True):
            run(["/usr/sbin/ip","netns","exec",nm["namespace"],"/usr/sbin/sysctl","-q","-w","net.ipv6.conf.all.disable_ipv6=1"])
            run(["/usr/sbin/ip","netns","exec",nm["namespace"],"/usr/sbin/sysctl","-q","-w","net.ipv6.conf.default.disable_ipv6=1"])
        run(["/usr/sbin/nft","-f","-"],input_text=nft_rules(policy,p["outbound_interface"],p["blocked_host_global_ipv4s"]))
        p["status"]="ACTIVE";p["host_ip_forwarding_preexisting"]=True
        return p
    except Exception:
        cleanup(policy);raise

def status(policy:dict[str,Any])->dict[str,Any]:
    nm=names(policy)
    q=run(["/usr/sbin/ip","netns","list"],check=False)
    active=any(line.split()[0]==nm["namespace"] for line in q.stdout.splitlines() if line.split())
    return {"schema":"chacha.dev/dark-intelligence-network-isolation-status/v1","namespace":nm["namespace"],"active":active}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True)
    sub=ap.add_subparsers(dest="cmd",required=True);sub.add_parser("plan");sub.add_parser("setup");sub.add_parser("teardown");sub.add_parser("status")
    a=ap.parse_args();policy=load(a.policy)
    if a.cmd=="plan":out=plan(policy)
    elif a.cmd=="setup":out=setup(policy)
    elif a.cmd=="status":out=status(policy)
    else:
        cleanup(policy);out={"schema":"chacha.dev/dark-intelligence-network-isolation-teardown/v1","status":"PASS"}
    print(json.dumps(out,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V801_NETWORK_ISOLATION_"+a.cmd.upper()+"=PASS")
    return 0

if __name__=="__main__": raise SystemExit(main())
