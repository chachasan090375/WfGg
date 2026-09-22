#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,time,tempfile,re
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x
def canon(v): return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v): return hashlib.sha256(canon(v).encode()).hexdigest()
def now_iso(): return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def slug(x): return re.sub(r"[^A-Za-z0-9._-]+","_",str(x)).strip("._")[:120] or "unknown"

def publish_nas(record):
    adapter=Path(os.environ.get("CHACHA_NAS_ADAPTER","/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"))
    if not adapter.is_file(): return {"status":"DEFERRED","reason":"NAS_ADAPTER_MISSING"}
    d=digest(record); day=now_iso()[:10].replace("-","")
    remote=f"knowledge/reusable-branches/{slug(record['domain'])}/{slug(record['branch_id'])}/{day}/{slug(record['version'])}-{d[:12]}.json"
    with tempfile.TemporaryDirectory(prefix="chacha-branch-memory-") as td:
        td=Path(td); local=td/"branch-record.json"; local.write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        env={"schema":"chacha.dev/dispatch-envelope/v1","project":"chacha-dev","transition":"reusable-branch-memory-persist",
             "run_id":"branch-memory-"+d[:16],"wave":1,
             "task":{"id":"branch-memory:"+d[:16],"kind":"knowledge-event","description":"Persist reusable branch knowledge record.",
                     "owner_role":"knowledge-compiler-agent","permission":"workspace-write",
                     "outputs":[{"type":"artifact","id":remote}],"verification":{"required":True,"mode":"machine"}},
             "bindings":[{"capability":"backup-store","provider":"nas","adapter":"nas-ssh-adapter","fallback_used":False,"health_state":"HEALTHY"}],
             "policy_context":{"resource_class":"light","requires_storage_preflight":False,"human_approval_required":False,"approval_id":None,"timeout_seconds":30},
             "workspace":str(td),"metadata":{"nas_storage":{"action":"put-file","local_path":"branch-record.json","remote_path":remote,"reserve_mb":1024}}}
        p=subprocess.run([str(adapter)],input=json.dumps(env).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=45)
        if p.returncode!=0:return {"status":"DEFERRED","reason":"NAS_PUBLISH_FAILED"}
        try:r=json.loads(p.stdout)
        except Exception:return {"status":"DEFERRED","reason":"NAS_RESPONSE_INVALID"}
        if r.get("status")=="OK" or r.get("summary")=="NAS_DESTINATION_ALREADY_EXISTS": return {"status":"PERSISTED","remote":remote}
        return {"status":"DEFERRED","reason":str(r.get("summary") or r.get("status"))}

def caps_by_package(pre):
    return {str(x.get("id")):[str(c) for c in x.get("capabilities") or []] for x in pre.get("packages") or [] if isinstance(x,dict)}

def metrics_for(metrics,branch_id,package_id):
    rows=metrics.get("branches") or {}
    return rows.get(branch_id) or rows.get(package_id) or {}

def incidents_for(incidents,branch_id,package_id):
    rows=incidents.get("branches") or {}
    x=rows.get(branch_id) or rows.get(package_id) or []
    return x if isinstance(x,list) else []

