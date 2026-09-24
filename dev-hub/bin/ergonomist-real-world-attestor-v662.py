#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/real-world-agent-attestation/v1"
VERIFIER="v662-ergonomist-real-world-attestor"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x

def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def canon(v:Any)->str:
    return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))

def digest(v:Any)->str:
    return "sha256:"+hashlib.sha256(canon(v).encode()).hexdigest()

def now_iso()->str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def same_path(value:Any,path:Path)->bool:
    try:return Path(str(value or "")).resolve()==path.resolve()
    except Exception:return False

def council_pass(council:dict[str,Any],advisor:str)->bool:
    rows=[x for x in (council.get("decisions") or []) if isinstance(x,dict)]
    return bool(rows) and all(str((x.get("mandatory_advisors") or {}).get(advisor) or "")=="PASS" for x in rows)

def evaluate(run:Path)->dict[str,Any]|None:
    p=run/"planning"
    ux_p=p/"ux-planning-report.json"
    comp_p=p/"multi-agent-compromise.json"
    council_p=p/"architecture-decision-council.json"
    boot_p=p/"bootstrap-result.json"
    contract_p=p/"functional-contract.json"
    preplan_p=p/"preplan.json"
    if not all(x.is_file() for x in (ux_p,comp_p,council_p,boot_p,contract_p,preplan_p)):return None
    ux=load(ux_p);comp=load(comp_p);council=load(council_p);boot=load(boot_p);contract=load(contract_p);pre=load(preplan_p)
    if ux.get("schema")!="chacha.dev/ux-planning-report/v1":return None
    pos=next((x for x in (comp.get("positions") or []) if isinstance(x,dict) and x.get("agent")=="ergonomist"),None)
    final=((comp.get("compromise") or {}).get("ux_proposal") or {})
    body=dict(ux);reported=str(body.pop("report_digest",""))
    recomputed=digest(body)
    proposal=(pos or {}).get("proposal") or {}
    evidence_refs=[str(x) for x in ((pos or {}).get("evidence_refs") or [])]
    checks={
      "report_digest_recomputed":reported==recomputed and reported.startswith("sha256:"),
      "functional_contract_bound":str(ux.get("contract_id") or "")==str(contract.get("contract_id") or ""),
      "preplan_primary_domains_count":int(ux.get("primary_domain_count") or 0)==len(pre.get("primary_domains") or []),
      "compromise_position_present":pos is not None,
      "challenge_status_bound":str((pos or {}).get("status") or "")==str(ux.get("challenge_status") or ""),
      "ux_contract_bound":proposal.get("ux_contract")==ux.get("ux_contract"),
      "recommended_action_bound":str(proposal.get("recommended_next_action") or "")==str(ux.get("recommended_next_action") or ""),
      "report_digest_referenced":reported in evidence_refs,
      "final_compromise_ux_bound":final==proposal,
      "central_compromise_found":comp.get("central_compromise_found") is True and comp.get("continuation_allowed") is True,
      "bootstrap_consumed_ux_report":same_path(boot.get("ux_planning_report"),ux_p),
      "bootstrap_challenge_bound":str(boot.get("ux_challenge_status") or "")==str(ux.get("challenge_status") or ""),
      "bootstrap_consumed_compromise":boot.get("architecture_council_consumed_compromise") is True,
      "architecture_council_logic_ux_valid":(council.get("logic_ux_compromise") or {}).get("valid") is True,
      "architecture_council_advisor_pass":council_pass(council,"logic-ux-compromise"),
      "architecture_council_final_authority":ux.get("architecture_council_final_authority") is True and boot.get("architecture_decision_allowed") is True,
      "direct_mutation_false":ux.get("direct_mutation") is False,
      "automatic_external_spend_zero":float(ux.get("automatic_external_spend_eur") or 0)==0 and float(boot.get("external_spend_eur") or 0)==0
    }
    return {"case_id":"ergonomist:"+run.name,"run_id":run.name,"passed":all(checks.values()),"checks":checks,
            "source_refs":[str(x) for x in (ux_p,comp_p,council_p,boot_p,contract_p,preplan_p)],
            "report_digest":reported,"challenge_status":ux.get("challenge_status")}

def build(runtime_root:Path)->dict[str,Any]:
    cases=[]
    root=runtime_root/"golden-path-runs"
    for run in sorted(root.iterdir() if root.is_dir() else []):
        if run.is_dir():
            x=evaluate(run)
            if x:cases.append(x)
    total=len(cases);passed=sum(1 for x in cases if x.get("passed") is True)
    value=round(100.0*passed/total,1) if total else None
    return {
      "schema":SCHEMA,"subject_agent":"ergonomist","verifier":VERIFIER,
      "verification":"INDEPENDENTLY_RECOMPUTED","verification_scope":"REAL_RUNTIME",
      "generated_at":now_iso(),"case_count":total,"passed_case_count":passed,
      "dimension_values":{"evidence_quality":value,"handoff_quality":value,"authority_discipline":value},
      "production_truth_eligible":total>0,"accuracy_inference":False,
      "source_refs":sorted({r for c in cases for r in (c.get("source_refs") or [])}),"cases":cases,
      "decision_authority":False,"direct_mutation":False,"active_self_mutation":False,
      "self_promotion":False,"permission_expansion":False,
      "canonical_observation_bus_mutation":False,"benchmark_evidence_mutation":False,
      "architecture_council_final_authority":True,"automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--runtime-root",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
    out=build(a.runtime_root.resolve());save(a.output,out)
    ok=out["case_count"]>0 and out["passed_case_count"]==out["case_count"]
    print("CHACHA_DEV_V662_ERGONOMIST_REAL_WORLD_ATTESTATION="+("PASS" if ok else "BLOCK"))
    print("ERGONOMIST_CASES="+str(out["case_count"]))
    print("ERGONOMIST_STRUCTURAL="+str(out["dimension_values"]["evidence_quality"]))
    print("CHACHA_DEV_V662_ERGONOMIST_ACCURACY_INFERENCE=NO")
    print("CHACHA_DEV_V662_CANONICAL_OBSERVATION_BUS_MUTATION=NO")
    print("CHACHA_DEV_V662_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0 if ok else 20

if __name__=="__main__":raise SystemExit(main())
