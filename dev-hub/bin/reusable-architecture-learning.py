#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,re,subprocess,sys,tempfile,time
from pathlib import Path

def load(p:Path):
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x
def canon(v): return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def digest(v): return hashlib.sha256(canon(v).encode()).hexdigest()
def now_iso(): return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def slug(x): return re.sub(r"[^A-Za-z0-9._-]+","_",str(x)).strip("._")[:120] or "unknown"

def project_signature(preplan:dict)->str:
    packages=[]
    for p in preplan.get("packages") or []:
        if not isinstance(p,dict): continue
        packages.append({"domain":str(p.get("domain") or ""),"kind":str(p.get("kind") or ""),
                         "capabilities":sorted(set(map(str,p.get("capabilities") or [])))})
    packages.sort(key=lambda x:(x["domain"],x["kind"],x["capabilities"]))
    return digest({"packages":packages})

def publish_nas(record):
    adapter=Path(os.environ.get("CHACHA_NAS_ADAPTER","/opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter"))
    if not adapter.is_file(): return {"status":"DEFERRED","reason":"NAS_ADAPTER_MISSING"}
    d=digest(record);day=now_iso()[:10].replace("-","")
    remote=f"knowledge/reusable-architectures/{record['functional_signature'][:20]}/{day}/{slug(record['version'])}-{d[:12]}.json"
    with tempfile.TemporaryDirectory(prefix="chacha-arch-memory-") as td:
        td=Path(td);local=td/"architecture-record.json"
        local.write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        env={"schema":"chacha.dev/dispatch-envelope/v1","project":"chacha-dev","transition":"reusable-architecture-memory-persist",
             "run_id":"architecture-memory-"+d[:16],"wave":1,
             "task":{"id":"architecture-memory:"+d[:16],"kind":"knowledge-event",
                     "description":"Persist reusable complete architecture memory.",
                     "owner_role":"knowledge-compiler-agent","permission":"workspace-write",
                     "outputs":[{"type":"artifact","id":remote}],"verification":{"required":True,"mode":"machine"}},
             "bindings":[{"capability":"backup-store","provider":"nas","adapter":"nas-ssh-adapter","fallback_used":False,"health_state":"HEALTHY"}],
             "policy_context":{"resource_class":"light","requires_storage_preflight":False,
                               "human_approval_required":False,"approval_id":None,"timeout_seconds":30},
             "workspace":str(td),"metadata":{"nas_storage":{"action":"put-file","local_path":"architecture-record.json",
                                                           "remote_path":remote,"reserve_mb":1024}}}
        p=subprocess.run([str(adapter)],input=json.dumps(env).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=45)
        if p.returncode!=0:return {"status":"DEFERRED","reason":"NAS_PUBLISH_FAILED"}
        try:r=json.loads(p.stdout)
        except Exception:return {"status":"DEFERRED","reason":"NAS_RESPONSE_INVALID"}
        if r.get("status")=="OK" or r.get("summary")=="NAS_DESTINATION_ALREADY_EXISTS":
            return {"status":"PERSISTED","remote":remote}
        return {"status":"DEFERRED","reason":str(r.get("summary") or r.get("status"))}

