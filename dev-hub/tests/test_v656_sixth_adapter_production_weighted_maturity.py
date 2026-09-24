#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_benchmark_adapter_runner as runner
import agent_benchmark_evidence_promoter as promoter
import agent_fleet_observatory as afo
import agent_evolution_controller as aec
import agent_observation_bus as aob

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json");bus_policy=load(CFG/"agent-observation-bus.v1.json")
evo=load(CFG/"agent-evolution.v1.json");adapter_cfg=load(CFG/"agent-benchmark-adapters.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
targets=["test-engineer","performance-engineer","sre-observability-engineer"]
runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v656-test"}

with tempfile.TemporaryDirectory(prefix="v656-weighted-") as td:
 rt=Path(td)
 # Four independently verified production dimensions per target.
 # Project Control artifacts establish accuracy/evidence_quality; Observation Bus establishes coverage/handoff.
 for i,aid in enumerate(targets,1):
  caps=routing["roles"][aid]["capabilities"]
  proj="v656-"+aid
  tasks=[]
  for j,cap in enumerate(caps[:4],1):
   tid=f"{aid}-{j}";tasks.append({"id":tid,"owner_role":aid,"capabilities":[cap]})
  save(rt/"plans"/proj/"IMPLEMENT.task-graph.json",{"schema":"chacha.dev/task-graph/v1","project":proj,"tasks":tasks})
  for j,cap in enumerate(caps[:4],1):
   tid=f"{aid}-{j}";digest="sha256:"+("%064x"%(i*10+j));vdigest="sha256:"+("%064x"%(100+i*10+j))
   d=rt/"transactions"/proj/f"ctx-{j}";d.mkdir(parents=True,exist_ok=True)
   save(d/"verified-task-result.json",{"schema":"chacha.dev/task-result/v1","project":proj,"task_id":tid,"status":"OK",
    "producer":"run-controller","observed_at":"2026-09-20T00:00:00Z",
    "evidence":[{"kind":"file","source":f"/evidence/{aid}/{j}","digest":digest}],
    "verification":{"status":"VERIFIED","method":"machine","verifier":"verification-broker","observed_at":"2026-09-20T00:01:00Z"},
    "outputs":[{"type":"artifact","id":tid,"status":"OK"}]})
   save(d/"verification-report.json",{"schema":"chacha.dev/verification-report/v1","project":proj,"task_id":tid,
    "verifier":"verification-broker","method":"machine","status":"VERIFIED","observed_at":"2026-09-20T00:01:00Z",
    "source_result_digest":vdigest,"checks":[{"id":"independent-verifier","status":"PASS"},{"id":"evidence-present","status":"PASS"}]})
   event={"schema":"chacha.dev/agent-observation-event/v1","event_id":f"v656-prod-{i}-{j}",
    "event_type":"HISTORICAL_TASK_RESULT_VERIFIED","source_id":"project-control",
    "source_surface":"project-control:v656-test","project_id":proj,"task_id":tid,
    "subject_role":aid,"outcome":"OK","verification":"VERIFIED","revision":vdigest,
    "capabilities":[cap],"evidence_refs":[f"/evidence/{aid}/{j}#{digest}"],
    "observed_at":"2026-09-20T00:01:00Z","details":{"historical_verified_backfill":True,"retroactive_reassessment":False}}
   pub=aob.publish(event,bus_policy,rt);assert pub["inserted"] is True and pub["trigger"] is None,pub

 metrics=afo.build_metrics(inv,rt,fleet_policy)
 for aid in targets:
  before=aec.score(aid,metrics[aid],evo)
  assert before["production_measurement_coverage_pct"]>=40.0,(aid,before)
  assert before["benchmark_measurement_coverage_pct"]==0.0,(aid,before)
  assert before["production_weighted_maturity_pct"]>=28.0,(aid,before)

 for aid in targets:
  raw=runner.run(aid,ROOT,"rev-v656",adapter_cfg)
  assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["canonical_observation_bus_writes"] is False,raw
  path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v656.json"
  pr=promoter.promote(raw,"rev-v656",adapter_cfg,path);assert pr["promoted"] is True,(aid,pr)

 metrics=afo.build_metrics(inv,rt,fleet_policy)
 for aid in targets:
  sc=aec.score(aid,metrics[aid],evo);pl=aec.plan(aid,sc,evo)
  assert sc["production_measurement_coverage_pct"]>=40.0,(aid,sc)
  assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
  assert sc["production_weighted_maturity_pct"]>=40.0,(aid,sc)
  assert sc["evidence_maturity_label"] in {"MIXED_EVIDENCE","PRODUCTION_MATURE"},(aid,sc)
  prod=set(sc["production_measured_dimensions"]);bench=set(sc["benchmark_measured_dimensions"])
  assert not(prod&bench),(aid,prod,bench)
  assert pl["evidence_maturity"]["production_weighted_maturity_pct"]==sc["production_weighted_maturity_pct"],(aid,pl)
  assert sc["recommendation"]!="MEASURE_FIRST",(aid,sc)

 # 100% benchmark coverage must remain immature without production evidence.
 rawdims={d:{"status":"MEASURED","value":100.0} for d in aec.DIMENSIONS}
 fake={"dimensions":rawdims,"dimension_evidence":{d:{"evidence_scope":"BENCHMARK_ONLY"} for d in aec.DIMENSIONS}}
 bench=aec.score("benchmark-only-agent",fake,evo);plan=aec.plan("benchmark-only-agent",bench,evo)
 assert bench["measurement_coverage_pct"]==100.0,bench
 assert bench["production_measurement_coverage_pct"]==0.0,bench
 assert bench["production_weighted_maturity_pct"]==30.0,bench
 assert bench["evidence_maturity_label"]=="BENCHMARK_HEAVY",bench
 assert plan["evidence_maturity"]["candidate_evidence_mature"] is False,plan
 assert plan["candidate"]["owner"] is None,plan

 # Production-heavy evidence must outrank benchmark-heavy evidence at equal total coverage.
 pdims={d:{"status":"MEASURED","value":90.0} for d in aec.DIMENSIONS[:8]}
 pev={d:{"evidence_scope":"PRODUCTION"} for d in aec.DIMENSIONS[:8]}
 prod=aec.score("production-heavy-agent",{"dimensions":pdims,"dimension_evidence":pev},evo)
 assert prod["measurement_coverage_pct"]==80.0,prod
 assert prod["production_weighted_maturity_pct"]>bench["production_weighted_maturity_pct"],(prod,bench)

print("CHACHA_DEV_V656_TEST_ENGINEER_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V656_PERFORMANCE_ENGINEER_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V656_SRE_OBSERVABILITY_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V656_PRODUCTION_WEIGHTED_MATURITY=PASS")
print("CHACHA_DEV_V656_BENCHMARK_ONLY_MATURITY_LIMIT=PASS")
print("CHACHA_DEV_V656_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED")
print("CHACHA_DEV_V656_PRODUCTION_OUTRANKS_BENCHMARK=PASS")
print("CHACHA_DEV_V656_SIXTH_WAVE_TOTAL_COVERAGE_80=PASS")
print("CHACHA_DEV_V656_PRODUCTION_MEASUREMENT_PRECEDENCE=PASS")
print("CHACHA_DEV_V656_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
