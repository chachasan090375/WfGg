#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_benchmark_adapter_runner as runner
import agent_benchmark_evidence_promoter as promoter
import agent_fleet_observatory as afo
import agent_evolution_controller as aec

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json");evo=load(CFG/"agent-evolution.v1.json")
adapter_cfg=load(CFG/"agent-benchmark-adapters.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
targets=["curator","intendant","knowledge-compiler-agent","uncertainty-resolution-agent"]
runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v657-test"}

with tempfile.TemporaryDirectory(prefix="v657-authority-") as td:
 rt=Path(td)
 # Real-format externally reverified specialist reviews: production evidence only for proven structural dimensions.
 for i,aid in enumerate(["curator","intendant"],1):
  for j,verdict in enumerate(["REVISE","ACCEPT"],1):
   p=rt/"plans"/f"project-{i}-{j}"/"automatic-finalization"/("a"*40)/("b"*24)/"reviews"/f"{aid}-source-reverified-review.json"
   review={"schema":"chacha.dev/compromise-agent-review/v1","agent":aid,"receipt_id":f"{aid}-{i}-{j}",
    "project_id":f"project-{i}-{j}","revision":"c"*40,"compromise_digest":"sha256:"+"d"*64,
    "verdict":verdict,"hard_objections":["NO_SPECIALIST_EVIDENCE"] if verdict=="REVISE" else [],
    "soft_objections":[],"evidence_refs":[] if verdict=="REVISE" else ["event:e1:sha256:"+"e"*64],
    "implementation_verified":True,"source_authority":"EXTERNAL","source_reverified":True,
    "source_payload_digest":"sha256:"+"f"*64,"post_implementation_second_read":True,
    "direct_mutation":False,"reviewed_at":"2026-09-23 15:00:00"}
   save(p,review)
 # Invalid review must not count.
 p=rt/"plans"/"bad"/"automatic-finalization"/("a"*40)/("b"*24)/"reviews"/"curator-source-reverified-review.json"
 save(p,{"schema":"chacha.dev/compromise-agent-review/v1","agent":"curator","receipt_id":"bad","project_id":"bad",
   "revision":"c"*40,"compromise_digest":"sha256:"+"d"*64,"verdict":"ACCEPT","hard_objections":[],"soft_objections":[],
   "evidence_refs":[],"implementation_verified":True,"source_authority":"EXTERNAL","source_reverified":False,
   "source_payload_digest":"sha256:"+"f"*64,"post_implementation_second_read":True,"direct_mutation":False})

 metrics=afo.build_metrics(inv,rt,fleet_policy)
 for aid in ["curator","intendant"]:
  sc=aec.score(aid,metrics[aid],evo)
  assert sc["production_measurement_coverage_pct"]==30.0,(aid,sc)
  for d in ["evidence_quality","handoff_quality","authority_discipline"]:
   assert metrics[aid]["dimensions"][d]["status"]=="MEASURED",(aid,d,metrics[aid]["dimensions"][d])
   assert metrics[aid]["dimensions"][d].get("evidence_scope")!="BENCHMARK_ONLY",(aid,d)

 for aid in targets:
  raw=runner.run(aid,ROOT,"rev-v657",adapter_cfg)
  assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["canonical_observation_bus_writes"] is False,raw
  path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v657.json"
  pr=promoter.promote(raw,"rev-v657",adapter_cfg,path);assert pr["promoted"] is True,(aid,pr)

 metrics=afo.build_metrics(inv,rt,fleet_policy)
 for aid in ["curator","intendant"]:
  sc=aec.score(aid,metrics[aid],evo);pl=aec.plan(aid,sc,evo)
  assert sc["production_measurement_coverage_pct"]==30.0,(aid,sc)
  assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
  assert sc["production_weighted_maturity_pct"]>=36.0,(aid,sc)
  assert sc["evidence_maturity_label"]=="MIXED_EVIDENCE",(aid,sc)
  assert pl["evidence_maturity"]["candidate_evidence_mature"] is False,(aid,pl)

 for aid in ["knowledge-compiler-agent","uncertainty-resolution-agent"]:
  sc=aec.score(aid,metrics[aid],evo);pl=aec.plan(aid,sc,evo)
  assert sc["production_measurement_coverage_pct"]==0.0,(aid,sc)
  assert sc["measurement_coverage_pct"]>=80.0,(aid,sc)
  assert sc["production_weighted_maturity_pct"]<=30.0,(aid,sc)
  assert sc["evidence_maturity_label"]=="BENCHMARK_HEAVY",(aid,sc)
  assert pl["evidence_maturity"]["candidate_evidence_mature"] is False,(aid,pl)
  assert pl["candidate"]["owner"] is None,(aid,pl)

print("CHACHA_DEV_V657_CURATOR_PRODUCTION_REVIEW_EVIDENCE=PASS")
print("CHACHA_DEV_V657_INTENDANT_PRODUCTION_REVIEW_EVIDENCE=PASS")
print("CHACHA_DEV_V657_CURATOR_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V657_INTENDANT_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V657_KNOWLEDGE_COMPILER_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V657_UNCERTAINTY_RESOLVER_EXECUTABLE_ADAPTER=PASS")
print("CHACHA_DEV_V657_REVISE_IS_NOT_ACCURACY_PROOF=PASS")
print("CHACHA_DEV_V657_BENCHMARK_ONLY_CANDIDATE_MATERIALIZATION=BLOCKED")
print("CHACHA_DEV_V657_PRODUCTION_MEASUREMENT_PRECEDENCE=PASS")
print("CHACHA_DEV_V657_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
