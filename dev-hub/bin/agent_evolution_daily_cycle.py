#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any
import agent_fleet_observatory as afo
import technology_watch_runtime as tw
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def safe(p:Path):
    try:return load(p)
    except Exception:return {}
def save(p:Path,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def now():return datetime.now(timezone.utc)
def iso(d):return d.isoformat().replace("+00:00","Z")
def parse(v):
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:return None
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"));a=ap.parse_args()
    root=a.repo_root.resolve();runtime=a.runtime_root.resolve();cfg=root/"dev-hub/config";ae=runtime/"agent-evolution";ae.mkdir(parents=True,exist_ok=True)
    routing=load(cfg/"agent-routing.v1.json");seven=load(cfg/"seven-agent-final-compromise.v1.json");project=load(root/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
    fp=load(cfg/"agent-fleet-observatory.v1.json");ep=load(cfg/"agent-evolution.v1.json")
    report=afo.build_report(root,runtime,fp,ep,routing,seven,[project]);save(ae/"fleet-observatory-latest.json",report)
    requests=[];qroot=runtime/"agent-evolution/reassessment-queue"
    if qroot.is_dir():
        for p in sorted(qroot.glob("*.json")):
            x=safe(p)
            if x.get("schema")=="chacha.dev/agent-reassessment-request/v1":requests.append(x)
    stamp=now();statep=ae/"cadence-state.json";state=safe(statep);cad=ep.get("cadence") or {}
    ld=parse(state.get("last_deep_audit_at"));lb=parse(state.get("last_ecosystem_benchmark_at"))
    deep=ld is None or stamp-ld>=timedelta(days=int(cad.get("deep_agent_audit_days") or 7))
    bench=lb is None or stamp-lb>=timedelta(days=int(cad.get("ecosystem_benchmark_days") or 30))
    scheduled=[]
    if deep:
        scheduled += [{"agent_id":x["agent_id"],"action":"DEEP_AGENT_AUDIT","candidate_owner":"agent-foundry","logician_challenge_required":True,"technology_watch_revalidation_required":True,"direct_agent_mutation":False} for x in report.get("agents") or []]
        state["last_deep_audit_at"]=iso(stamp)
    if bench:
        scheduled += [{"agent_id":x["agent_id"],"action":"ECOSYSTEM_BENCHMARK","candidate_owner":"agent-foundry","logician_challenge_required":True,"technology_watch_revalidation_required":True,"direct_agent_mutation":False} for x in report.get("agents") or []]
        state["last_ecosystem_benchmark_at"]=iso(stamp)
    state["last_lightweight_health_at"]=iso(stamp);save(statep,state)
    idx={"schema":"chacha.dev/agent-evolution-reassessment-index/v1","generated_at":iso(stamp),"event_requests":requests,"scheduled_actions":scheduled,
      "event_request_count":len(requests),"scheduled_action_count":len(scheduled),"direct_agent_mutation":False,"self_promotion":False,
      "candidate_owner":"agent-foundry","architecture_council_final_authority":True,"automatic_external_spend_eur":0}
    save(ae/"reassessment-queue-latest.json",idx)
    receipt={"schema":"chacha.dev/agent-evolution-daily-cycle/v1","generated_at":iso(stamp),"agent_count":report.get("agent_count"),
      "optimization_count":len(report.get("optimization_queue") or []),"measurement_count":len(report.get("measurement_queue") or []),
      "event_request_count":len(requests),"scheduled_action_count":len(scheduled),"deep_audit_due":deep,"ecosystem_benchmark_due":bench,
      "technology_watch":tw.snapshot_status(root),"direct_agent_mutation":False,"self_promotion":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
    save(ae/"daily-cycle-latest.json",receipt)
    print("CHACHA_DEV_V648_AGENT_EVOLUTION_DAILY_CYCLE=PASS");print("AGENT_COUNT="+str(receipt["agent_count"]))
    print("EVENT_REQUESTS="+str(len(requests)));print("SCHEDULED_ACTIONS="+str(len(scheduled)));print("CHACHA_DEV_V648_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
if __name__=="__main__":raise SystemExit(main())
