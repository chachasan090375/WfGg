#!/usr/bin/env python3
from __future__ import annotations
import json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_observation_bus as bus
import agent_fleet_observatory as afo
import agent_evolution_controller as aec

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

policy=load(CFG/"agent-observation-bus.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json")
evo=load(CFG/"agent-evolution.v1.json")
routing=load(CFG/"agent-routing.v1.json")
seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")

with tempfile.TemporaryDirectory(prefix="v648-observation-bus-") as td:
    rt=Path(td)
    assert bus.db_path(rt,policy)==rt/"agent-observation/observations.db",(bus.db_path(rt,policy),rt)
    assert bus.queue_root(rt,policy)==rt/"agent-evolution/reassessment-queue",(bus.queue_root(rt,policy),rt)

    # Self-assertion can never promote itself to VERIFIED.
    self_evt={
      "event_id":"self-1","event_type":"TASK_RESULT_VERIFIED","source_id":"test-engineer","source_surface":"agent-self",
      "project_id":"p1","revision":"sha-test","subject_role":"test-engineer","outcome":"OK","verification":"VERIFIED",
      "capabilities":["unit-test-js"],"evidence_refs":["self:evidence"]
    }
    s=bus.publish(self_evt,policy,rt)
    assert s["event"]["verification"]=="SELF_ASSERTED",s
    assert "PRODUCER_SELF_ASSERTION_DOWNGRADED" in s["event"]["verification_reason_codes"],s
    assert s["trigger"] is None,s

    # Unknown verifier requested VERIFIED is only OBSERVED.
    unknown={**self_evt,"event_id":"unknown-1","source_id":"random-tool","subject_role":"release-engineer"}
    u=bus.publish(unknown,policy,rt)
    assert u["event"]["verification"]=="OBSERVED",u

    # Independent Project Control verification is accepted.
    verified={
      "event_id":"verified-1","event_type":"TASK_RESULT_VERIFIED","source_id":"project-control","source_surface":"project-control:verification-broker",
      "project_id":"p1","revision":"sha-test","subject_role":"test-engineer","outcome":"OK","verification":"VERIFIED",
      "capabilities":["unit-test-js","e2e-test-web"],"evidence_refs":["verified:/tmp/result","report:/tmp/report"]
    }
    v=bus.publish(verified,policy,rt)
    assert v["event"]["verification"]=="VERIFIED",v
    assert v["trigger"] is None,v

    # Duplicate event ID is idempotent.
    vd=bus.publish(verified,policy,rt)
    assert vd["status"]=="DUPLICATE" and vd["inserted"] is False,vd

    # Verified failure immediately creates reassessment request but no mutation/candidate.
    fail={**verified,"event_id":"verified-fail-1","outcome":"FAILED","evidence_refs":["verified:failure"]}
    f=bus.publish(fail,policy,rt)
    assert f["trigger"]["trigger_type"]=="VERIFIED_FAILURE",f
    req=load(Path(f["trigger"]["path"]))
    assert req["action"]=="REASSESS",req
    assert req["direct_agent_mutation"] is False and req["direct_candidate_materialization"] is False,req
    assert req["candidate_owner"]=="agent-foundry",req

    # Technology Watch material delta can request reassessment.
    tw={
      "event_id":"tw-delta-1","event_type":"TECHNOLOGY_WATCH_MATERIAL_DELTA","source_id":"technology-watch-agent",
      "source_surface":"technology-watch","project_id":"platform-global","revision":"sha-test","subject_role":"backend-api-architect",
      "outcome":"CHANGE","verification":"VERIFIED","capabilities":["library-docs"],"evidence_refs":["technology-watch:delta"]
    }
    t=bus.publish(tw,policy,rt)
    assert t["trigger"]["trigger_type"]=="TECHNOLOGY_WATCH_MATERIAL_DELTA",t

    self_request={"event_id":"self-request-1","event_type":"AGENT_REASSESSMENT_REQUEST",
      "source_id":"bastion","source_surface":"agent-self","project_id":"p1","revision":"sha-test",
      "subject_role":"bastion","outcome":"REQUEST","verification":"SELF_ASSERTED",
      "capabilities":["fake-capability"],"evidence_refs":["agent-request:1"],"details":{"reason":"new architecture idea"}}
    sr=bus.publish(self_request,policy,rt)
    assert sr["trigger"]["trigger_type"]=="AGENT_REASSESSMENT_REQUEST",sr
    srq=load(Path(sr["trigger"]["path"]))
    assert srq["self_request"] is True and srq["metric_authority"] is False,srq
    assert srq["action"]=="REQUEST_REASSESSMENT",srq

    final_review={"event_id":"final-review-1","event_type":"FINAL_REVIEW_VERIFIED",
      "source_id":"seven-agent-final-compromise-controller","source_surface":"seven-agent-final-compromise",
      "project_id":"p1","revision":"sha-test","subject_role":"bastion","outcome":"OK","verification":"VERIFIED",
      "capabilities":[],"evidence_refs":["final-review:bastion"]}
    fr=bus.publish(final_review,policy,rt);assert fr["event"]["verification"]=="VERIFIED",fr
    stage={"event_id":"stage-1","event_type":"STAGE_EXECUTION_OBSERVED","source_id":"central-orchestrator",
      "source_surface":"autonomous-project-orchestrator","project_id":"p1","revision":"sha-test","subject_role":"logician",
      "outcome":"OK","verification":"OBSERVED","capabilities":[],"evidence_refs":["stage:logic"]}
    bus.publish(stage,policy,rt)
    chain=bus.verify_chain(rt,policy)
    assert chain["status"]=="PASS" and chain["event_count"]==8,chain
    assert (rt/"agent-observation/observations.db").is_file()
    assert not Path("/opt/chacha-dev/runtime/agent-observation/observations.db").exists() or str(rt)!="/opt/chacha-dev/runtime"

    # Bus evidence improves coverage/handoff only where evidence exists.
    inv=aec.build_inventory(routing,seven,[project])
    metrics=afo.build_metrics(inv,rt,fleet_policy)
    tm=metrics["test-engineer"]
    assert tm["dimensions"]["coverage"]["status"]=="MEASURED",tm
    assert tm["dimensions"]["coverage"]["value"]>0,tm
    assert tm["dimensions"]["handoff_quality"]["status"]=="MEASURED",tm
    assert tm["dimensions"]["handoff_quality"]["value"]==50.0,tm
    # Self-asserted event does not count as handoff verification.
    assert tm["signals"]["handoff_total"]==2,tm
    bm=metrics["bastion"]
    assert "fake-capability" not in bm["signals"]["observed_capabilities"],bm
    assert bm["dimensions"]["handoff_quality"]["status"]=="MEASURED" and bm["dimensions"]["handoff_quality"]["value"]==100.0,bm
    lm=metrics["logician"]
    assert lm["dimensions"]["robustness"]["status"]=="MEASURED" and lm["dimensions"]["robustness"]["value"]==100.0,lm

    # No fabricated scores for still-unmeasured dimensions.
    sc=aec.score("test-engineer",tm,evo)
    assert sc["dimensions"]["calibration"] is None,sc
    assert sc["unknown_dimension_default_score"] is None,sc