def main():
    ap=argparse.ArgumentParser()
    for n in ("acceptance","preplan","architecture_council","branch_topology","agent_topology",
              "capability_foundry","runtime_wave_plan","technology_snapshot","registry","registry_db","output"):
        ap.add_argument("--"+n.replace("_","-"),required=True,type=Path)
    ap.add_argument("--metrics",type=Path);ap.add_argument("--incidents",type=Path)
    ap.add_argument("--nas-mode",choices=["REQUIRED","OPTIONAL","DISABLED"],default="REQUIRED")
    a=ap.parse_args()
    acc=load(a.acceptance)
    if acc.get("accepted") is not True: raise SystemExit("ARCHITECTURE_LEARNING_REQUIRES_ACCEPTED_DELIVERY")
    pre=load(a.preplan);council=load(a.architecture_council);branch=load(a.branch_topology)
    agent=load(a.agent_topology);cap=load(a.capability_foundry);waves=load(a.runtime_wave_plan);snap=load(a.technology_snapshot)
    metrics=load(a.metrics) if a.metrics and a.metrics.exists() else {}
    incidents_doc=load(a.incidents) if a.incidents and a.incidents.exists() else {}
    required=[x for x in acc.get("criteria") or [] if x.get("required",True)]
    passed=[x for x in required if x.get("state")=="PASS"]
    acceptance_quality=100.0*(len(passed)/max(1,len(required)))
    project_metrics=metrics.get("project") or {}
    incidents=incidents_doc.get("project") or []
    if not isinstance(incidents,list): incidents=[]
    cost=float(council.get("automatic_external_spend_eur") or 0)
    signature=project_signature(pre)
    packages=[]
    premap={str(x.get("id")):x for x in pre.get("packages") or [] if isinstance(x,dict)}
    for d in council.get("decisions") or []:
        if not isinstance(d,dict): continue
        p=premap.get(str(d.get("package_id"))) or {}
        packages.append({
          "domain":str(d.get("domain") or p.get("domain") or ""),
          "kind":str(p.get("kind") or ""),
          "capabilities":sorted(set(map(str,d.get("capabilities") or p.get("capabilities") or []))),
          "architecture":d.get("architecture"),
          "architecture_source":d.get("architecture_source"),
          "selected_reuse":d.get("selected_reuse"),
          "agent_decision":(d.get("agent_foundry_opinion") or {}).get("decision")
        })
    composition={
      "packages":packages,
      "agent_topology":agent.get("decisions") or [],
      "capability_foundry":cap.get("plans") or [],
      "runtime_waves":waves.get("waves") or [],
      "mandatory_advisors":council.get("mandatory_advisors") or []
    }
    version="system-"+digest(composition)[:12]
    architecture_id="architecture-"+signature[:20]
    quality=float(project_metrics.get("quality_score") if project_metrics.get("quality_score") is not None else acceptance_quality)
    state="ADOPT" if council.get("dispatch_allowed") is True and cost==0 and quality>=95 and not incidents else "CATALOG_CANDIDATE"
    record={
      "schema":"chacha.dev/reusable-architecture-record/v1",
      "architecture_id":architecture_id,"version":version,"functional_signature":signature,
      "components":composition,"qualification_status":"PASS","state":state,
      "technology_revalidated_at":snap.get("generated_at") or now_iso(),
      "technology_snapshot_digest":snap.get("snapshot_digest"),
      "external_spend_eur":cost,"quality_score":quality,
      "success_count":1,"failure_count":0,"increment_existing":True,
      "latency_ms":project_metrics.get("latency_ms"),"memory_mb":project_metrics.get("memory_mb"),
      "incident_count":len(incidents),
      "last_incident_at":(incidents[-1].get("observed_at") if incidents and isinstance(incidents[-1],dict) else None),
      "last_used_at":now_iso(),
      "evidence":{"acceptance_schema":acc.get("schema"),"council_version":council.get("version"),
                  "dispatch_allowed":council.get("dispatch_allowed"),"project_metrics":project_metrics,
                  "incidents":incidents}
    }
    nas={"status":"DISABLED_FOR_TEST"} if a.nas_mode=="DISABLED" else publish_nas(record)
    if a.nas_mode=="REQUIRED" and nas.get("status")!="PERSISTED":
        raise SystemExit("ARCHITECTURE_MEMORY_NAS_NOT_PERSISTED:"+str(nas.get("reason") or nas.get("status")))
    record["nas"]=nas
    a.output.parent.mkdir(parents=True,exist_ok=True)
    temp=a.output.parent/(version+".record.json");temp.write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    p=subprocess.run([sys.executable,str(a.registry),"--db",str(a.registry_db),"register","--record",str(temp)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    if p.returncode!=0: raise SystemExit("ARCHITECTURE_REGISTRY_REGISTER_FAILED:"+p.stderr+p.stdout)
    result={"schema":"chacha.dev/reusable-architecture-learning-result/v1","accepted":True,
            "architecture_id":architecture_id,"version":version,"state":state,
            "functional_signature":signature,"nas":nas,"quality_score":quality,
            "external_spend_eur":cost,"incident_count":len(incidents)}
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_V613_REUSABLE_ARCHITECTURE_LEARNING=PASS")
    print("STATE="+state)
if __name__=="__main__":main()
