#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import agent_evolution_logician as ael
import technology_watch_runtime as tw

SCHEMA="chacha.dev/agent-foundry-independent-pilot/v1"
VERIFIER="v662-acceptance-independent-pilot"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def now_iso()->str:return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def sha_ref(p:Path)->str:return str(p)+"#sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def run_engine(script:Path,contract:Path,evidence:Path,out:Path)->dict[str,Any]:
    p=subprocess.run([sys.executable,str(script),"--contract",str(contract),"--evidence",str(evidence),"--output",str(out)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if p.returncode!=0:raise RuntimeError("ENGINE_FAILED:"+str(script)+":"+p.stderr[-1000:]+p.stdout[-1000:])
    return load(out)
def core(x:dict[str,Any])->dict[str,Any]:
    keys=("schema","accepted","criteria","return_to_factories","delivery_allowed","local_acceptance_candidate",
          "final_delivery_allowed","final_delivery_gate","final_delivery_receipt_required")
    return {k:x.get(k) for k in keys}
def guardian_ok(runtime_root:Path,override:Path|None=None)->bool:
    p=override if override is not None else runtime_root/"guardian/coverage-latest.json"
    if not p.is_file():return False
    x=load(p);return x.get("all_hooks_active") is True

def real_cases(runtime_root:Path,incumbent:Path,candidate:Path,work:Path)->tuple[list[dict[str,Any]],bool]:
    rows=[];ok=True;root=runtime_root/"golden-path-runs"
    for run in sorted(root.iterdir() if root.is_dir() else []):
        contract=run/"planning/functional-contract.json";evidence=run/"external-assurance/acceptance-evidence.json";observed=run/"external-assurance/acceptance.json"
        if not all(p.is_file() for p in (contract,evidence,observed)):continue
        inc=run_engine(incumbent,contract,evidence,work/(run.name+"-inc.json"))
        cand=run_engine(candidate,contract,evidence,work/(run.name+"-cand.json"))
        obs=load(observed);match=core(inc)==core(cand)==core(obs);ok=ok and match
        rows.append({"run_id":run.name,"passed":match,"incumbent_accepted":inc.get("accepted"),"candidate_accepted":cand.get("accepted")})
    return rows,ok

def adversarial(repo_root:Path,incumbent:Path,candidate:Path,work:Path)->list[dict[str,Any]]:
    cases=[]
    def one(name,artifact_exists=True,tamper=False,malformed=False):
        d=work/name;d.mkdir()
        artifact=d/"artifact.json"
        if artifact_exists:artifact.write_text('{"status":"PASS"}\n',encoding="utf-8")
        ref=sha_ref(artifact) if artifact_exists else str(artifact)+"#sha256:"+"a"*64
        if tamper:artifact.write_text('{"status":"TAMPERED"}\n',encoding="utf-8")
        if malformed:ref=str(artifact)+"#sha256:not-a-digest"
        contract=d/"contract.json";evidence=d/"evidence.json"
        save(contract,{"schema":"chacha.dev/functional-contract/v1","criteria":[{"criterion_id":"required","dimension":"functional","required":True,"owner":"product"}]})
        save(evidence,{"criteria":[{"criterion_id":"required","state":"PASS","evidence":ref}]})
        inc=run_engine(incumbent,contract,evidence,d/"inc.json");cand=run_engine(candidate,contract,evidence,d/"cand.json")
        expected_candidate=(name=="valid")
        passed=(inc.get("accepted") is True and cand.get("accepted") is expected_candidate)
        cases.append({"case_id":name,"passed":passed,"incumbent_accepted":inc.get("accepted"),"candidate_accepted":cand.get("accepted")})
    one("valid");one("tampered",tamper=True);one("missing",artifact_exists=False);one("malformed",malformed=True)
    return cases

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,required=True);ap.add_argument("--runtime-root",type=Path,required=True);ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--technology-watch-status",type=Path);ap.add_argument("--guardian-coverage",type=Path);a=ap.parse_args()
    repo=a.repo_root.resolve();runtime=a.runtime_root.resolve()
    incumbent=repo/"dev-hub/bin/acceptance-engine.py"
    candidate=repo/"dev-hub/candidates/acceptance-engineer/v661/acceptance-engine-candidate.py"
    manifest=load(repo/"dev-hub/candidates/acceptance-engineer/v661/candidate-manifest.json")
    fleet=load(runtime/"agent-evolution/fleet-observatory-latest.json")
    acc=next(x for x in fleet.get("agents") or [] if x.get("agent_id")=="acceptance-engineer")
    sc=acc.get("scorecard") or {};pl=acc.get("plan") or {}
    challenge=ael.build("acceptance-engineer",sc)
    routes={x.get("route") for x in challenge.get("falsification_paths") or []}
    logician_ok={"ADVERSARIAL_COUNTEREXAMPLES","INDEPENDENT_ORACLE_CHECK","PERMISSION_BOUNDARY_PROBE","INCUMBENT_VS_CANDIDATE_SHADOW_COMPARISON"}<=routes
    watch=load(a.technology_watch_status) if a.technology_watch_status is not None else tw.snapshot_status(repo)
    watch_ok=watch.get("fresh") is True and watch.get("state")=="FRESH"
    guard=guardian_ok(runtime,a.guardian_coverage)
    governance_ok=(
      manifest.get("owner")=="agent-foundry" and manifest.get("isolated") is True and
      manifest.get("incumbent_control_group") is True and manifest.get("production_activation_allowed") is False and
      manifest.get("active_self_mutation") is False and manifest.get("self_promotion") is False and
      manifest.get("permission_expansion") is False and manifest.get("guardian_required") is True and
      manifest.get("sentinel_required") is True and manifest.get("logician_falsification_required") is True and
      manifest.get("technology_watch_revalidation_required") is True and
      manifest.get("architecture_council_final_authority") is True and float(manifest.get("automatic_external_spend_eur") or 0)==0 and
      (pl.get("candidate") or {}).get("owner")=="agent-foundry" and (pl.get("candidate") or {}).get("isolated") is True and
      (pl.get("candidate") or {}).get("incumbent_control_group") is True
    )
    with tempfile.TemporaryDirectory(prefix="v662-independent-pilot-") as td:
        work=Path(td)
        real,real_ok=real_cases(runtime,incumbent,candidate,work)
        adv=adversarial(repo,incumbent,candidate,work)
    adv_ok=bool(adv) and all(x["passed"] for x in adv)
    passed=bool(real and real_ok and adv_ok and logician_ok and watch_ok and guard and governance_ok)
    out={
      "schema":SCHEMA,"pilot_id":"acceptance-engineer:v662:independent-evidence-digest-pilot",
      "candidate_id":manifest.get("candidate_id"),"subject_agent":"acceptance-engineer",
      "verifier":VERIFIER,"verification":"INDEPENDENT_PILOT_VERIFIED","generated_at":now_iso(),
      "real_case_count":len(real),"real_passed_count":sum(1 for x in real if x["passed"]),"real_no_regression":real_ok,
      "adversarial_case_count":len(adv),"adversarial_passed_count":sum(1 for x in adv if x["passed"]),
      "adversarial_gain_verified":adv_ok,
      "logician_falsification_paths_verified":logician_ok,"logician_decision_authority":False,
      "technology_watch_state":watch.get("state"),"technology_watch_fresh":watch_ok,
      "guardian_all_hooks_active":guard,"sentinel_required_for_release":True,
      "governance_contract_valid":governance_ok,
      "decision":"INDEPENDENT_PILOT_PASS_HOLD_INCUMBENT" if passed else "BLOCK_CANDIDATE",
      "isolated":True,"incumbent_control_group":True,"production_entrypoint_changed":False,
      "production_activation_allowed":False,"promotion_allowed":False,
      "measurable_gain_verified":adv_ok and real_ok,
      "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
      "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0,
      "real_cases":real,"adversarial_cases":adv,"logician_challenge":challenge
    }
    save(a.output,out)
    print("CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT="+("PASS" if passed else "BLOCK"))
    print("CHACHA_DEV_V662_ACCEPTANCE_REAL_NO_REGRESSION="+("PASS" if real_ok and real else "BLOCK"))
    print("CHACHA_DEV_V662_ACCEPTANCE_ADVERSARIAL_GAIN="+("PASS" if adv_ok else "BLOCK"))
    print("CHACHA_DEV_V662_LOGICIAN_FALSIFICATION="+("PASS" if logician_ok else "BLOCK"))
    print("CHACHA_DEV_V662_TECHNOLOGY_WATCH="+("FRESH" if watch_ok else "BLOCK"))
    print("CHACHA_DEV_V662_GUARDIAN_ACTIVE="+("YES" if guard else "NO"))
    print("CHACHA_DEV_V662_SENTINEL_REQUIRED=YES")
    print("CHACHA_DEV_V662_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
    print("CHACHA_DEV_V662_ACCEPTANCE_PROMOTION=NO")
    print("CHACHA_DEV_V662_INCUMBENT_CONTROL_GROUP=YES")
    print("CHACHA_DEV_V662_SELF_MUTATION=NO")
    print("CHACHA_DEV_V662_SELF_PROMOTION=NO")
    print("CHACHA_DEV_V662_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
    print("CHACHA_DEV_V662_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if passed else 20
if __name__=="__main__":raise SystemExit(main())
