#!/usr/bin/env python3
from __future__ import annotations
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import technology_truth_scoring as tts
import technology_watch_logician as twl
import technology_source_reputation as tsr
import technology_core_watch as tcw
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
POL=load(CFG/"technology-truth-scoring.v1.json");REP=load(CFG/"technology-source-reputation.v1.json");LOG=load(CFG/"technology-watch-logician.v1.json");CORE=load(CFG/"technology-core-watch.v1.json")
def base(version="1.8.4",release="2026-06-01"):
    return {"schema":"chacha.dev/technology-candidate-dossier/v1","technology_id":"example-runtime","publisher":"ExampleVendor","version":version,
      "release_date":release,"as_of":"2026-09-24T00:00:00Z","blast_radius":"medium",
      "claims":[{"id":"claim-core","class":"runtime","required":True}],
      "evidence":[
        {"id":"vendor-doc","claim_id":"claim-core","type":"official_technical","origin":"vendor-docs","origin_kind":"publisher","independence_group":"vendor","verified":True,"stance":"SUPPORT"},
        {"id":"independent","claim_id":"claim-core","type":"independent_technical","origin":"engineering-blog","independence_group":"independent-a","verified":True,"stance":"SUPPORT"},
        {"id":"exec","claim_id":"claim-core","type":"executable_reproduction","origin":"chacha-lab","independence_group":"chacha-exec","verified":True,"reproducible":True,"stance":"SUPPORT"},
        {"id":"pilot","claim_id":"claim-core","type":"project_pilot","origin":"chacha-pilot","independence_group":"chacha-pilot","verified":True,"reproducible":True,"stance":"SUPPORT"}],
      "operational":{"maintenance_health":95,"security_health":95,"unresolved_critical_issues":0,"unresolved_high_impact_issues":0,"unresolved_medium_issues":0,"regression_rate_pct":1,"rollback_tested":True,"shadow_passed":True,"pilot_passed":True},
      "architecture_fit":{"compatibility":92,"security_fit":92,"resource_efficiency":88,"observability":90,"rollback_readiness":95,"integration_fit":91,"cost_fit":100,"migration_safety":90},
      "outcomes":[]}
