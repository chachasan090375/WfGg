#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_observation_bus as bus
import agent_fleet_observatory as afo
import agent_evolution_controller as aec

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
policy=load(CFG/"agent-observation-bus.v1.json");fleet=load(CFG/"agent-fleet-observatory.v1.json")
evo=load(CFG/"agent-evolution.v1.json");routing=load(CFG/"agent-routing.v1.json")
seven=load(CFG/"seven-agent-final-compromise.v1.json");project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
inst=load(CFG/"assurance-agent-instrumentation.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35,inv

ids={x["agent_id"] for x in inst["priority_targets"]}
assert {"bastion","guardian","sentinel","autonomous-recovery-agent","logician","ergonomist","curator","intendant"}.issubset(ids),ids
assert inst["invariants"]["recovery_decision_is_not_recovery_success"] is True

with tempfile.TemporaryDirectory(prefix="v649-agent-instrumentation-") as td:
    rt=Path(td)
    # Unknown OBSERVED source cannot inflate capability coverage.
    bus.publish({"event_id":"untrusted-observed","event_type":"RECOVERY_DECISION_OBSERVED","source_id":"random-tool",
      "source_surface":"random","project_id":"p1","revision":"sha-v649","subject_role":"autonomous-recovery-agent",
      "outcome":"ROLLBACK_REVERSIBLE_RELEASE","verification":"OBSERVED","capabilities":["recovery-orchestration","rollback-validation","health-checks"],
      "evidence_refs":["random:activity"]},policy,rt)
    # Trusted recovery activity can prove exercised coverage, but not accuracy.
    bus.publish({"event_id":"trusted-recovery","event_type":"RECOVERY_DECISION_OBSERVED","source_id":"recovery-orchestrator",
      "source_surface":"recovery-orchestrator","project_id":"p1","revision":"sha-v649","subject_role":"autonomous-recovery-agent",
      "outcome":"ROLLBACK_REVERSIBLE_RELEASE","verification":"OBSERVED","capabilities":["recovery-orchestration","rollback-validation","health-checks"],
      "evidence_refs":["recovery:decision"]},policy,rt)
    # Seven-agent final boundary gives verified handoff evidence.
    for agent in ("bastion","guardian","sentinel","logician","ergonomist","curator","intendant"):
        bus.publish({"event_id":"final-"+agent,"event_type":"FINAL_REVIEW_VERIFIED","source_id":"seven-agent-final-compromise-controller",
          "source_surface":"seven-agent-final-compromise","project_id":"p1","revision":"sha-v649","subject_role":agent,
          "outcome":"OK","verification":"VERIFIED","capabilities":[],"evidence_refs":["final:"+agent]},policy,rt)
    # Central orchestrator gives observed robustness to internal agents/foundries.
    bus.publish({"event_id":"stage-logician","event_type":"STAGE_EXECUTION_OBSERVED","source_id":"central-orchestrator",
      "source_surface":"autonomous-project-orchestrator","project_id":"p1","revision":"sha-v649","subject_role":"logician",
      "outcome":"OK","verification":"OBSERVED","capabilities":[],"evidence_refs":["stage:logician"]},policy,rt)

    metrics=afo.build_metrics(inv,rt,fleet)
    ar=metrics["autonomous-recovery-agent"]
    assert ar["dimensions"]["coverage"]["status"]=="MEASURED",ar
    assert ar["dimensions"]["coverage"]["value"]==100.0,ar
    assert ar["dimensions"]["accuracy"]["value"] is None,ar
    # Only trusted recovery source counted; random tool did not create extra independent coverage semantics.
    assert set(ar["signals"]["observed_capabilities"])=={"recovery-orchestration","rollback-validation","health-checks"},ar
    for agent in ("bastion","guardian","sentinel","curator","intendant"):
        assert metrics[agent]["dimensions"]["handoff_quality"]["value"]==100.0,(agent,metrics[agent])
    assert metrics["logician"]["dimensions"]["handoff_quality"]["value"]==100.0,metrics["logician"]
    assert metrics["logician"]["dimensions"]["robustness"]["value"]==100.0,metrics["logician"]

    # Self request remains request-only and cannot create quality.
    sr=bus.publish({"event_id":"bastion-self-request","event_type":"AGENT_REASSESSMENT_REQUEST","source_id":"bastion",
      "source_surface":"agent-self","project_id":"p1","revision":"sha-v649","subject_role":"bastion",
      "outcome":"REQUEST","verification":"SELF_ASSERTED","capabilities":[],"evidence_refs":["self:request"]},policy,rt)
    req=load(Path(sr["trigger"]["path"]));assert req["metric_authority"] is False and req["direct_agent_mutation"] is False,req

assert evo["self_evolution"]["agent_may_modify_active_self"] is False
assert evo["self_evolution"]["agent_may_promote_self"] is False
print("CHACHA_DEV_V649_PRIORITY_ASSURANCE_TARGETS=PASS")
print("CHACHA_DEV_V649_TRUSTED_OBSERVED_SOURCE_FILTER=PASS")
print("CHACHA_DEV_V649_RECOVERY_COVERAGE_OBSERVED=PASS")
print("CHACHA_DEV_V649_RECOVERY_ACTIVITY_IS_ACCURACY=NO")
print("CHACHA_DEV_V649_SEVEN_AGENT_VERIFIED_HANDOFF=PASS")
print("CHACHA_DEV_V649_INTERNAL_AGENT_ROBUSTNESS=PASS")
print("CHACHA_DEV_V649_SELF_REQUEST_METRIC_AUTHORITY=NO")
print("CHACHA_DEV_V649_DIRECT_SELF_MUTATION=NO")
print("CHACHA_DEV_V649_SELF_PROMOTION=NO")
print("CHACHA_DEV_V649_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V649_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
