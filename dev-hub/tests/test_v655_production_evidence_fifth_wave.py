#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_verified_evidence_backfill as backfill
import agent_observation_bus as aob
import agent_benchmark_adapter_runner as runner
import agent_benchmark_evidence_promoter as promoter
import agent_fleet_observatory as afo
import agent_evolution_controller as aec

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json");bus_policy=load(CFG/"agent-observation-bus.v1.json")
evo=load(CFG/"agent-evolution.v1.json");adapter_cfg=load(CFG/"agent-benchmark-adapters.v1.json")
bus_policy["historical_verified_backfill"]["minimum_age_minutes"]=0
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
ids=["backend-api-architect","frontend-architect","product-domain-architect","documentation-adr-agent"]
aliases={"backend-api":"backend-api-architect","frontend":"frontend-architect","product-domain":"product-domain-architect","documentation":"documentation-adr-agent"}

with tempfile.TemporaryDirectory(prefix="v655-production-backfill-") as td:
 rt=Path(td)
 for i,(role,aid) in enumerate(aliases.items(),1):
  caps=(routing["roles"][aid].get("capabilities") or [])
  cap=str(caps[0]) if caps else "benchmark-cap"
  proj="prod-"+aid;tid="task-"+str(i)
  graph={"schema":"chacha.dev/task-graph/v1","project":proj,"tasks":[{"id":tid,"owner_role":role,"capabilities":[cap]}]}
  save(rt/"plans"/proj/"DESIGN-to-IMPLEMENT.task-graph.json",graph)
  d=rt/"transactions"/proj/("ctx-"+str(i));d.mkdir(parents=True,exist_ok=True)
  digest="sha256:"+("%064x"%i)
  result={"schema":"chacha.dev/task-result/v1","project":proj,"task_id":tid,"status":"OK",
    "producer":"producer-"+role,"observed_at":"2026-09-20T00:00:00Z",
    "evidence":[{"kind":"file","source":"/evidence/"+tid,"digest":digest}],
    "verification":{"status":"VERIFIED","method":"machine","verifier":"independent-broker","observed_at":"2026-09-20T00:01:00Z"},
    "outputs":[{"type":"artifact","id":tid,"status":"OK"}]}
  save(d/"verified-task-result.json",result)
  report={"schema":"chacha.dev/verification-report/v1","project":proj,"task_id":tid,
    "verifier":"independent-broker","method":"machine","status":"VERIFIED","observed_at":"2026-09-20T00:01:00Z",
    "source_result_digest":"sha256:"+("%064x"%(100+i)),
    "checks":[{"id":"independent-verifier","status":"PASS"},{"id":"evidence-present","status":"PASS"}]}
  save(d/"verification-report.json",report)

 # Invalid self-verification must never be promoted.
 badproj="bad-self";save(rt/"plans"/badproj/"graph.task-graph.json",{"schema":"chacha.dev/task-graph/v1","project":badproj,
   "tasks":[{"id":"bad-task","owner_role":"backend-api","capabilities":[routing["roles"]["backend-api-architect"]["capabilities"][0]]}]})
 bd=rt/"transactions"/badproj/"ctx-bad";bd.mkdir(parents=True,exist_ok=True)
 save(bd/"verified-task-result.json",{"schema":"chacha.dev/task-result/v1","project":badproj,"task_id":"bad-task","status":"OK",
   "producer":"same","evidence":[{"source":"/e","digest":"sha256:"+"a"*64}],
   "verification":{"status":"VERIFIED","verifier":"same","observed_at":"2026-09-20T00:00:00Z"}})
 save(bd/"verification-report.json",{"schema":"chacha.dev/verification-report/v1","project":badproj,"task_id":"bad-task",
   "verifier":"same","status":"VERIFIED","source_result_digest":"sha256:"+"b"*64,
   "checks":[{"id":"x","status":"PASS"}]})

 first=backfill.run(rt,fleet_policy,bus_policy,routing,seven,[project],False)
 assert first["counts"].get("inserted")==4,first
 assert first["counts"].get("invalid")==1,first
 assert first["retroactive_reassessment"] is False,first
 chain=aob.verify_chain(rt,bus_policy);assert chain["status"]=="PASS" and chain["event_count"]==4,chain
 second=backfill.run(rt,fleet_policy,bus_policy,routing,seven,[project],False)
 assert second["counts"].get("inserted",0)==0,second
 assert second["counts"].get("already_present")==4,second

 metrics=afo.build_metrics(inv,rt,fleet_policy)
 for aid in ids:
  m=metrics[aid]
  for d in ["accuracy","evidence_quality","coverage","handoff_quality"]:
   assert m["dimensions"][d]["status"]=="MEASURED",(aid,d,m["dimensions"][d])
   assert m["dimensions"][d].get("evidence_scope")!="BENCHMARK_ONLY",(aid,d,m["dimensions"][d])

 runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v655-test"}
 for aid in ids:
  raw=runner.run(aid,ROOT,"rev-v655",adapter_cfg)
  assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["canonical_observation_bus_writes"] is False,raw
  path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v655.json"
  pr=promoter.promote(raw,"rev-v655",adapter_cfg,path);assert pr["promoted"] is True,(aid,pr)

 metrics=afo.build_metrics(inv,rt,fleet_policy)
 for aid in ids:
  sc=aec.score(aid,metrics[aid],evo)
  assert sc["production_measurement_coverage_pct"]>=40.0,(aid,sc)
  assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
  prod=set(sc.get("production_measured_dimensions") or []);bench=set(sc.get("benchmark_measured_dimensions") or [])
  assert not(prod&bench),(aid,prod,bench)
  for d in prod:
   assert metrics[aid]["dimensions"][d].get("evidence_scope")!="BENCHMARK_ONLY",(aid,d)
  assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)

print("CHACHA_DEV_V655_HISTORICAL_VERIFIED_BACKFILL=PASS")
print("CHACHA_DEV_V655_BACKFILL_IDEMPOTENT=PASS")
print("CHACHA_DEV_V655_SELF_VERIFICATION_PROMOTION=BLOCKED")
print("CHACHA_DEV_V655_RETROACTIVE_REASSESSMENT=NO")
print("CHACHA_DEV_V655_PRODUCTION_COVERAGE_HANDOFF=PASS")
print("CHACHA_DEV_V655_BACKEND_API_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V655_FRONTEND_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V655_PRODUCT_DOMAIN_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V655_DOCUMENTATION_ADR_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V655_FIFTH_WAVE_TOTAL_COVERAGE_80=PASS")
print("CHACHA_DEV_V655_PRODUCTION_MEASUREMENT_PRECEDENCE=PASS")
print("CHACHA_DEV_V655_CANONICAL_OBSERVATION_BUS_BENCHMARK_WRITE=NO")
print("CHACHA_DEV_V655_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