marketing=base();marketing["evidence"]=[{"id":"press","claim_id":"claim-core","type":"marketing","origin":"vendor-marketing","origin_kind":"publisher","independence_group":"vendor","verified":True,"stance":"SUPPORT"}]
m=tts.evaluate(marketing,POL,REP,{})
assert m["marketing_only"] is True and m["recommendation_class"] in {"WATCH","REJECT"} and m["automatic_selection_allowed"] is False,m
one=base();one["evidence"]=[{"id":"a","claim_id":"claim-core","type":"independent_technical","origin":"blog-a","independence_group":"same-upstream","verified":True,"stance":"SUPPORT"}]
dup=copy.deepcopy(one);dup["evidence"].append({"id":"b","claim_id":"claim-core","type":"independent_technical","origin":"blog-b-repost","independence_group":"same-upstream","verified":True,"stance":"SUPPORT"})
r1=tts.evaluate(one,POL,REP,{});r2=tts.evaluate(dup,POL,REP,{})
assert r1["technical_truth_score"]==r2["technical_truth_score"] and r2["evidence_graph"]["duplicate_or_shared_origin_evidence_count"]>=1,(r1,r2)
noexec=base();noexec["evidence"]=[x for x in noexec["evidence"] if x["type"] not in {"executable_reproduction","project_pilot"}]
ne=tts.evaluate(noexec,POL,REP,{});we=tts.evaluate(base(),POL,REP,{})
assert we["technical_truth_score"]>ne["technical_truth_score"] and we["executable_or_real_pilot_proof"] is True,(ne,we)
conf=base();conf["evidence"].append({"id":"counter","claim_id":"claim-core","type":"independent_technical","origin":"failure-lab","independence_group":"independent-negative","verified":True,"stance":"CONTRADICT"})
cr=tts.evaluate(conf,POL,REP,{})
assert cr["contradictory_evidence"] is True and cr["additional_verification_required"] is True and "CONTRADICTORY_EVIDENCE" in cr["blocking_reasons"],cr
old=base("1.8.4","2026-06-01");new=base("2.0.0","2026-09-23");new["operational"].update({"rollback_tested":False,"shadow_passed":False,"pilot_passed":False})
orpt=tts.evaluate(old,POL,REP,{});nrpt=tts.evaluate(new,POL,REP,{})
assert orpt["recommendation_class"]=="ADOPT",orpt
assert nrpt["operational_maturity_score"]<orpt["operational_maturity_score"],(orpt,nrpt)
selected=tts.select_verified_safe([nrpt,orpt]);assert selected["selected"]["version"]=="1.8.4" and selected["selection_principle"]=="BEST_VERIFIED_SAFE_NOT_NEWEST",selected
bad=base();bad["outcomes"]=[{"status":"VERIFIED_FAILURE","verified":True,"severity":"high"}];br=tts.evaluate(bad,POL,REP,{})
assert br["technical_truth_score"]<orpt["technical_truth_score"] and br["operational_maturity_score"]<orpt["operational_maturity_score"],(br,orpt)
initial=tsr.profile_confidence(REP,"ExampleVendor");evt={"publisher":"ExampleVendor","outcome":"CONTRADICTED","claim_class":"runtime","evidence_ref":"evidence:1"}
rep1=tsr.apply_event(REP,evt);rep2=tsr.apply_event(rep1,{**evt,"evidence_ref":"evidence:2"});lower=tsr.profile_confidence(rep2,"ExampleVendor")
assert lower<initial and rep2["publishers"]["ExampleVendor"]["confidence"]==lower,(initial,lower)
challenge=twl.build_challenge(marketing,LOG);routes={x["route"] for x in challenge["falsification_paths"]}
assert "EXECUTABLE_REPRODUCTION" in routes and "NEGATIVE_ISSUE_SEARCH" in routes and challenge["decision_authority"]=="technology-watch-agent" and challenge["direct_mutation"] is False,challenge
high=base();high["blast_radius"]="critical";hc=twl.build_challenge(high,LOG);hroutes={x["route"] for x in hc["falsification_paths"]}
assert {"ROLLBACK_DRILL","SHADOW_COMPARISON","DEPENDENCY_COMPATIBILITY_MATRIX"}.issubset(hroutes),hc
required={"central-brain","central-orchestrator","architecture-council","logician","ergonomist","agent-foundry","branch-foundry","capability-foundry","guardian","sentinel","bastion","intendant","project-control","verification-broker","run-controller","learning-fabric","central-memory","mcp-connectors","provider-adapters","vps-runtime","nas-runtime","cloudflare-runtime","python-runtime","node-runtime"}
ids={x["id"] for x in CORE["components"]};assert required.issubset(ids),(required-ids)
core=tcw.build_core_watch(CORE,{"components":{"node-runtime":{"eol_days":20,"maintenance_health":35},"guardian":{"critical_security_advisory":True}}})
assert core["inventory_coverage_complete"] is True and core["recommendations_only"] is True and core["uncontrolled_upgrade"] is False,core
assert max(x["technology_debt_score"] for x in core["components"])>=50,core
for report in (m,r2,we,cr,orpt,nrpt,br):
    assert report["automatic_external_spend_eur"]==0 and report["permission_escalation"] is False and report["architecture_council_final_authority"] is True and report["guardian_authority_preserved"] is True and report["sentinel_authority_preserved"] is True,report
print("CHACHA_DEV_V645_MARKETING_ONLY_ADOPTION=BLOCKED")
print("CHACHA_DEV_V645_SOURCE_DUPLICATION_INFLATION=NO")
print("CHACHA_DEV_V645_EXECUTABLE_PROOF_RAISES_TRUTH=PASS")
print("CHACHA_DEV_V645_CONTRADICTORY_EVIDENCE_REQUIRES_VERIFICATION=PASS")
print("CHACHA_DEV_V645_MATURITY_INDEPENDENT_FROM_TRUTH=PASS")
print("CHACHA_DEV_V645_NEWEST_VERSION_PRIORITY=NO")
print("CHACHA_DEV_V645_OLDER_VERIFIED_SAFE_SELECTION=PASS")
print("CHACHA_DEV_V645_REAL_OUTCOME_FEEDBACK=PASS")
print("CHACHA_DEV_V645_PUBLISHER_CONFIDENCE_CALIBRATION=PASS")
print("CHACHA_DEV_V645_LOGICIAN_FALSIFICATION=PASS")
print("CHACHA_DEV_V645_LOGICIAN_DECISION_AUTHORITY=NO")
print("CHACHA_DEV_V645_CORE_ARCHITECTURE_WATCH=PASS")
print("CHACHA_DEV_V645_TECHNOLOGY_DEBT_RADAR=PASS")
print("CHACHA_DEV_V645_PERMISSION_ESCALATION=NO")
print("CHACHA_DEV_V645_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V645_AUTOMATIC_EXTERNAL_SPEND_EUR=0")