def promotion_state(decision,incidents,quality,cost):
    if decision=="CREATE_PROJECT_LOCAL_BRANCH": return "PROJECT_LOCAL"
    if incidents: return "CATALOG_CANDIDATE"
    if cost!=0: return "CATALOG_CANDIDATE"
    if quality<95: return "CATALOG_CANDIDATE"
    return "ADOPT"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--acceptance",required=True,type=Path)
    ap.add_argument("--branch-topology",required=True,type=Path)
    ap.add_argument("--preplan",required=True,type=Path)
    ap.add_argument("--technology-snapshot",required=True,type=Path)
    ap.add_argument("--registry",required=True,type=Path)
    ap.add_argument("--registry-db",required=True,type=Path)
    ap.add_argument("--metrics",type=Path)
    ap.add_argument("--incidents",type=Path)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--nas-mode",choices=["REQUIRED","OPTIONAL","DISABLED"],default="REQUIRED")
    a=ap.parse_args()
    acc,topo,pre,snap=map(load,[a.acceptance,a.branch_topology,a.preplan,a.technology_snapshot])
    if acc.get("accepted") is not True:
        raise SystemExit("BRANCH_LEARNING_REQUIRES_ACCEPTED_DELIVERY")
    metrics=load(a.metrics) if a.metrics and a.metrics.exists() else {}
    incidents_doc=load(a.incidents) if a.incidents and a.incidents.exists() else {}
    capmap=caps_by_package(pre)
    required=[x for x in acc.get("criteria") or [] if x.get("required",True)]
    passed=[x for x in required if x.get("state")=="PASS"]
    acceptance_quality=100.0*(len(passed)/max(1,len(required)))
    out=[]
    for d in topo.get("decisions") or []:
        if not isinstance(d,dict): continue
        if d.get("decision")=="MEMORY_ONLY": continue
        pid=str(d.get("package_id") or "");domain=str(d.get("domain") or "")
        arch=d.get("architecture")
        if not isinstance(arch,dict): continue
        branch_id=f"generic:{domain}:{str(d.get('kind') or 'primary')}"
        version="arch-"+digest(arch)[:12]
        m=metrics_for(metrics,str(d.get("branch_id") or ""),pid)
        incidents=incidents_for(incidents_doc,str(d.get("branch_id") or ""),pid)
        cost=float((d.get("chosen_cost") or {}).get("external_spend_eur") or 0)
        quality=float(m.get("quality_score") if m.get("quality_score") is not None else acceptance_quality)
        state=promotion_state(str(d.get("decision") or ""),incidents,quality,cost)
        record={
          "schema":"chacha.dev/reusable-branch-record/v2",
          "branch_id":branch_id,"version":version,"domain":domain,
          "capabilities":capmap.get(pid,[]),"architecture":arch,
          "qualification_status":"PASS","state":state,
          "technology_revalidated_at":snap.get("generated_at") or now_iso(),
          "technology_snapshot_digest":snap.get("snapshot_digest"),
          "external_spend_eur":cost,"quality_score":quality,
          "success_count":1,"failure_count":0,"increment_existing":True,
          "latency_ms":m.get("latency_ms"),"memory_mb":m.get("memory_mb"),
          "incident_count":len(incidents),
          "last_incident_at":(incidents[-1].get("observed_at") if incidents and isinstance(incidents[-1],dict) else None),
          "last_used_at":now_iso(),
          "evidence":{
            "acceptance_schema":acc.get("schema"),
            "branch_decision":d.get("decision"),
            "candidate_count":d.get("candidate_count"),
            "technology_watch":d.get("technology_watch"),
            "runtime_metrics":m,
            "incidents":incidents
          }
        }
        nas={"status":"DISABLED_FOR_TEST"} if a.nas_mode=="DISABLED" else publish_nas(record)
        if a.nas_mode=="REQUIRED" and nas.get("status")!="PERSISTED":
            raise SystemExit("BRANCH_MEMORY_NAS_NOT_PERSISTED:"+str(nas.get("reason") or nas.get("status")))
        record["nas"]=nas
        tmp=a.output.parent/(version+"-"+hashlib.sha256(branch_id.encode()).hexdigest()[:8]+".json")
        tmp.parent.mkdir(parents=True,exist_ok=True);tmp.write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        p=subprocess.run([sys.executable,str(a.registry),"--db",str(a.registry_db),"register","--record",str(tmp)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
        if p.returncode!=0: raise SystemExit("BRANCH_REGISTRY_REGISTER_FAILED:"+p.stderr+p.stdout)
        out.append({"branch_id":branch_id,"version":version,"state":state,"quality_score":quality,
                    "external_spend_eur":cost,"incident_count":len(incidents),"nas":nas})
    result={"schema":"chacha.dev/reusable-branch-learning-result/v1","accepted":True,"registered":out,
            "registered_count":len(out),"technology_snapshot_digest":snap.get("snapshot_digest")}
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V612_REUSABLE_BRANCH_LEARNING=PASS")
    print("REGISTERED="+str(len(out)))
if __name__=="__main__": main()
