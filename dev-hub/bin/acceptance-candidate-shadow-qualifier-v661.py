#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/agent-foundry-isolated-candidate-qualification/v1"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def sha(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def run_engine(script:Path,contract:Path,evidence:Path,output:Path)->dict[str,Any]:
    p=subprocess.run([sys.executable,str(script),"--contract",str(contract),"--evidence",str(evidence),"--output",str(output)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if p.returncode!=0:
        raise RuntimeError("ENGINE_FAILED:"+str(script)+":"+p.stderr[-1200:]+p.stdout[-1200:])
    return load(output)

def core(x:dict[str,Any])->dict[str,Any]:
    keys=("schema","accepted","criteria","return_to_factories","delivery_allowed","local_acceptance_candidate",
          "final_delivery_allowed","final_delivery_gate","final_delivery_receipt_required")
    return {k:x.get(k) for k in keys}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--runtime-root",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();repo=a.repo_root.resolve();runtime=a.runtime_root.resolve()
    incumbent=repo/"dev-hub/bin/acceptance-engine.py"
    candidate=repo/"dev-hub/candidates/acceptance-engineer/v661/acceptance-engine-candidate.py"
    manifest_path=repo/"dev-hub/candidates/acceptance-engineer/v661/candidate-manifest.json"
    fleet_path=runtime/"agent-evolution/fleet-observatory-latest.json"
    if not all(p.is_file() for p in (incumbent,candidate,manifest_path,fleet_path)):
        raise SystemExit("V661_CANDIDATE_INPUT_MISSING")
    manifest=load(manifest_path);fleet=load(fleet_path)
    row=next((x for x in (fleet.get("agents") or []) if x.get("agent_id")=="acceptance-engineer"),None)
    if not row:raise SystemExit("ACCEPTANCE_ENGINEER_PROFILE_MISSING")
    plan=row.get("plan") or {};candplan=plan.get("candidate") or {};evidence_maturity=plan.get("evidence_maturity") or {}
    governance_ok=(
      manifest.get("owner")=="agent-foundry" and manifest.get("isolated") is True and
      manifest.get("incumbent_control_group") is True and manifest.get("shadow_required") is True and
      manifest.get("pilot_required") is True and manifest.get("production_activation_allowed") is False and
      manifest.get("active_self_mutation") is False and manifest.get("self_promotion") is False and
      manifest.get("permission_expansion") is False and manifest.get("architecture_council_final_authority") is True and
      float(manifest.get("automatic_external_spend_eur") or 0)==0 and
      candplan.get("owner")=="agent-foundry" and candplan.get("isolated") is True and
      candplan.get("incumbent_control_group") is True and candplan.get("shadow_required") is True and
      candplan.get("pilot_required") is True and evidence_maturity.get("candidate_evidence_mature") is True
    )
    real_cases=[];no_regression=True
    root=runtime/"golden-path-runs"
    with tempfile.TemporaryDirectory(prefix="v661-acceptance-shadow-") as td:
        work=Path(td)
        for run in sorted(root.iterdir() if root.is_dir() else []):
            contract=run/"planning/functional-contract.json"
            evidence=run/"external-assurance/acceptance-evidence.json"
            observed=run/"external-assurance/acceptance.json"
            if not all(p.is_file() for p in (contract,evidence,observed)):continue
            inc_out=work/(run.name+"-inc.json");cand_out=work/(run.name+"-cand.json")
            inc=run_engine(incumbent,contract,evidence,inc_out)
            cand=run_engine(candidate,contract,evidence,cand_out)
            obs=load(observed)
            matched=core(inc)==core(cand)==core(obs)
            no_regression=no_regression and matched
            real_cases.append({"run_id":run.name,"passed":matched,
                               "incumbent_accepted":inc.get("accepted"),"candidate_accepted":cand.get("accepted")})

        fixture=work/"adversarial";fixture.mkdir()
        artifact=fixture/"artifact.json";artifact.write_text('{"status":"PASS"}\n',encoding="utf-8")
        digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
        ref=str(artifact)+"#sha256:"+digest
        contract=fixture/"contract.json";evidence=fixture/"evidence.json"
        save(contract,{"schema":"chacha.dev/functional-contract/v1","contract_id":"v661-adversarial",
                       "criteria":[{"criterion_id":"required","dimension":"functional","required":True,"owner":"product","verification":"evidence"}]})
        save(evidence,{"criteria":[{"criterion_id":"required","state":"PASS","evidence":ref}]})
        artifact.write_text('{"status":"TAMPERED"}\n',encoding="utf-8")
        inc=run_engine(incumbent,contract,evidence,fixture/"inc.json")
        cand=run_engine(candidate,contract,evidence,fixture/"cand.json")
        adversarial_gain=inc.get("accepted") is True and cand.get("accepted") is False

    real_passed=sum(1 for x in real_cases if x["passed"])
    pilot_eligible=bool(governance_ok and real_cases and real_passed==len(real_cases) and adversarial_gain)
    result={
      "schema":SCHEMA,
      "candidate_id":manifest.get("candidate_id"),
      "subject_agent":"acceptance-engineer",
      "owner":"agent-foundry",
      "incumbent_digest":sha(incumbent),"candidate_digest":sha(candidate),"manifest_digest":sha(manifest_path),
      "real_shadow_case_count":len(real_cases),"real_shadow_passed_count":real_passed,
      "real_shadow_no_regression":no_regression,
      "adversarial_digest_mismatch_gain":adversarial_gain,
      "governance_contract_valid":governance_ok,
      "decision":"ISOLATED_PILOT_ELIGIBLE_HOLD_INCUMBENT" if pilot_eligible else "BLOCK_CANDIDATE",
      "isolated":True,"incumbent_control_group":True,"shadow_required":True,"pilot_required":True,
      "pilot_mode":"ISOLATED_READ_ONLY","production_activation_allowed":False,"promotion_allowed":False,
      "measurable_gain_required_for_future_promotion":True,"no_material_regression_required":True,
      "active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
      "technology_watch_revalidation_required":True,"logician_falsification_required":True,
      "guardian_required":True,"sentinel_required":True,"architecture_council_final_authority":True,
      "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
      "automatic_external_spend_eur":0,"real_cases":real_cases
    }
    save(a.output,result)
    print("CHACHA_DEV_V661_ACCEPTANCE_REAL_SHADOW="+("PASS" if no_regression and real_cases else "BLOCK"))
    print("CHACHA_DEV_V661_ACCEPTANCE_ADVERSARIAL_GAIN="+("PASS" if adversarial_gain else "BLOCK"))
    print("CHACHA_DEV_V661_ACCEPTANCE_ISOLATED_PILOT="+("PASS" if pilot_eligible else "BLOCK"))
    print("CHACHA_DEV_V661_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
    print("CHACHA_DEV_V661_ACCEPTANCE_PROMOTION=NO")
    print("CHACHA_DEV_V661_INCUMBENT_CONTROL_GROUP=YES")
    print("CHACHA_DEV_V661_SELF_MUTATION=NO")
    print("CHACHA_DEV_V661_SELF_PROMOTION=NO")
    print("CHACHA_DEV_V661_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
    print("CHACHA_DEV_V661_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if pilot_eligible else 20

if __name__=="__main__":
    raise SystemExit(main())