# A time-fresh V6.44-style snapshot is not semantically fresh for V6.45.
import os,tempfile,time
import technology_watch_runtime as tw
with tempfile.TemporaryDirectory(prefix="v645-snapshot-contract-") as td:
    p=Path(td)/"legacy-fresh.json"
    legacy={"schema":"chacha.dev/technology-watch-snapshot/v1",
            "generated_at":"2026-09-24T00:00:00Z",
            "snapshot_digest":"legacy-v644"}
    p.write_text(json.dumps(legacy),encoding="utf-8")
    old_env=os.environ.get("CHACHA_TECHNOLOGY_WATCH_SNAPSHOT")
    os.environ["CHACHA_TECHNOLOGY_WATCH_SNAPSHOT"]=str(p)
    try:
        status=tw.snapshot_status(ROOT)
        assert status["state"]=="INCOMPATIBLE" and status["fresh"] is False,status
        assert set(status["missing_required_sections"])=={"technology_truth_assurance","core_architecture_watch"},status
    finally:
        if old_env is None: os.environ.pop("CHACHA_TECHNOLOGY_WATCH_SNAPSHOT",None)
        else: os.environ["CHACHA_TECHNOLOGY_WATCH_SNAPSHOT"]=old_env
print("CHACHA_DEV_V645_LEGACY_FRESH_SNAPSHOT_COMPATIBILITY=BLOCKED")


# Real-PILOT regression: a recent V6.44 snapshot can be time-fresh but contract-incompatible.
import os,tempfile
from datetime import datetime,timezone
import technology_watch_runtime as tw
with tempfile.TemporaryDirectory(prefix="v645-incompatible-snapshot-") as td:
    legacy=Path(td)/"optimizer-input.json"
    legacy.write_text(json.dumps({
      "schema":"chacha.dev/technology-watch-snapshot/v1",
      "generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
      "snapshot_digest":"v644-time-fresh-but-legacy",
      "provider_candidates":[]
    }),encoding="utf-8")
    old_env=os.environ.get("CHACHA_TECHNOLOGY_WATCH_SNAPSHOT")
    os.environ["CHACHA_TECHNOLOGY_WATCH_SNAPSHOT"]=str(legacy)
    try:
        status=tw.snapshot_status(ROOT)
        assert status["state"]=="INCOMPATIBLE" and status["fresh"] is False,status
        assert set(status["missing_required_sections"])=={"technology_truth_assurance","core_architecture_watch"},status
        feed=tw.consult(ROOT,consumer="architecture-decision-council",domain="platform-release",capabilities=[])
        assert feed["targeted_refresh_performed"] is True,feed
        assert (feed.get("technology_truth_assurance") or {}).get("required_for_new_or_version_changed_candidate") is True,feed
        assert (feed.get("technology_truth_assurance") or {}).get("marketing_only_adoption_forbidden") is True,feed
        assert (feed.get("core_architecture_watch") or {}).get("technology_debt_radar") is True,feed
        assert json.loads(legacy.read_text(encoding="utf-8"))["snapshot_digest"]=="v644-time-fresh-but-legacy"
    finally:
        if old_env is None:os.environ.pop("CHACHA_TECHNOLOGY_WATCH_SNAPSHOT",None)
        else:os.environ["CHACHA_TECHNOLOGY_WATCH_SNAPSHOT"]=old_env
print("CHACHA_DEV_V645_INCOMPATIBLE_SNAPSHOT_TARGETED_REFRESH=PASS")
print("CHACHA_DEV_V645_INCOMPATIBLE_REFRESH_CANONICAL_MUTATION=NO")
