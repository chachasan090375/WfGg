#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import technology_watch_runtime as tw

SCHEMA="chacha.dev/acceptance-candidate-promotion-readiness/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def now_iso()->str:return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def sha256(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def github_runs(repository:str,revision:str)->dict[str,Any]:
    q=urllib.parse.urlencode({"head_sha":revision,"per_page":50})
    url=f"https://api.github.com/repos/{repository}/actions/runs?{q}"
    req=urllib.request.Request(url,headers={"User-Agent":"ChaCha-DEV-V663-Readiness/1.0","Accept":"application/vnd.github+json"})
    with urllib.request.urlopen(req,timeout=20) as r:
        x=json.loads(r.read().decode("utf-8"))
    if not isinstance(x,dict):raise ValueError("GITHUB_RUNS_INVALID")
    return x
def successful_workflow(runs:dict[str,Any],name:str,revision:str)->bool:
    return any(
      isinstance(x,dict) and x.get("name")==name and x.get("head_sha")==revision and
      x.get("status")=="completed" and x.get("conclusion")=="success"
      for x in (runs.get("workflow_runs") or [])
    )

def latest_pilot(runtime:Path)->Path|None:
    roots=[
      runtime/"agent-evolution/candidate-qualifications/acceptance-engineer",
      runtime/"agent-evolution/candidate-pilots/acceptance-engineer/v662"
    ]
    rows=[]
    for root in roots:
        if root.is_dir():
            rows += list(root.glob("**/independent-pilot.json"))
            rows += list(root.glob("**/pilot-receipt.json"))
    return sorted(set(rows),key=lambda p:p.stat().st_mtime)[-1] if rows else None

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--runtime-root",type=Path,required=True)
    ap.add_argument("--revision",required=True);ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--github-runs-json",type=Path);ap.add_argument("--technology-watch-status",type=Path)
    ap.add_argument("--guardian-coverage",type=Path);a=ap.parse_args()
    repo=a.repo_root.resolve();runtime=a.runtime_root.resolve();rev=str(a.revision)
    manifest_path=repo/"dev-hub/candidates/acceptance-engineer/v661/candidate-manifest.json"
    incumbent=repo/"dev-hub/bin/acceptance-engine.py"
    fleet_path=runtime/"agent-evolution/fleet-observatory-latest.json"
    guardian_path=a.guardian_coverage if a.guardian_coverage is not None else runtime/"guardian/coverage-latest.json"
    pilot_path=latest_pilot(runtime)
    if not all(p and Path(p).is_file() for p in (manifest_path,incumbent,fleet_path,guardian_path,pilot_path)):
        raise SystemExit("V663_READINESS_INPUT_MISSING")
    manifest=load(manifest_path);pilot=load(Path(pilot_path));fleet=load(fleet_path);guardian=load(guardian_path)
    watch=load(a.technology_watch_status) if a.technology_watch_status is not None else tw.snapshot_status(repo)
    runs=load(a.github_runs_json) if a.github_runs_json else github_runs("chachasan090375/WfGg",rev)
    acc=next((x for x in (fleet.get("agents") or []) if x.get("agent_id")=="acceptance-engineer"),None)
    if not acc:raise SystemExit("ACCEPTANCE_ENGINEER_FLEET_ROW_MISSING")
    cand=(acc.get("plan") or {}).get("candidate") or {}
    pilot_ok=(
      str(pilot.get("candidate_id") or "")==str(manifest.get("candidate_id") or "") and
      int(pilot.get("real_candidate_passed") or pilot.get("real_passed_count") or 0)>=3 and
      int(pilot.get("real_case_count") or 0)>=3 and
      int(pilot.get("adversarial_candidate_passed") or pilot.get("adversarial_passed_count") or 0)>=3 and
      (pilot.get("measurable_gain") is True or pilot.get("measurable_gain_verified") is True)
    )
    incumbent_digest=str(pilot.get("incumbent_digest") or "")
    incumbent_unchanged=bool(incumbent_digest) and sha256(incumbent)==incumbent_digest
    guardian_ok=guardian.get("all_hooks_active") is True
    watch_ok=watch.get("fresh") is True and watch.get("state")=="FRESH"
    logician_ok=pilot.get("logician_falsification_required") is True or pilot.get("logician_falsification_paths_verified") is True
    sentinel_required=pilot.get("sentinel_required") is True or pilot.get("sentinel_required_for_release") is True
    sentinel_ok=successful_workflow(runs,"ChaCha DEV Sentinel technical assurance",rev)
    qualification_ok=successful_workflow(runs,"ChaCha DEV V6.63 runtime surface instrumentation and Acceptance readiness qualification",rev)
    candidate_governance_ok=(
      manifest.get("owner")=="agent-foundry" and manifest.get("isolated") is True and
      manifest.get("incumbent_control_group") is True and manifest.get("production_activation_allowed") is False and
      manifest.get("active_self_mutation") is False and manifest.get("self_promotion") is False and
      manifest.get("permission_expansion") is False and manifest.get("architecture_council_final_authority") is True and
      cand.get("owner")=="agent-foundry" and cand.get("isolated") is True and cand.get("incumbent_control_group") is True
    )
    evidence_complete=all((pilot_ok,incumbent_unchanged,guardian_ok,watch_ok,logician_ok,sentinel_required,sentinel_ok,qualification_ok,candidate_governance_ok))
    result={
      "schema":SCHEMA,"generated_at":now_iso(),"revision":rev,
      "candidate_id":manifest.get("candidate_id"),"owner":"agent-foundry",
      "pilot_source":str(pilot_path),"pilot_evidence_complete":pilot_ok,
      "measurable_gain_verified":bool(pilot.get("measurable_gain") is True or pilot.get("measurable_gain_verified") is True),
      "incumbent_digest_matches_pilot":incumbent_unchanged,
      "guardian_all_hooks_active":guardian_ok,"technology_watch_fresh":watch_ok,
      "logician_falsification_satisfied":logician_ok,
      "sentinel_required":sentinel_required,"sentinel_exact_revision_success":sentinel_ok,
      "v663_exact_revision_qualification_success":qualification_ok,
      "candidate_governance_valid":candidate_governance_ok,
      "evidence_complete_for_review":evidence_complete,
      "architecture_council_approval_present":False,
      "human_explicit_promotion_approval_present":False,
      "decision":"READY_FOR_ARCHITECTURE_COUNCIL_REVIEW_HOLD_INCUMBENT" if evidence_complete else "NOT_READY_HOLD_INCUMBENT",
      "production_entrypoint_changed":False,"production_activation_allowed":False,"promotion_allowed":False,
      "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
      "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0
    }
    save(a.output,result)
    print("CHACHA_DEV_V663_ACCEPTANCE_READINESS="+("PASS" if evidence_complete else "BLOCK"))
    print("CHACHA_DEV_V663_ACCEPTANCE_DECISION="+result["decision"])
    print("CHACHA_DEV_V663_ARCHITECTURE_COUNCIL_APPROVAL_PRESENT=NO")
    print("CHACHA_DEV_V663_HUMAN_PROMOTION_APPROVAL_PRESENT=NO")
    print("CHACHA_DEV_V663_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
    print("CHACHA_DEV_V663_ACCEPTANCE_PROMOTION=NO")
    print("CHACHA_DEV_V663_INCUMBENT_CONTROL_GROUP=YES")
    print("CHACHA_DEV_V663_SELF_MUTATION=NO")
    print("CHACHA_DEV_V663_SELF_PROMOTION=NO")
    print("CHACHA_DEV_V663_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
    print("CHACHA_DEV_V663_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if evidence_complete else 20
if __name__=="__main__":raise SystemExit(main())
