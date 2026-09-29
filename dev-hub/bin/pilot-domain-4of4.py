#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,re,subprocess,tempfile,urllib.request
from pathlib import Path

SHA="70f4e826d369cfee870c64ca5386c06959d25c7f"
CAND=Path(f"/tmp/chacha-domain-candidate-{SHA[:12]}")
CONTROL=Path("/tmp/chacha-control-plane-after-attestation.json")
CURRENT=Path("/opt/chacha-dev/platform/current")
WANTED={
 "capability:domain-knowledge-research:technology-radar",
 "capability:domain-knowledge-research:architecture-optimization",
 "capability:domain-knowledge-research:library-docs",
 "capability:domain-knowledge-research:collector-knowledge-inspect",
}
PERM={"technology-radar":"read","architecture-optimization":"plan","library-docs":"read","collector-knowledge-inspect":"read"}
ADAPTERS={
 "platform-command-adapter":"dev-hub/adapters/platform-command-adapter.py",
 "context7-mcp-adapter":"dev-hub/adapters/context7-mcp-adapter.py",
 "collector-knowledge-adapter":"dev-hub/adapters/collector-knowledge-adapter.py",
}

def load(p): return json.loads(Path(p).read_text())
def run(a,**kw): return subprocess.run(a,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,**kw)
def fail(s): raise SystemExit("PILOT_FAIL="+s)
def pairs(v): return {(str(x.get("type")),str(x.get("id"))) for x in v or [] if isinstance(x,dict) and x.get("type") and x.get("id")}

