#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re,sys,time
from pathlib import Path
from typing import Any
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
import promotion_transaction as ptx
SCHEMA="chacha.dev/promotion-cycle-evidence/v1"
SHA_RE=re.compile(r"^[0-9a-f]{40}$")

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def digest(path:Path)->str:return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
def iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def capture(runtime_root:Path,promotion_id:str,lease_token:str,candidate_revision:str,phase:str,run_path:Path,before:int,after:int,output:Path,trigger:str="")->dict[str,Any]:
    if phase not in {"CONTROLLED","TIMER"}:raise ValueError("CYCLE_PHASE_INVALID")
    if not SHA_RE.fullmatch(candidate_revision):raise ValueError("EXACT_CANDIDATE_REVISION_REQUIRED")
    if int(after)!=int(before)+1:raise ValueError("CYCLE_COUNTER_NOT_EXACTLY_ONE")
    run_path=run_path.resolve();run=load(run_path)
    if run.get("status")!="CONVERGED" or run.get("next_state")!="RESUME":raise ValueError("CYCLE_NOT_CONVERGED_RESUME")
    if run.get("direct_mutation_by_supervisor") is not False:raise ValueError("CYCLE_DIRECT_MUTATION_FORBIDDEN")
    if int(run.get("automatic_external_spend_eur",0))!=0:raise ValueError("CYCLE_NONZERO_EXTERNAL_SPEND")
    run_id=str(run.get("run_id") or "").strip()
    if not run_id:raise ValueError("CYCLE_RUN_ID_REQUIRED")
    lx=ptx.assert_owner(runtime_root.resolve(),lease_token,promotion_id,candidate_revision,"CAPTURE_"+phase+"_CYCLE_EVIDENCE")
    if phase=="TIMER" and not str(trigger or "").strip():raise ValueError("TIMER_TRIGGER_REQUIRED")
    core={"schema":SCHEMA,"status":"PASS","phase":phase,"candidate_revision":candidate_revision,
          "counter_before":int(before),"counter_after":int(after),"run_id":run_id,"run_path":str(run_path),
          "run_sha256":digest(run_path),"trigger":trigger or None,"captured_at":iso()}
    binding=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    out=ptx.bind_receipt(lx,{**core,"binding_digest":"sha256:"+binding})
    ptx.write_once_json(output.resolve(),out)
    return out

def require(path:Path,phase:str,lx:dict[str,Any],candidate_revision:str,runtime_root:Path|None=None)->dict[str,Any]:
    x=load(path.resolve())
    if x.get("schema")!=SCHEMA or x.get("status")!="PASS" or x.get("phase")!=phase:raise ValueError("CYCLE_EVIDENCE_INVALID:"+phase)
    if runtime_root is None:
        if x.get("candidate_revision")!=candidate_revision or x.get("promotion_lease_id")!=lx.get("lease_id"):raise ValueError("CYCLE_EVIDENCE_SCOPE_MISMATCH:"+phase)
    else:
        ptx.require_receipt_binding(runtime_root.resolve(),x,lx,candidate_revision,"CYCLE_EVIDENCE_"+phase)
    before=int(x.get("counter_before"));after=int(x.get("counter_after"))
    if after!=before+1:raise ValueError("CYCLE_EVIDENCE_COUNTER_INVALID:"+phase)
    if phase=="TIMER" and not str(x.get("trigger") or "").strip():raise ValueError("TIMER_TRIGGER_REQUIRED")
    core={k:x.get(k) for k in ("schema","status","phase","candidate_revision","counter_before","counter_after","run_id","run_path","run_sha256","trigger","captured_at")}
    expected="sha256:"+hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    if x.get("binding_digest")!=expected:raise ValueError("CYCLE_EVIDENCE_BINDING_DIGEST_MISMATCH:"+phase)
    rp=Path(str(x.get("run_path") or ""))
    if not rp.is_file() or digest(rp)!=x.get("run_sha256"):raise ValueError("CYCLE_EVIDENCE_RUN_DIGEST_MISMATCH:"+phase)
    run=load(rp)
    if str(run.get("run_id") or "")!=str(x.get("run_id") or ""):raise ValueError("CYCLE_EVIDENCE_RUN_ID_MISMATCH:"+phase)
    if run.get("status")!="CONVERGED" or run.get("next_state")!="RESUME":raise ValueError("CYCLE_EVIDENCE_RUN_NOT_CONVERGED:"+phase)
    return x

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--runtime-root",type=Path,required=True);ap.add_argument("--promotion-id",required=True);ap.add_argument("--lease-token",required=True);ap.add_argument("--candidate-revision",required=True);ap.add_argument("--phase",choices=["CONTROLLED","TIMER"],required=True);ap.add_argument("--run",type=Path,required=True);ap.add_argument("--before",type=int,required=True);ap.add_argument("--after",type=int,required=True);ap.add_argument("--output",type=Path,required=True);ap.add_argument("--trigger",default="")
    a=ap.parse_args()
    try:out=capture(a.runtime_root,a.promotion_id,a.lease_token,a.candidate_revision,a.phase,a.run,a.before,a.after,a.output,a.trigger);print(json.dumps(out,ensure_ascii=False));return 0
    except Exception as e:print(json.dumps({"schema":SCHEMA,"status":"BLOCK","reason":str(e),"automatic_external_spend_eur":0},ensure_ascii=False));return 20
if __name__=="__main__":raise SystemExit(main())
