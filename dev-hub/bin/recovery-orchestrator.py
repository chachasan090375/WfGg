#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

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
    print("CHACHA_RECOVERY_ORCHESTRATOR=PASS")
    print("RECOVERY_ACTION="+action)
if __name__=="__main__":main()