def main():
 if not CAND.is_dir(): fail("CANDIDATE_WORKTREE_MISSING")
 if run(["git","-C",str(CAND),"rev-parse","HEAD"]).stdout.strip()!=SHA: fail("CANDIDATE_SHA_MISMATCH")
 if not CONTROL.is_file(): fail("CONTROL_PLANE_JSON_MISSING")
 active_before=str(CURRENT.resolve())
 health_before=urllib.request.urlopen("http://127.0.0.1:8792/healthz",timeout=5).read().decode()
 d=load(CONTROL)["report"]["domain_execution"]["decision"]
 tasks=d["domain_toolchain_readiness"]["tasks"]
 task_map={str(t.get("_task_id") or t.get("task_id") or t.get("id")):t for t in tasks}
 if not WANTED.issubset(task_map): fail("TASK_CONTRACT_SET_INCOMPLETE")
 rows=d["independent_verification"]["rows"]
 old_pass=sum(1 for r in rows if r.get("returncode")==0)
 reports={}
 for row in rows:
  tid=str(row.get("task_id") or "")
  if tid not in WANTED or row.get("returncode")==0: continue
  hits=re.findall(r'/opt/chacha-dev/runtime/transactions/[^"\\\s]+/verification-report\.json',json.dumps(row,ensure_ascii=False))
  if not hits: fail("REPORT_PATH_MISSING:"+tid)
  p=Path(hits[0])
  if not p.is_file(): fail("REPORT_FILE_MISSING:"+str(p))
  reports[tid]=p
 if set(reports)!=WANTED: fail("FAILED_REPORT_SET_MISMATCH")

 # Historical proof: for the three evidence-only failures every non-evidence check was already PASS.
 for tid,p in reports.items():
  rep=load(p); suffix=tid.rsplit(":",1)[-1]
  checks=rep.get("checks") or []
  non_evidence=[c for c in checks if not str(c.get("id") or "").startswith("evidence-")]
  if suffix!="collector-knowledge-inspect":
   if any(c.get("status")!="PASS" for c in non_evidence): fail("HISTORICAL_NON_EVIDENCE_NOT_PASS:"+tid)
  else:
   oc=[c for c in checks if c.get("id")=="outputs-declared"]
   if len(oc)!=1 or oc[0].get("status")!="FAIL" or "collector-knowledge-status" not in str(oc[0].get("detail")): fail("COLLECTOR_OLD_OUTPUT_FAILURE_NOT_PROVEN")
  ev=[c for c in checks if str(c.get("id") or "").startswith("evidence-")]
  if not any(c.get("status")=="NEEDS_CHECK" for c in ev): fail("OLD_EXTERNAL_EVIDENCE_BLOCKER_NOT_PROVEN:"+tid)

 work=Path(tempfile.mkdtemp(prefix="chacha-domain-4of4-")); evidence_root=work/"evidence"
 broker=CAND/"dev-hub/bin/verification-broker.py"; policy=CAND/"dev-hub/config/verification-broker.v1.json"
 verified=[]
 for i,tid in enumerate(sorted(WANTED),1):
  ready=task_map[tid]; suffix=tid.rsplit(":",1)[-1]
  if ready.get("gate")!="READY": fail("GATE_NOT_READY:"+tid)
  caps=ready.get("capabilities") or []
  if len(caps)!=1: fail("CAPABILITY_CARDINALITY:"+tid)
  cap=str(caps[0]); sel=ready.get("selected_candidate") or {}
  provider=str(ready.get("selected_provider") or sel.get("provider") or ""); adapter=str(sel.get("adapter_id") or "")
  if adapter not in ADAPTERS: fail("ADAPTER_UNSUPPORTED:"+adapter)
  # Differential pilot: outputs are empty on purpose. Historical reports already prove the old output
  # contract passed for the 3 evidence-only failures; Collector specifically needs the fixed adapter
  # to stop inventing its undeclared output.
  task={"id":tid,"kind":"capability","capabilities":[cap],"permission":PERM[suffix],"outputs":[],"verification":{"mode":"independent-agent"}}
  metadata={"collector_knowledge":{"action":"status"}} if suffix=="collector-knowledge-inspect" else {}
  project=str(load(reports[tid]).get("project") or "chacha-dev-platform")
  envlp={"schema":"chacha.dev/dispatch-envelope/v1","project":project,"transition":"PILOT","run_id":f"pilot-four-{i}","wave":0,"task":task,"bindings":[{"capability":cap,"provider":provider,"adapter":adapter,"health_state":"HEALTHY"}],"policy_context":{"human_approval_required":False,"timeout_seconds":120},"workspace":None,"metadata":metadata}
  tdir=work/f"task-{i}"; tdir.mkdir(parents=True)
  env=dict(os.environ); env["CHACHA_DEV_EVIDENCE_ROOT"]=str(evidence_root); env["CHACHA_DEV_PLATFORM_ROOT"]=str(CURRENT)
  pr=run(["python3",str(CAND/ADAPTERS[adapter])],input=json.dumps(envlp),env=env,timeout=120)
  if pr.returncode!=0:
   print(pr.stdout[-2500:]); print(pr.stderr[-2500:]); fail("ADAPTER_FAILED:"+tid)
  result=json.loads(pr.stdout.strip().splitlines()[-1])
  if result.get("status")!="OK": fail("RESULT_NOT_OK:"+tid+":"+str(result.get("summary")))
  evidence=result.get("evidence") or []
  if not evidence: fail("NO_EVIDENCE:"+tid)
  for ev in evidence:
   src=Path(str(ev.get("source") or ""))
   if not src.is_absolute() or not src.is_file(): fail("NON_LOCAL_EVIDENCE:"+tid)
   if "sha256:"+hashlib.sha256(src.read_bytes()).hexdigest()!=str(ev.get("digest") or ""): fail("EVIDENCE_DIGEST_MISMATCH:"+tid)
  if pairs(result.get("outputs")): fail("OUTPUT_CONTRACT_NOT_EMPTY:"+tid)
  rp=tdir/"task-result.json"; gp=tdir/"task-graph.json"; vrp=tdir/"verification-report.json"; vtp=tdir/"verified-task-result.json"
  rp.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
  gp.write_text(json.dumps({"schema":"chacha.dev/task-graph/v1","project":project,"tasks":[task]},indent=2,ensure_ascii=False)+"\n")
  vr=run(["python3",str(broker),"--result",str(rp),"--graph",str(gp),"--policy",str(policy),"--report",str(vrp),"--verified-result",str(vtp),"--verifier","verification-broker","--method","independent-agent"],timeout=60)
  if vr.returncode!=0:
   if vrp.is_file(): print(vrp.read_text())
   print(vr.stdout); print(vr.stderr); fail("BROKER_FAILED:"+tid)
  if load(vrp).get("status")!="VERIFIED": fail("BROKER_NOT_VERIFIED:"+tid)
  final=load(vtp)
  if (final.get("verification") or {}).get("status")!="VERIFIED": fail("FINAL_NOT_VERIFIED:"+tid)
  verified.append(tid); print("VERIFIED="+tid)

 active_after=str(CURRENT.resolve()); health_after=urllib.request.urlopen("http://127.0.0.1:8792/healthz",timeout=5).read().decode()
 if active_after!=active_before: fail("PRODUCTION_RELEASE_CHANGED")
 if len(verified)!=4: fail("FOUR_TASK_PILOT_INCOMPLETE")
 if old_pass!=3: fail("HISTORICAL_PASS_COUNT_CHANGED:"+str(old_pass))
 print("DECIDED=pilot_only_four_previous_blockers")
 print("EXECUTED=4_targeted_differential_pilots")
 print("VERIFIED_TASKS=4")
 print("HISTORICAL_VERIFIED_TASKS=3")
 print("FOUR_PREVIOUS_BLOCKER_CONDITIONS_CLEARED=PASS")
 print("PRODUCTION_RELEASE_UNCHANGED=PASS")
 print("DIRECT_OPERATOR_BEFORE="+health_before)
 print("DIRECT_OPERATOR_AFTER="+health_after)
 print("PILOT_ROOT="+str(work))
 print("NEXT=isolated_full_domain_control_plane_pilot")

if __name__=="__main__": main()