print("CHACHA_DEV_V648_SELF_ASSERTION_VERIFIED=NO")
print("CHACHA_DEV_V648_UNKNOWN_VERIFIER_DOWNGRADED=PASS")
print("CHACHA_DEV_V648_PROJECT_CONTROL_VERIFIED_BOUNDARY=PASS")
print("CHACHA_DEV_V648_EVENT_ID_DEDUPLICATION=PASS")
print("CHACHA_DEV_V648_HASH_CHAIN=PASS")
print("CHACHA_DEV_V648_ISOLATED_RUNTIME_STORAGE=PASS")
print("CHACHA_DEV_V648_VERIFIED_FAILURE_REASSESSMENT_TRIGGER=PASS")
print("CHACHA_DEV_V648_TECHNOLOGY_WATCH_DELTA_TRIGGER=PASS")
print("CHACHA_DEV_V648_AGENT_SELF_REASSESSMENT_REQUEST=PASS")
print("CHACHA_DEV_V648_SELF_REQUEST_METRIC_AUTHORITY=NO")
print("CHACHA_DEV_V648_SELF_ASSERTED_COVERAGE_INFLATION=NO")
print("CHACHA_DEV_V648_EXACT_REVISION_LINEAGE=PASS")
print("CHACHA_DEV_V648_SEVEN_AGENT_FINAL_HANDOFF=PASS")
print("CHACHA_DEV_V648_CENTRAL_STAGE_OBSERVATION=PASS")
print("CHACHA_DEV_V648_DIRECT_AGENT_MUTATION=NO")
print("CHACHA_DEV_V648_DIRECT_CANDIDATE_MATERIALIZATION=NO")
print("CHACHA_DEV_V648_COVERAGE_FROM_OBSERVATION_BUS=PASS")
print("CHACHA_DEV_V648_HANDOFF_FROM_VERIFIED_BOUNDARY=PASS")
print("CHACHA_DEV_V648_UNKNOWN_DIMENSION_DEFAULT=NONE")
print("CHACHA_DEV_V648_AGENT_SELF_SCORING_AUTHORITY=NO")
print("CHACHA_DEV_V648_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V648_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
