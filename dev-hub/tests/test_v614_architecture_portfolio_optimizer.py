#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OPT=ROOT/"dev-hub/bin/architecture-portfolio-optimizer.py"
REG=ROOT/"dev-hub/bin/reusable-architecture-registry.py"
COUNCIL=ROOT/"dev-hub/bin/architecture-decision-council.py"
POLICY=ROOT/"dev-hub/config/architecture-portfolio-optimizer.v1.json"
COUNCIL_POLICY=ROOT/"dev-hub/config/architecture-decision-council.v1.json"

def run_opt(td,db):
    out=td/"portfolio.json"
    p=subprocess.run(["python3",str(OPT),"--repo-root",str(ROOT),"--preplan",str(td/"pre.json"),
                      "--branch-topology",str(td/"branch.json"),"--agent-topology",str(td/"agent.json"),
                      "--architecture-memory-db",str(db),"--policy",str(POLICY),"--output",str(out)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    assert p.returncode==0,(p.stdout,p.stderr)
    return json.load(open(out))

with tempfile.TemporaryDirectory(prefix="chacha-v614-") as d:
    td=Path(d);db=td/"arch.db"
    pre={"schema":"chacha.dev/domain-plan/v1","packages":[{"id":"web","domain":"web-ui","kind":"primary","capabilities":["static-web"]}]}
    branch={"schema":"chacha.dev/branch-topology/v1","blocked":[],"decisions":[{
      "package_id":"web","domain":"web-ui","architecture":{"pattern":"edge-static","runtime":"none"},
      "chosen_cost":{"external_spend_eur":0}
    }]}
    agent={"schema":"chacha.dev/agent-topology/v1","decisions":[{"package_id":"web","domain":"web-ui","decision":"TOOL_ONLY"}]}
    cap={"schema":"chacha.dev/capability-foundry-plan/v1","plans":[]}
    for n,x in [("pre",pre),("branch",branch),("agent",agent),("cap",cap)]:(td/(n+".json")).write_text(json.dumps(x))

    # No memory: current foundry synthesis is accepted.
    x=run_opt(td,db)
    assert x["mode"]=="CURRENT_FOUNDRY_SYNTHESIS",x
    assert x["decision_ready"] is True,x

    # Register a proven version that agrees with current foundries.
    sig=subprocess.check_output([
      "python3","-c",
      "import importlib.util,json,sys;s=importlib.util.spec_from_file_location('r',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(m.project_signature(json.load(open(sys.argv[2]))))",
      str(REG),str(td/"pre.json")],text=True).strip()
    rec={
      "architecture_id":"architecture-"+sig[:20],"version":"system-agree","functional_signature":sig,
      "components":{"packages":[{"domain":"web-ui","kind":"primary","capabilities":["static-web"],
                                "architecture":{"pattern":"edge-static","runtime":"none"},"agent_decision":"TOOL_ONLY"}]},
      "qualification_status":"PASS","state":"ADOPT",
      "technology_revalidated_at":time.strftime("%Y-%m-%dT%H:%M:%S",time.gmtime())+".123456Z",
      "technology_snapshot_digest":"snap","external_spend_eur":0,"quality_score":98,
      "success_count":12,"failure_count":0,"incident_count":0,"latency_ms":30,"memory_mb":64
    }
    p=td/"record.json";p.write_text(json.dumps(rec))
    subprocess.run(["python3",str(REG),"--db",str(db),"register","--record",str(p)],check=True,stdout=subprocess.DEVNULL)
    x=run_opt(td,db)
    assert x["mode"]=="FAST_REUSE",x
    assert x["decision_ready"] is True,x
    assert x["selected"]["version"]=="system-agree",x

    # A historically stronger version conflicts with today's foundry.
    rec2=dict(rec);rec2["version"]="system-conflict";rec2["quality_score"]=100;rec2["success_count"]=30
    rec2["components"]={"packages":[{"domain":"web-ui","kind":"primary","capabilities":["static-web"],
                                     "architecture":{"pattern":"different-edge","runtime":"none"},"agent_decision":"TOOL_ONLY"}]}
    p2=td/"record2.json";p2.write_text(json.dumps(rec2))
    subprocess.run(["python3",str(REG),"--db",str(db),"register","--record",str(p2)],check=True,stdout=subprocess.DEVNULL)
    x=run_opt(td,db)
    assert x["mode"]=="COMPARATIVE_PILOT_REQUIRED",x
    assert x["decision_ready"] is False,x
    assert x["historical_best"]["version"]=="system-conflict",x

    # The central council must block production dispatch until the comparison pilot resolves the conflict.
    out=td/"council.json"
    q=subprocess.run(["python3",str(COUNCIL),"--repo-root",str(ROOT),"--preplan",str(td/"pre.json"),
                      "--branch-topology",str(td/"branch.json"),"--agent-topology",str(td/"agent.json"),
                      "--capability-foundry",str(td/"cap.json"),"--policy",str(COUNCIL_POLICY),
                      "--reuse-db",str(td/"branch.db"),"--architecture-memory-db",str(db),"--output",str(out)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    assert q.returncode==0,(q.stdout,q.stderr)
    council=json.load(open(out))
    assert council["dispatch_allowed"] is False,council
    assert council["architecture_portfolio"]["mode"]=="COMPARATIVE_PILOT_REQUIRED",council
    assert council["decisions"][0]["mandatory_advisors"]["architecture-portfolio"]=="BLOCKED",council

print("CHACHA_DEV_V614_NO_MEMORY_FOUNDRY_PATH=PASS")
print("CHACHA_DEV_V614_FAST_REUSE_ON_CONSENSUS=PASS")
print("CHACHA_DEV_V614_CONFLICT_REQUIRES_COMPARATIVE_PILOT=PASS")
print("CHACHA_DEV_V614_PORTFOLIO_BLOCKS_PRODUCTION_ON_UNRESOLVED_CONFLICT=PASS")
