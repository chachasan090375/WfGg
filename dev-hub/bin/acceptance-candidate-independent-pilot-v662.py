#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/acceptance-candidate-independent-pilot/v1"
VERIFIER="v662-acceptance-independent-oracle"

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def sha(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def parse_ref(value:Any)->tuple[Path,str]|None:
    ref=str(value or "")
    if "#sha256:" not in ref:return None
    raw,digest=ref.rsplit("#sha256:",1)
    if len(digest)!=64:return None
    return Path(raw),digest

def verified_ref(value:Any)->bool:
    row=parse_ref(value)
    if not row:return False
    p,d=row
    return p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==d

def oracle(contract:dict[str,Any],evidence:dict[str,Any])->dict[str,Any]:
    emap={str(x.get("criterion_id")):x for x in (evidence.get("criteria") or []) if isinstance(x,dict)}
    rows=[];routes={}
    for c in contract.get("criteria") or []:
        if not isinstance(c,dict):continue
        cid=str(c.get("criterion_id"));required=bool(c.get("required",True));e=emap.get(cid) or {}
        state=str(e.get("state") or "UNVERIFIED");eref=e.get("evidence")
        if state=="PASS" and not verified_ref(eref):state="UNVERIFIED"
        rows.append({"criterion_id":cid,"dimension":c.get("dimension"),"required":required,
                     "owner":c.get("owner"),"state":state,"evidence":eref})
        if required and state!="PASS":
            routes.setdefault(str(c.get("owner") or "core"),[]).append(cid)
    ok=not routes
    return {"schema":"chacha.dev/acceptance-result/v1","accepted":ok,"criteria":rows,
            "return_to_factories":routes,"delivery_allowed":ok,"local_acceptance_candidate":ok,
            "final_delivery_allowed":False,"final_delivery_gate":"seven-agent-final-compromise",
            "final_delivery_receipt_required":True}

def core(x:dict[str,Any])->dict[str,Any]:
    keys=("schema","accepted","criteria","return_to_factories","delivery_allowed","local_acceptance_candidate",
          "final_delivery_allowed","final_delivery_gate","final_delivery_receipt_required")
    return {k:x.get(k) for k in keys}

def run_engine(script:Path,contract:Path,evidence:Path,output:Path)->dict[str,Any]:
    p=subprocess.run([sys.executable,str(script),"--contract",str(contract),"--evidence",str(evidence),"--output",str(output)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if p.returncode!=0:raise RuntimeError("ENGINE_FAILED:"+str(script)+":"+p.stderr[-1600:]+p.stdout[-1600:])
    return load(output)

def clone_adversarial(contract_path:Path,evidence_path:Path,dest:Path)->tuple[Path,Path,bool]:
    contract=load(contract_path);evidence=load(evidence_path);emap=[x for x in (evidence.get("criteria") or []) if isinstance(x,dict)]
    dest.mkdir(parents=True,exist_ok=True);tampered=False
    for i,row in enumerate(emap):
        ref=parse_ref(row.get("evidence"))
        if not ref:continue
        src,digest=ref
        if not src.is_file():continue
        cp=dest/("evidence-"+str(i)+src.suffix)
        shutil.copy2(src,cp)
        row["evidence"]=str(cp)+"#sha256:"+digest
        cid=str(row.get("criterion_id") or "")
        criterion=next((c for c in (contract.get("criteria") or []) if str(c.get("criterion_id") or "")==cid),{})
        if not tampered and bool(criterion.get("required",True)) and str(row.get("state") or "")=="PASS":
            with cp.open("ab") as fh:fh.write(b"\nV662_TAMPER\n")
            tampered=True
    cp_contract=dest/"contract.json";cp_evidence=dest/"evidence.json"
    save(cp_contract,contract);save(cp_evidence,evidence)
    return cp_contract,cp_evidence,tampered

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,required=True)
    ap.add_argument("--runtime-root",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();repo=a.repo_root.resolve();runtime=a.runtime_root.resolve()
    incumbent=repo/"dev-hub/bin/acceptance-engine.py"
    candidate=repo/"dev-hub/candidates/acceptance-engineer/v661/acceptance-engine-candidate.py"
    manifest=repo/"dev-hub/candidates/acceptance-engineer/v661/candidate-manifest.json"
    if not all(p.is_file() for p in (incumbent,candidate,manifest)):raise SystemExit("V662_PILOT_INPUT_MISSING")
    m=load(manifest)
    governance=(
      m.get("owner")=="agent-foundry" and m.get("isolated") is True and m.get("incumbent_control_group") is True and
      m.get("shadow_required") is True and m.get("pilot_required") is True and m.get("production_activation_allowed") is False and
      m.get("active_self_mutation") is False and m.get("self_promotion") is False and m.get("permission_expansion") is False and
      m.get("architecture_council_final_authority") is True and float(m.get("automatic_external_spend_eur") or 0)==0
    )
    real=[];adversarial=[]
    with tempfile.TemporaryDirectory(prefix="v662-acceptance-independent-pilot-") as td:
        work=Path(td)
        root=runtime/"golden-path-runs"
        for run in sorted(root.iterdir() if root.is_dir() else []):
            contract=run/"planning/functional-contract.json";evidence=run/"external-assurance/acceptance-evidence.json"
            observed=run/"external-assurance/acceptance.json"
            if not all(p.is_file() for p in (contract,evidence,observed)):continue
            expected=oracle(load(contract),load(evidence))
            inc=run_engine(incumbent,contract,evidence,work/(run.name+"-real-inc.json"))
            cand=run_engine(candidate,contract,evidence,work/(run.name+"-real-cand.json"))
            obs=load(observed)
            real.append({
              "run_id":run.name,
              "oracle_accepted":expected["accepted"],
              "candidate_matches_oracle":core(cand)==core(expected),
              "incumbent_matches_oracle":core(inc)==core(expected),
              "observed_matches_oracle":core(obs)==core(expected)
            })
            adv_dir=work/(run.name+"-adversarial")
            adv_contract,adv_evidence,tampered=clone_adversarial(contract,evidence,adv_dir)
            if not tampered:continue
            expected_adv=oracle(load(adv_contract),load(adv_evidence))
            inc_adv=run_engine(incumbent,adv_contract,adv_evidence,adv_dir/"inc.json")
            cand_adv=run_engine(candidate,adv_contract,adv_evidence,adv_dir/"cand.json")
            adversarial.append({
              "run_id":run.name,
              "oracle_accepted":expected_adv["accepted"],
              "candidate_matches_oracle":core(cand_adv)==core(expected_adv),
              "incumbent_matches_oracle":core(inc_adv)==core(expected_adv),
              "candidate_blocked":cand_adv.get("accepted") is False,
              "incumbent_accepted":inc_adv.get("accepted") is True
            })
    real_candidate_ok=sum(1 for x in real if x["candidate_matches_oracle"])
    real_inc_ok=sum(1 for x in real if x["incumbent_matches_oracle"])
    adv_candidate_ok=sum(1 for x in adversarial if x["candidate_matches_oracle"] and x["candidate_blocked"])
    adv_inc_missed=sum(1 for x in adversarial if not x["incumbent_matches_oracle"] and x["incumbent_accepted"])
    measurable_gain=bool(adversarial and adv_candidate_ok==len(adversarial) and adv_inc_missed==len(adversarial))
    passed=bool(governance and real and real_candidate_ok==len(real) and real_inc_ok==len(real) and measurable_gain)
    out={
      "schema":SCHEMA,"verifier":VERIFIER,"verification":"INDEPENDENTLY_RECOMPUTED",
      "verification_scope":"ISOLATED_REAL_RUNTIME_PILOT","generated_at":now_iso(),
      "candidate_id":m.get("candidate_id"),"owner":"agent-foundry",
      "incumbent_digest":sha(incumbent),"candidate_digest":sha(candidate),"manifest_digest":sha(manifest),
      "real_case_count":len(real),"real_candidate_passed":real_candidate_ok,"real_incumbent_passed":real_inc_ok,
      "adversarial_case_count":len(adversarial),"adversarial_candidate_passed":adv_candidate_ok,
      "adversarial_incumbent_missed":adv_inc_missed,"measurable_gain":measurable_gain,
      "decision":"INDEPENDENT_ISOLATED_PILOT_PASS_HOLD_INCUMBENT" if passed else "BLOCK_CANDIDATE",
      "isolated":True,"incumbent_control_group":True,"production_activation_allowed":False,"promotion_allowed":False,
      "direct_mutation":False,"active_self_mutation":False,"self_promotion":False,"permission_expansion":False,
      "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
      "technology_watch_revalidation_required":True,"logician_falsification_required":True,
      "guardian_required":True,"sentinel_required":True,"architecture_council_final_authority":True,
      "automatic_external_spend_eur":0,"real_cases":real,"adversarial_cases":adversarial
    }
    save(a.output,out)
    print("CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_REAL="+("PASS" if real and real_candidate_ok==len(real) else "BLOCK"))
    print("CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_ADVERSARIAL="+("PASS" if measurable_gain else "BLOCK"))
    print("CHACHA_DEV_V662_ACCEPTANCE_INDEPENDENT_PILOT="+("PASS" if passed else "BLOCK"))
    print("CHACHA_DEV_V662_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
    print("CHACHA_DEV_V662_ACCEPTANCE_PROMOTION=NO")
    print("CHACHA_DEV_V662_INCUMBENT_CONTROL_GROUP=YES")
    print("CHACHA_DEV_V662_SELF_MUTATION=NO")
    print("CHACHA_DEV_V662_SELF_PROMOTION=NO")
    print("CHACHA_DEV_V662_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
    print("CHACHA_DEV_V662_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if passed else 20

if __name__=="__main__":
    raise SystemExit(main())
