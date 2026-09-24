#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
try:
    import agent_observation_bus as aob
except Exception:
    aob=None

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"));return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--incident",required=True);ap.add_argument("--policy",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();incident=load(a.incident);policy=load(a.policy)
    destructive=bool(incident.get("destructive_restore_required"))
    data_loss=bool(incident.get("data_loss_possible"))
    security=bool(incident.get("security_boundary_change"))
    rollback=bool(incident.get("rollback_available"))
    service=bool(incident.get("safe_service_restart_available"))
    if destructive or data_loss or security:
        action="ASK_HUMAN";autonomous=False
    elif rollback:
        action="ROLLBACK_REVERSIBLE_RELEASE";autonomous=True
    elif service:
        action="RESTART_SAFE_SERVICE";autonomous=True
    else:
        action="OPEN_INCIDENT";autonomous=True
    result={"schema":"chacha.dev/recovery-decision/v1","action":action,"autonomous":autonomous,
            "rerun_acceptance":action!="ASK_HUMAN","feed_learning":True}
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    if aob is not None and Path("/opt/chacha-dev/runtime").exists():
        try:
            project_id=str(incident.get("project_id") or "platform-global")
            aob.publish({
              "schema":"chacha.dev/agent-observation-event/v1",
              "event_id":"aobs-recovery-"+str(incident.get("incident_id") or Path(a.output).stem)+"-"+aob.runtime_revision()[:12],
              "event_type":"RECOVERY_DECISION_OBSERVED","source_id":"recovery-orchestrator","source_surface":"recovery-orchestrator",
              "project_id":project_id,"revision":aob.runtime_revision(),"subject_role":"autonomous-recovery-agent",
              "outcome":action,"verification":"OBSERVED",
              "capabilities":["recovery-orchestration","rollback-validation","health-checks"],
              "evidence_refs":[str(Path(a.output).resolve())],
              "details":{"autonomous":autonomous,"decision_only":True,"quality_claim":False}
            })
        except Exception:
            pass
    print("CHACHA_RECOVERY_ORCHESTRATOR=PASS")
    print("RECOVERY_ACTION="+action)
if __name__=="__main__":main()
