#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys,time
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise RuntimeError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def run(argv:list[str],stdout:Path,timeout:int=60)->int:
    p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
    stdout.write_text(p.stdout,encoding="utf-8")
    if p.stderr:stdout.with_suffix(stdout.suffix+".err").write_text(p.stderr,encoding="utf-8")
    return p.returncode
def json_stdout(path:Path)->dict[str,Any]:
    text=path.read_text(encoding="utf-8").strip().splitlines()
    for line in text:
        try:
            x=json.loads(line)
            if isinstance(x,dict):return x
        except Exception:pass
    raise RuntimeError("JSON_OUTPUT_MISSING:"+str(path))

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--project-id",required=True);ap.add_argument("--revision",required=True)
    ap.add_argument("--compromise",type=Path,required=True);ap.add_argument("--council",type=Path,required=True)
    ap.add_argument("--logic-report",type=Path,required=True);ap.add_argument("--ux-report",type=Path,required=True)
    ap.add_argument("--implementation-manifest",type=Path,required=True)
    ap.add_argument("--implementation-verification",type=Path,required=True)
    ap.add_argument("--guardian-functional-receipt-id",required=True)
    ap.add_argument("--sentinel-technical-receipt-id",required=True)
    ap.add_argument("--repo-root",type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--final-output",type=Path,required=True)
    ap.add_argument("--evidence-ledger",type=Path)
    a=ap.parse_args()

    root=a.repo_root.resolve();bin_dir=root/"dev-hub/bin";cfg=root/"dev-hub/config"
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    comp=load(a.compromise);cd=str(comp.get("dossier_digest") or "")
    if not cd:raise SystemExit("COMPROMISE_DIGEST_MISSING")

    # Internal second reads.
    internal=[]
    for agent,report in (("logician",a.logic_report),("ergonomist",a.ux_report)):
        review=out/(agent+"-final-review.json")
        p=subprocess.run([
          sys.executable,str(bin_dir/"internal-final-review.py"),
          "--agent",agent,"--project-id",a.project_id,"--revision",a.revision,
          "--report",str(report),"--compromise",str(a.compromise),
          "--implementation-manifest",str(a.implementation_manifest),
          "--implementation-verification",str(a.implementation_verification),
          "--output",str(review)
        ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
        if p.returncode not in (0,20):raise RuntimeError("INTERNAL_FINAL_REVIEW_FAILED:"+agent+":"+p.stderr[-500:])
        internal.append(review)

    # External authorities issue their own final reviews.
    g_out=out/"guardian-final-review.out"
    rc=run([sys.executable,str(bin_dir/"guardian-client.py"),"--policy",str(cfg/"guardian-runtime-policy.v1.json"),
      "final-review","--project-id",a.project_id,"--revision",a.revision,
      "--compromise-digest",cd,"--source-receipt-id",a.guardian_functional_receipt_id,
      "--implementation-verified"],g_out)
    if rc not in (0,20):raise RuntimeError("GUARDIAN_FINAL_REVIEW_UNAVAILABLE")

    s_out=out/"sentinel-final-review.out"
    rc=run([sys.executable,str(bin_dir/"sentinel-client.py"),"--policy",str(cfg/"sentinel-runtime-policy.v1.json"),
      "final-review","--project-id",a.project_id,"--revision",a.revision,
      "--compromise-digest",cd,"--source-receipt-id",a.sentinel_technical_receipt_id,
      "--implementation-verified"],s_out)
    if rc not in (0,20):raise RuntimeError("SENTINEL_FINAL_REVIEW_UNAVAILABLE")

    for role in ("curator","bastion","intendant"):
        path=out/(role+"-final-review.out")
        rc=run([sys.executable,str(bin_dir/"specialist-authority-client.py"),
          "--policy",str(cfg/(role+"-runtime-policy.v1.json")),"review",
          "--project-id",a.project_id,"--revision",a.revision,
          "--compromise-digest",cd,"--implementation-verified"],path)
        if rc not in (0,20):raise RuntimeError(role.upper()+"_FINAL_REVIEW_UNAVAILABLE")

    # Exchange must independently re-read all five external reviews.
    batch=None
    for attempt in range(8):
        ex=out/"external-final-reviews.out"
        rc=run([sys.executable,str(bin_dir/"assurance-exchange-client.py"),
          "--policy",str(cfg/"assurance-exchange-runtime-policy.v1.json"),"final-reviews",
          "--project-id",a.project_id,"--revision",a.revision,"--compromise-digest",cd],ex)
        if rc==0:
            batch=json_stdout(ex)
            if int(batch.get("count") or 0)>=5:break
        time.sleep(1)
    if not batch or int(batch.get("count") or 0)<5:
        raise RuntimeError("FIVE_EXTERNAL_FINAL_REVIEWS_NOT_SOURCE_REVERIFIED")
    ext={str(x.get("agent")):x for x in batch.get("items") or []}
    if set(ext)!={"guardian","sentinel","curator","bastion","intendant"}:
        raise RuntimeError("EXTERNAL_FINAL_REVIEW_SET_INVALID:"+",".join(sorted(ext)))
    for role,x in ext.items():
        if x.get("source_reverified") is not True:raise RuntimeError("EXTERNAL_REVIEW_NOT_REVERIFIED:"+role)
        save(out/(role+"-source-reverified-review.json"),x)

    # One fail-closed release gate for all seven.
    release=out/"compromise-release-receipt.json"
    cmd=[sys.executable,str(bin_dir/"compromise-release-gate.py"),
      "--project-id",a.project_id,"--revision",a.revision,
      "--policy",str(cfg/"compromise-release-gate.v1.json"),
      "--compromise",str(a.compromise),"--council",str(a.council),
      "--implementation-verification",str(a.implementation_verification),
      "--output",str(release)]
    for p in internal:cmd+=["--agent-review",str(p)]
    for role in ("guardian","sentinel","curator","bastion","intendant"):
        cmd+=["--agent-review",str(out/(role+"-source-reverified-review.json"))]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    gate=load(release)

    if p.returncode==0 and gate.get("release_allowed") is True:
        final={
          "schema":"chacha.dev/seven-agent-final-delivery/v1","version":"1.0.0",
          "project_id":a.project_id,"revision":a.revision,"compromise_digest":cd,
          "status":"DELIVERED","delivery_allowed":True,
          "release_receipt_digest":gate.get("receipt_digest"),
          "seven_agents":["logician","ergonomist","guardian","sentinel","curator","bastion","intendant"],
          "all_seven_accept":True,"five_external_source_reverified":True,
          "two_internal_second_reads":True,
          "local_acceptance_was_provisional":True,
          "direct_mutation":False,"delivered_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
        }
        save(a.final_output,final)
        if a.evidence_ledger:
            ledger=load(a.evidence_ledger)
            artifacts=ledger.setdefault("artifacts",{})
            gates=ledger.setdefault("gates",{})
            stamp=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
            artifacts["compromise-release-receipt"]={"status":"OK","source":str(release),"observed_at":stamp}
            artifacts["seven-agent-final-delivery-receipt"]={"status":"OK","source":str(a.final_output),"observed_at":stamp}
            gates["compromise-release"]={"status":"OK","source":str(a.final_output),"observed_at":stamp}
            save(a.evidence_ledger,ledger)
        print("CHACHA_DEV_V636_SEVEN_AGENT_FINAL_COMPROMISE=PASS")
        print("FINAL_DELIVERY_ALLOWED=YES")
        return 0

    blockers=gate.get("reason_codes") or []
    agents=sorted({x.split(":")[1] for x in blockers if ":" in x and x.split(":")[1] in
                   {"logician","ergonomist","guardian","sentinel","curator","bastion","intendant"}})
    final={
      "schema":"chacha.dev/seven-agent-final-delivery/v1","version":"1.0.0",
      "project_id":a.project_id,"revision":a.revision,"compromise_digest":cd,
      "status":"REMEDIATION_REQUIRED","delivery_allowed":False,
      "reason_codes":blockers,"impacted_agents":agents,
      "central_brain_first_action":"REPAIR_IMPLEMENTATION_AND_RETEST",
      "renegotiate_agent_proposals_only_if_existing_compromise_becomes_infeasible":True,
      "direct_mutation":False,"checked_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    }
    save(a.final_output,final)
    if a.evidence_ledger:
        ledger=load(a.evidence_ledger)
        ledger.setdefault("gates",{})["compromise-release"]={
          "status":"BLOCKED","source":str(a.final_output),
          "observed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
          "reason":"SEVEN_AGENT_FINAL_COMPROMISE_NOT_REACHED"
        }
        save(a.evidence_ledger,ledger)
    print("CHACHA_DEV_V636_SEVEN_AGENT_FINAL_COMPROMISE=BLOCK")
    print("FINAL_DELIVERY_ALLOWED=NO")
    print("CENTRAL_REMEDIATION_FIRST=YES")
    return 20

if __name__=="__main__":raise SystemExit(main())
