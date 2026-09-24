#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any
import agent_fleet_observatory as afo
import agent_benchmark_harness as abh
import agent_benchmark_campaign_runner as abcr
import technology_watch_runtime as tw
import agent_evolution_profile as aep
import component_evolution_governance as ceg
import platform_component_evolution_controller as pcec
import agent_verified_evidence_backfill as aveb
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
def collect_reassessment_requests(runtime:Path):
    agent_requests=[];platform_requests=[];platform_actions=[];blocked=[]
    aq=runtime/"agent-evolution/reassessment-queue"
    if aq.is_dir():
        for p in sorted(aq.glob("*.json")):
            x=safe(p)
            if x.get("schema")=="chacha.dev/agent-reassessment-request/v1":
                agent_requests.append(x)
    pq=runtime/"platform-evolution/reassessment-queue"
    if pq.is_dir():
        for p in sorted(pq.glob("*.json")):
            x=safe(p)
            if x.get("schema")!="chacha.dev/platform-component-reassessment-request/v1":
                continue
            platform_requests.append(x)
            owner=str(x.get("candidate_owner") or "")
            if owner=="capability-foundry":action="CAPABILITY_FOUNDRY_REASSESSMENT"
            elif owner=="branch-foundry":action="BRANCH_FOUNDRY_REASSESSMENT"
            else:
                blocked.append({"request_id":x.get("request_id"),"component_id":x.get("component_id"),
                    "candidate_owner":owner,"blocker":"UNSUPPORTED_PLATFORM_EVOLUTION_OWNER"})
                continue
            platform_actions.append({
                "request_id":x.get("request_id"),"component_id":x.get("component_id"),
                "action":action,"candidate_owner":owner,
                "trigger_reasons":list(x.get("trigger_reasons") or []),
                "technology_watch_revalidation_required":True,
                "logician_falsification_required":True,
                "shadow_required":bool(x.get("shadow_required") is True),
                "pilot_required":bool(x.get("pilot_required") is True),
                "direct_component_mutation":False,"self_promotion":False,
                "architecture_council_final_authority":True,
                "automatic_external_spend_eur":0})
    return agent_requests,platform_requests,platform_actions,blocked
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--runtime-root",type=Path,default=Path("/opt/chacha-dev/runtime"));a=ap.parse_args()
    root=a.repo_root.resolve();runtime=a.runtime_root.resolve();cfg=root/"dev-hub/config";ae=runtime/"agent-evolution";ae.mkdir(parents=True,exist_ok=True)
    routing=load(cfg/"agent-routing.v1.json");seven=load(cfg/"seven-agent-final-compromise.v1.json");project=load(root/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
    fp=load(cfg/"agent-fleet-observatory.v1.json");ep=load(cfg/"agent-evolution.v1.json")
    backfill=aveb.run(runtime,fp,load(cfg/"agent-observation-bus.v1.json"),routing,seven,[project],False)
    save(ae/"verified-evidence-backfill-latest.json",backfill)
    report=afo.build_report(root,runtime,fp,ep,routing,seven,[project]);save(ae/"fleet-observatory-latest.json",report)
    requests,platform_requests,platform_actions,platform_blocked=collect_reassessment_requests(runtime)
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
    platform_idx={"schema":"chacha.dev/platform-evolution-reassessment-index/v1","generated_at":iso(stamp),
      "event_requests":platform_requests,"routed_actions":platform_actions,"blocked_requests":platform_blocked,
      "event_request_count":len(platform_requests),"routed_action_count":len(platform_actions),
      "blocked_request_count":len(platform_blocked),
      "routing_complete":len(platform_requests)==len(platform_actions) and not platform_blocked,
      "direct_component_mutation":False,"self_promotion":False,
      "technology_watch_revalidation_required":True,"logician_falsification_required":True,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
    pe=runtime/"platform-evolution";pe.mkdir(parents=True,exist_ok=True)
    save(pe/"reassessment-index-latest.json",platform_idx)
    benchmark_campaign=None
    if scheduled:
        bp=load(cfg/"agent-benchmark-harness.v1.json")
        benchmark_campaign=abh.campaign(idx,report,bp,tw.snapshot_status(root))
        camp_root=ae/"benchmark-campaigns";camp_root.mkdir(parents=True,exist_ok=True)
        stamp_id=stamp.strftime("%Y%m%dT%H%M%SZ")
        campaign_path=camp_root/(stamp_id+".json");save(campaign_path,benchmark_campaign)
        save(ae/"benchmark-campaign-latest.json",benchmark_campaign)
        adapter_cfg=load(cfg/"agent-benchmark-adapters.v1.json")
        revision=(root/".revision").read_text(encoding="utf-8").strip() if (root/".revision").is_file() else "UNKNOWN"
        benchmark_run=abcr.execute(benchmark_campaign,root,runtime,revision,adapter_cfg)
        save(ae/"benchmark-run-latest.json",benchmark_run)
        # Rebuild Fleet Observatory immediately so newly promoted benchmark evidence can fill UNKNOWN dimensions.
        report=afo.build_report(root,runtime,fp,ep,routing,seven,[project]);save(ae/"fleet-observatory-latest.json",report)
    profile_policy=load(cfg/"agent-evolution-profile.v1.json")
    adapter_cfg=load(cfg/"agent-benchmark-adapters.v1.json")
    profile_index=aep.build_index(report,routing,seven,[project],adapter_cfg,ep,profile_policy)
    aep.write_profiles(ae/"profiles",profile_index)
    universal_policy=load(cfg/"universal-evolution-governance.v1.json")
    component_index=ceg.build_index(profile_index,load(cfg/"technology-core-watch.v1.json"),
      load(cfg/"provider-adapters.v1.json"),load(cfg/"mcp-provider-catalog.v1.json"),
      load(cfg/"project-embedded-assurance.v1.json"),universal_policy,
      load(cfg/"guardian-coverage-manifest.v1.json"))
    save(ae/"component-governance-latest.json",component_index)
    platform_dispatch=pcec.build_dispatch(platform_idx,component_index)
    save(pe/"foundry-dispatch-latest.json",platform_dispatch)
    receipt={"schema":"chacha.dev/agent-evolution-daily-cycle/v1","generated_at":iso(stamp),"agent_count":report.get("agent_count"),
      "optimization_count":len(report.get("optimization_queue") or []),"measurement_count":len(report.get("measurement_queue") or []),
      "event_request_count":len(requests),"scheduled_action_count":len(scheduled),
      "platform_event_request_count":len(platform_requests),"platform_routed_action_count":len(platform_actions),
      "platform_blocked_request_count":len(platform_blocked),
      "platform_reassessment_routing_complete":platform_idx["routing_complete"],
      "platform_foundry_dispatch_count":platform_dispatch.get("dispatch_count"),
      "platform_foundry_dispatch_blocked_count":platform_dispatch.get("blocked_count"),
      "platform_foundry_dispatch_complete":platform_dispatch.get("dispatch_complete"),
      "deep_audit_due":deep,"ecosystem_benchmark_due":bench,
      "benchmark_campaign_created":benchmark_campaign is not None,
      "benchmark_contract_count":len((benchmark_campaign or {}).get("contracts") or []),
      "benchmark_run_promoted_count":int((locals().get("benchmark_run") or {}).get("promoted_count") or 0),
      "verified_evidence_backfill_eligible":int(backfill.get("eligible_event_count") or 0),
      "verified_evidence_backfill_inserted":int((backfill.get("counts") or {}).get("inserted") or 0),
      "verified_evidence_backfill_retroactive_reassessment":False,
      "universal_profile_count":profile_index.get("profile_count"),"universal_profiles_generated":True,
      "universal_component_governance_count":component_index.get("component_count"),
      "single_evolution_owner_per_component":component_index.get("single_evolution_owner_per_component"),
      "no_parallel_governance_engines":component_index.get("no_parallel_governance_engines"),
      "guardian_component_governance_count":component_index.get("guardian_component_count"),
      "guardian_evolution_coverage_sync_complete":component_index.get("guardian_evolution_coverage_sync_complete"),
      "guardian_uncovered_components":component_index.get("guardian_uncovered_components") or [],
      "technology_watch":tw.snapshot_status(root),"direct_agent_mutation":False,"self_promotion":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0}
    save(ae/"daily-cycle-latest.json",receipt)
    print("CHACHA_DEV_V648_AGENT_EVOLUTION_DAILY_CYCLE=PASS");print("AGENT_COUNT="+str(receipt["agent_count"]))
    print("EVENT_REQUESTS="+str(len(requests)));print("SCHEDULED_ACTIONS="+str(len(scheduled)))
    print("PLATFORM_EVENT_REQUESTS="+str(len(platform_requests)));print("PLATFORM_ROUTED_ACTIONS="+str(len(platform_actions)))
    print("PLATFORM_REASSESSMENT_ROUTING="+("PASS" if platform_idx["routing_complete"] else "BLOCKED"))
    print("PLATFORM_FOUNDRY_DISPATCH="+("PASS" if platform_dispatch["dispatch_complete"] else "BLOCKED"))
    print("CHACHA_DEV_V648_AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0
if __name__=="__main__":raise SystemExit(main())
