#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,time,uuid
from pathlib import Path
from typing import Any

DEFAULT_STOP=Path("/opt/chacha-dev/runtime/control/emergency-stop.json")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    t=path.with_name(path.name+f".tmp-{os.getpid()}")
    t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(t,path)

def stop_active(path:Path)->bool:
    try:return bool(load(path).get("active"))
    except Exception:return False

def unit_name(run_id:str,variant:str)->str:
    token=hashlib.sha256((run_id+":"+variant).encode()).hexdigest()[:16]
    return f"chacha-dev-preview@{token}.service"

def guardian_event(repo_root:Path,output_dir:Path,phase:str,evidence:dict[str,Any])->dict[str,Any]:
    if not Path("/opt/chacha-dev/runtime").exists():
        return {"status":"NON_RUNTIME_TEST_BYPASS"}
    client=repo_root/"dev-hub/bin/guardian-client.py"
    policy=repo_root/"dev-hub/config/guardian-runtime-policy.v1.json"
    if not client.is_file() or not policy.is_file():
        return {"status":"UNAVAILABLE"}
    event={
      "schema":"chacha.dev/governance-action/v1",
      "event_id":"gov-"+uuid.uuid4().hex,
      "phase":phase,
      "actor":"comparative-pilot",
      "subject_role":"comparative-pilot",
      "action":"RUN_COMPARATIVE_PILOT",
      "task_kind":"architecture-comparative-pilot",
      "permission":"workspace-write",
      "project_id":"platform-global",
      "run_id":evidence.get("run_id"),
      "adapters":[],
      "evidence":{
        "isolated_capsules":bool(evidence.get("isolated_capsules")),
        "same_benchmark_contract":bool(evidence.get("same_benchmark_contract")),
        "emergency_stop_active":stop_active(DEFAULT_STOP),
        "result_status":evidence.get("result_status")
      },
      "context":{"resource_class":"light","human_approval_required":False,"storage_preflight_required":False}
    }
    gd=output_dir/"guardian";gd.mkdir(parents=True,exist_ok=True)
    ep=gd/(event["event_id"]+".json");save(ep,event)
    p=subprocess.run([sys.executable,str(client),"--policy",str(policy),"check","--event",str(ep)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=25)
    try:v=json.loads(p.stdout.strip())
    except Exception:v={"status":"UNAVAILABLE","reason":"INVALID_RESPONSE"}
    save(gd/(event["event_id"]+".verdict.json"),v)
    if str(v.get("verdict")) in {"BLOCK","CRITICAL"}:
        raise RuntimeError("GUARDIAN_COMPARATIVE_PILOT_BLOCK:"+str(v.get("reason_codes") or []))
    return v

def expand_argv(argv:list[Any],variant:str,architecture:Path,result:Path)->list[str]:
    out=[]
    repl={"{variant}":variant,"{architecture_json}":str(architecture),"{result_json}":str(result)}
    for raw in argv:
        s=str(raw)
        for k,v in repl.items():s=s.replace(k,v)
        out.append(s)
    return out

def valid_metrics(x:dict[str,Any])->bool:
    required=["acceptance_pass","quality_score","stability_score","latency_ms","memory_mb","external_spend_eur"]
    return all(k in x for k in required)

def rank_key(x:dict[str,Any])->tuple:
    # Hard validity and zero-spend dominance are handled before this key.
    return (
      -float(x.get("quality_score") or 0),
      -float(x.get("stability_score") or 0),
      float(x.get("error_rate") or 0),
      float(x.get("latency_ms") or 1e18),
      float(x.get("memory_mb") or 1e18),
    )

def choose(results:dict[str,dict[str,Any]])->tuple[str|None,str]:
    valid={k:v for k,v in results.items() if v.get("acceptance_pass") is True}
    if not valid:return None,"NO_VARIANT_PASSED_ACCEPTANCE"
    zero={k:v for k,v in valid.items() if float(v.get("external_spend_eur") or 0)==0}
    pool=zero if zero else valid
    ordered=sorted(pool.items(),key=lambda kv:rank_key(kv[1]))
    if len(ordered)==1:return ordered[0][0],"ONLY_VALID_VARIANT"
    if rank_key(ordered[0][1])==rank_key(ordered[1][1]):return None,"METRIC_TIE"
    return ordered[0][0],"LEXICOGRAPHIC_RUNTIME_EVIDENCE"

def run_variant(run_id:str,variant:str,architecture_obj:dict[str,Any],harness:dict[str,Any],root:Path)->dict[str,Any]:
    if stop_active(DEFAULT_STOP): raise RuntimeError("CHACHA_DEV_EMERGENCY_STOP_ACTIVE")
    workspace=root/variant;workspace.mkdir(parents=True,exist_ok=True)
    architecture_path=workspace/"architecture.json";result_path=workspace/"metrics.json"
    save(architecture_path,architecture_obj)
    argv=expand_argv(harness.get("argv") or [],variant,architecture_path,result_path)
    if not argv:raise RuntimeError("COMPARATIVE_PILOT_HARNESS_ARGV_MISSING")
    budget=harness.get("resource_budget") or {}
    mem=max(64,int(budget.get("memory_mb") or 256))
    cpu=max(1,min(10000,int(budget.get("cpu_weight") or 50)))
    tasks=max(1,int(budget.get("tasks_max") or 8))
    timeout=max(10,int(budget.get("timeout_seconds") or 120))
    unit=unit_name(run_id,variant)
    cmd=[
      "/usr/bin/systemd-run","--wait","--collect","--pipe","--unit="+unit,
      "--property=MemoryMax="+str(mem)+"M","--property=CPUWeight="+str(cpu),
      "--property=TasksMax="+str(tasks),"--property=RuntimeMaxSec="+str(timeout),
      "--property=KillMode=mixed","--working-directory="+str(workspace),
      *argv
    ]
    started=time.monotonic()
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout+30)
    elapsed_ms=round((time.monotonic()-started)*1000,3)
    if p.returncode!=0:
        return {"variant":variant,"acceptance_pass":False,"quality_score":0,"stability_score":0,
                "latency_ms":elapsed_ms,"memory_mb":mem,"external_spend_eur":0,
                "error_rate":1,"failure":"HARNESS_EXIT_"+str(p.returncode),
                "stdout":p.stdout[-1000:],"stderr":p.stderr[-1000:],"unit":unit}
    if not result_path.is_file():
        return {"variant":variant,"acceptance_pass":False,"quality_score":0,"stability_score":0,
                "latency_ms":elapsed_ms,"memory_mb":mem,"external_spend_eur":0,
                "error_rate":1,"failure":"METRICS_FILE_MISSING","unit":unit}
    m=load(result_path)
    if not valid_metrics(m):
        return {"variant":variant,"acceptance_pass":False,"quality_score":0,"stability_score":0,
                "latency_ms":elapsed_ms,"memory_mb":mem,"external_spend_eur":0,
                "error_rate":1,"failure":"METRICS_SCHEMA_INVALID","unit":unit}
    m={**m,"variant":variant,"unit":unit,"wall_clock_ms":elapsed_ms,"resource_limit_memory_mb":mem}
    return m

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--portfolio",type=Path,required=True)
    ap.add_argument("--harness",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime/comparative-pilots"))
    ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args()
    portfolio=load(a.portfolio)
    if portfolio.get("mode")!="COMPARATIVE_PILOT_REQUIRED":
        save(a.output,{"schema":"chacha.dev/architecture-comparative-pilot-result/v1","status":"NOT_REQUIRED",
                       "resolved":False,"portfolio_mode":portfolio.get("mode")})
        print("CHACHA_DEV_V615_COMPARATIVE_PILOT=NOT_REQUIRED")
        return 0
    if not a.harness or not a.harness.is_file():
        save(a.output,{"schema":"chacha.dev/architecture-comparative-pilot-result/v1","status":"BLOCKED",
                       "resolved":False,"reason":"REAL_BENCHMARK_HARNESS_REQUIRED",
                       "functional_signature":(portfolio.get("historical_best") or {}).get("functional_signature")})
        print("CHACHA_DEV_V615_COMPARATIVE_PILOT=BLOCKED reason=REAL_BENCHMARK_HARNESS_REQUIRED")
        return 0
    harness=load(a.harness)
    if harness.get("schema")!="chacha.dev/comparative-pilot-harness/v1":
        raise RuntimeError("COMPARATIVE_PILOT_HARNESS_SCHEMA_INVALID")
    historical=portfolio.get("historical_best") or {}
    current=portfolio.get("current_foundry_candidate") or {}
    if not historical.get("components") or not current.get("packages"):
        raise RuntimeError("COMPARATIVE_PILOT_CANDIDATES_INCOMPLETE")
    run_id="cmp-"+time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())+"-"+uuid.uuid4().hex[:8]
    run_root=a.runtime_root/run_id
    evidence={"run_id":run_id,"isolated_capsules":True,"same_benchmark_contract":True}
    guardian_event(a.repo_root.resolve(),run_root,"PRE_ACTION",evidence)
    if a.dry_run:
        result={"schema":"chacha.dev/architecture-comparative-pilot-result/v1","status":"DRY_RUN","resolved":False,
                "run_id":run_id,"same_benchmark_contract":True,"isolated_capsules":True}
        save(a.output,result);print("CHACHA_DEV_V615_COMPARATIVE_PILOT=DRY_RUN");return 0
    results={
      "HISTORICAL":run_variant(run_id,"HISTORICAL",historical.get("components") or {},harness,run_root),
      "CURRENT":run_variant(run_id,"CURRENT",{"packages":current.get("packages") or []},harness,run_root)
    }
    winner,reason=choose(results)
    resolved=winner is not None
    result={
      "schema":"chacha.dev/architecture-comparative-pilot-result/v1",
      "status":"PASS" if resolved else "UNRESOLVED",
      "resolved":resolved,"winner":winner,"reason":reason,"run_id":run_id,
      "functional_signature":historical.get("functional_signature"),
      "historical":{"architecture_id":historical.get("architecture_id"),"version":historical.get("version")},
      "results":results,"same_benchmark_contract":True,"isolated_capsules":True,
      "automatic_external_spend_eur":0
    }
    save(a.output,result)
    guardian_event(a.repo_root.resolve(),run_root,"POST_ACTION",{**evidence,"result_status":result["status"]})
    print("CHACHA_DEV_V615_COMPARATIVE_PILOT="+result["status"])
    print("RESOLVED="+("YES" if resolved else "NO"))
    if winner:print("WINNER="+winner)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
