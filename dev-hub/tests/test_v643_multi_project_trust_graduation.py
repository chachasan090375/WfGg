#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def mod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

plf=mod("plf_v643",BIN/"production-lineage-feedback.py")
conf=mod("conf_v643",BIN/"component-confidence-engine.py")

def save(path:Path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")

def load(path:Path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha256_file(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def digest_obj(value)->str:
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    return "sha256:"+hashlib.sha256(raw).hexdigest()

def project_control_proof(root:Path,project_id:str,task_id:str,claims_path:Path,artifact_id:str):
    root.mkdir(parents=True,exist_ok=True)
    verified=root/"verified-task-result.json"
    ledger=root/"evidence-ledger.json"
    receipt=root/"project-control-receipt.json"
    claims_digest=sha256_file(claims_path)
    verified_value={
      "schema":"chacha.dev/task-result/v1","project":project_id,"task_id":task_id,
      "producer":"v643-project-runtime","status":"OK","summary":"Verified capability project outcome.",
      "observed_at":"2026-09-24T00:00:00+00:00",
      "outputs":[{"type":"artifact","id":artifact_id,"status":"OK"}],
      "evidence":[{"source":str(claims_path.resolve()),"digest":claims_digest}],
      "verification":{"status":"VERIFIED","method":"machine","verifier":"verification-broker"}
    }
    save(verified,verified_value)
    verified_digest=digest_obj(verified_value)
    ledger_value={
      "schema":"chacha.dev/evidence-ledger/v1","project":project_id,
      "updated_at":"2026-09-24T00:00:00+00:00",
      "artifacts":{artifact_id:{
        "status":"OK","source":str(claims_path.resolve()),"observed_at":"2026-09-24T00:00:00+00:00",
        "digest":verified_digest,"producer":"v643-project-runtime","verifier":"verification-broker",
        "verification_method":"machine","task_id":task_id,"summary":"Verified capability project outcome.",
        "learning_eligibility":"EXACT_LINEAGE"
      }},
      "gates":{},"approvals":{},"risk_acceptances":[],
      "history":[{
        "event":"task-result-ingested","task_id":task_id,"producer":"v643-project-runtime",
        "verifier":"verification-broker","verification_method":"machine","verification_status":"VERIFIED",
        "result_status":"OK","result_digest":verified_digest,"learning_eligibility":"EXACT_LINEAGE",
        "learning_context":None,"changes":["artifact:"+artifact_id+":OK"],
        "observed_at":"2026-09-24T00:00:00+00:00"
      }]
    }
    save(ledger,ledger_value)
    save(receipt,{
      "schema":"chacha.dev/control-transaction-receipt/v1",
      "transaction_id":"ctx-"+project_id+"-"+task_id,"project":project_id,"operation":"verify-result",
      "status":"COMMITTED","verification_status":"VERIFIED","verified_result":str(verified),
      "report":str(root/"verification-report.json"),"new_ledger_digest":digest_obj(ledger_value),
      "updated_at":"2026-09-24T00:00:00+00:00"
    })
    return receipt,ledger

def add_delta(source_db:Path,delta:dict,observed_at:str):
    d=dict(delta);d["observed_at"]=observed_at
    db=sqlite3.connect(source_db)
    db.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",
      (d["delta_id"],d["project_id"],d["source_id"],d["source_kind"],d["deployment_id"],d["sequence"],
       observed_at,(d.get("anomaly") or {}).get("severity"),"digest-"+d["delta_id"],json.dumps(d)))
    db.commit();db.close()

def confidence_snapshot(feedback_db:Path,branch_db:Path,arch_db:Path,conf_db:Path,snap:Path):
    class C:pass
    a=C();a.policy=CFG/"component-confidence.v1.json";a.feedback_db=feedback_db
    a.branch_db=branch_db;a.architecture_db=arch_db;a.db=conf_db;a.snapshot=snap;a.nas=False
    return conf.build(a)

def reconcile(source_db:Path,feedback_db:Path,branch_db:Path,arch_db:Path,output:Path):
    class A:pass
    a=A();a.policy=CFG/"production-lineage-feedback.v1.json";a.source_db=source_db;a.db=feedback_db
    a.branch_db=branch_db;a.architecture_db=arch_db;a.output=output;a.nas=False
    return plf.reconcile(a)

with tempfile.TemporaryDirectory(prefix="v643-trust-") as td_raw:
    td=Path(td_raw)
    capability="v643-durable-read"
    adoption_id="adopt-v643-durable-read-0001"
    provider="playwright-mcp"
    adapter="playwright-mcp-adapter"

    durable=td/"durable.json"
    save(durable,{
      "schema":"chacha.dev/durable-capability-adoptions/v1","version":"1.0.0",
      "capabilities":{capability:{
        "class":"execution","providers":[{"id":provider,"status":"ADOPT","health":"runtime-check",
          "cost_class":"included","scope":"platform-durable","fallback":[]}],
        "generated_by":"durable-capability-adoption","promotion_state":"ADOPT",
        "selected_adapter":adapter,"adoption_id":adoption_id,"automatic_external_spend_eur":0
      }},
      "providers":{},"adapters":{},
      "adoptions":{adoption_id:{
        "adoption_id":adoption_id,"status":"ADOPTED","project_id":"project-origin",
        "capability":capability,"provider":provider,"adapter":adapter,
        "provider_origin":"BASE_EXISTING","source_kind":"EXISTING_PROVIDER",
        "production_capable":False,"network_access":False,"credentials_required":False,
        "automatic_external_spend_eur":0
      }},
      "history":[],"automatic_external_spend_eur":0
    })

    source_db=td/"deltas.db"
    db=sqlite3.connect(source_db)
    db.execute("""CREATE TABLE deltas(
      delta_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_id TEXT NOT NULL,source_kind TEXT NOT NULL,
      deployment_id TEXT NOT NULL,sequence INTEGER NOT NULL,observed_at TEXT NOT NULL,
      anomaly_severity TEXT,digest TEXT NOT NULL,payload TEXT NOT NULL)""")
    db.commit();db.close()
    feedback_db=td/"feedback.db";branch_db=td/"branches.db";arch_db=td/"arch.db"
    conf_db=td/"confidence.db";conf_snap=td/"confidence.json"
    outbox=td/"outbox";state_root=td/"observer-state"

    counter=0
    def emit(project_id:str,outcome_kind:str,*,severity:str|None=None):
        nonlocal_counter=None
        global counter
        counter+=1
        root=td/f"proof-{counter:02d}-{project_id}-{outcome_kind.lower()}"
        root.mkdir(parents=True,exist_ok=True)
        evidence_refs=[f"project-control:{project_id}:{outcome_kind}:{counter}"]
        claims=root/"claims.json"
        save(claims,{
          "project_id":project_id,"capability":capability,"outcome":outcome_kind,
          "technology_watch_revalidated":True,"evidence_refs":evidence_refs
        })
        artifact_id="capability-project-outcome:"+capability
        task_id=f"v643-{project_id}-{outcome_kind.lower()}-{counter}"
        receipt,ledger=project_control_proof(root,project_id,task_id,claims,artifact_id)
        outcome=root/"outcome.json"
        value={
          "schema":"chacha.dev/capability-project-outcome/v1","project_id":project_id,
          "capability":capability,"adoption_id":adoption_id,"outcome":outcome_kind,
          "technology_watch_revalidated":True,"automatic_external_spend_eur":0,
          "evidence_refs":evidence_refs,"project_control_receipt":str(receipt),
          "project_control_ledger":str(ledger),"verified_task_id":task_id,
          "verified_artifact_id":artifact_id,"verified_claims_path":str(claims),
          "verified_claims_digest":sha256_file(claims)
        }
        if severity:value["severity"]=severity
        save(outcome,value)
        p=subprocess.run([
          sys.executable,str(BIN/"capability-trust-observer.py"),
          "--registry",str(durable),"--outcome",str(outcome),
          "--outbox-root",str(outbox),"--state-root",str(state_root)
        ],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        assert p.returncode==0,(p.stdout,p.stderr)
        result=json.loads(p.stdout.split("\nCHACHA_DEV_V643_",1)[0])
        assert result["project_control_committed_proof"] is True,result
        assert result["queued"] is True,result
        delta=load(Path(result["outbox"]))
        assert delta["lineage"]["components"][0]["kind"]=="capability",delta
        assert delta["lineage"]["components"][0]["component_id"]==capability,delta
        assert delta["lineage"]["components"][0]["version"]==adoption_id,delta
        return delta

    # A self-declared outcome without Project Control proof is blocked.
    bad=td/"bad-outcome.json"
    save(bad,{
      "schema":"chacha.dev/capability-project-outcome/v1","project_id":"bad-project",
      "capability":capability,"adoption_id":adoption_id,"outcome":"SUCCESS",
      "technology_watch_revalidated":True,"automatic_external_spend_eur":0,
      "evidence_refs":["self:declared"]
    })
    p=subprocess.run([
      sys.executable,str(BIN/"capability-trust-observer.py"),
      "--registry",str(durable),"--outcome",str(bad),
      "--outbox-root",str(outbox),"--state-root",str(state_root)
    ],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    assert p.returncode!=0,p.stdout+p.stderr
    assert "PROJECT_CONTROL_RECEIPT_REQUIRED" in (p.stdout+p.stderr),p.stdout+p.stderr

    # Project 1 success + replay of the same project: raw events=2, distinct successes=1.
    d1=emit("project-1","SUCCESS");add_delta(source_db,d1,"2026-09-24T00:01:00Z")
    d1r=emit("project-1","SUCCESS");add_delta(source_db,d1r,"2026-09-24T00:02:00Z")
    reconcile(source_db,feedback_db,branch_db,arch_db,td/"feedback-1.json")
    snap=confidence_snapshot(feedback_db,branch_db,arch_db,conf_db,conf_snap)
    item=next(x for x in snap["items"] if x["component_kind"]=="capability")
    assert item["state"]=="PROVISIONAL",item
    assert item["verified_success_count"]==1,item
    assert item["distinct_project_count"]==1,item
    assert item["project_distinct_counting"] is True,item

    # Project 2 remains provisional.
    d2=emit("project-2","SUCCESS");add_delta(source_db,d2,"2026-09-24T00:03:00Z")
    reconcile(source_db,feedback_db,branch_db,arch_db,td/"feedback-2.json")
    snap=confidence_snapshot(feedback_db,branch_db,arch_db,conf_db,conf_snap)
    item=next(x for x in snap["items"] if x["component_kind"]=="capability")
    assert item["state"]=="PROVISIONAL" and item["verified_success_count"]==2,item

    # Project 3 graduates to TRUSTED.
    d3=emit("project-3","SUCCESS");add_delta(source_db,d3,"2026-09-24T00:04:00Z")
    reconcile(source_db,feedback_db,branch_db,arch_db,td/"feedback-3.json")
    snap=confidence_snapshot(feedback_db,branch_db,arch_db,conf_db,conf_snap)
    item=next(x for x in snap["items"] if x["component_kind"]=="capability")
    assert item["state"]=="TRUSTED",item
    assert item["verified_success_count"]==3,item
    assert item["reuse_advisory_eligible"] is True,item

    merged_caps=td/"merged-trusted-caps.json";merged_providers=td/"merged-trusted-providers.json"
    p=subprocess.run([
      sys.executable,str(BIN/"durable-capability-registry.py"),"merge",
      "--base-capability-registry",str(CFG/"capability-registry.v1.json"),
      "--base-provider-registry",str(CFG/"provider-adapters.v1.json"),
      "--registry",str(durable),"--output-capabilities",str(merged_caps),
      "--output-providers",str(merged_providers),
      "--trust-snapshot",str(conf_snap),"--trust-policy",str(CFG/"capability-trust-graduation.v1.json")
    ],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    cap_entry=load(merged_caps)["capabilities"][capability]
    assert cap_entry["trust_state"]=="TRUSTED",cap_entry
    assert cap_entry["trust_is_advisory"] is True,cap_entry
    assert cap_entry["technology_revalidation_required"] is True,cap_entry

    # A critical incident from a new project immediately quarantines and removes reuse.
    di=emit("project-4","INCIDENT",severity="critical");add_delta(source_db,di,"2026-09-24T00:05:00Z")
    reconcile(source_db,feedback_db,branch_db,arch_db,td/"feedback-4.json")
    snap=confidence_snapshot(feedback_db,branch_db,arch_db,conf_db,conf_snap)
    item=next(x for x in snap["items"] if x["component_kind"]=="capability")
    assert item["state"]=="QUARANTINED" and item["reuse_advisory_eligible"] is False,item

    blocked_caps=td/"blocked-caps.json";blocked_providers=td/"blocked-providers.json"
    p=subprocess.run([
      sys.executable,str(BIN/"durable-capability-registry.py"),"merge",
      "--base-capability-registry",str(CFG/"capability-registry.v1.json"),
      "--base-provider-registry",str(CFG/"provider-adapters.v1.json"),
      "--registry",str(durable),"--output-capabilities",str(blocked_caps),
      "--output-providers",str(blocked_providers),
      "--trust-snapshot",str(conf_snap),"--trust-policy",str(CFG/"capability-trust-graduation.v1.json")
    ],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    assert capability not in load(blocked_caps)["capabilities"],load(blocked_caps)
    assert "CAPABILITY_TRUST_BLOCKED:QUARANTINED" in p.stdout,p.stdout

    # Verified recovery alone does not re-enable reuse.
    dr=emit("project-4","RECOVERY",severity="critical");add_delta(source_db,dr,"2026-09-24T00:06:00Z")
    reconcile(source_db,feedback_db,branch_db,arch_db,td/"feedback-5.json")
    snap=confidence_snapshot(feedback_db,branch_db,arch_db,conf_db,conf_snap)
    item=next(x for x in snap["items"] if x["component_kind"]=="capability")
    assert item["state"]=="RECOVERY_CANDIDATE",item

    # Two fresh distinct projects after recovery move only to PROVISIONAL, never directly TRUSTED.
    d5=emit("project-5","SUCCESS");add_delta(source_db,d5,"2026-09-24T00:07:00Z")
    d6=emit("project-6","SUCCESS");add_delta(source_db,d6,"2026-09-24T00:08:00Z")
    reconcile(source_db,feedback_db,branch_db,arch_db,td/"feedback-6.json")
    snap=confidence_snapshot(feedback_db,branch_db,arch_db,conf_db,conf_snap)
    item=next(x for x in snap["items"] if x["component_kind"]=="capability")
    assert item["state"]=="PROVISIONAL",item
    assert item["fresh_success_projects_after_recovery"]==2,item
    assert item["reuse_advisory_eligible"] is True,item

    recovered_caps=td/"recovered-caps.json";recovered_providers=td/"recovered-providers.json"
    p=subprocess.run([
      sys.executable,str(BIN/"durable-capability-registry.py"),"merge",
      "--base-capability-registry",str(CFG/"capability-registry.v1.json"),
      "--base-provider-registry",str(CFG/"provider-adapters.v1.json"),
      "--registry",str(durable),"--output-capabilities",str(recovered_caps),
      "--output-providers",str(recovered_providers),
      "--trust-snapshot",str(conf_snap),"--trust-policy",str(CFG/"capability-trust-graduation.v1.json")
    ],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    recovered=load(recovered_caps)["capabilities"][capability]
    assert recovered["trust_state"]=="PROVISIONAL",recovered
    assert recovered["trust_is_advisory"] is True,recovered

policy=load(CFG/"capability-trust-graduation.v1.json")
assert policy["thresholds"]["trusted_min_distinct_success_projects"]==3
assert policy["evidence"]["replay_same_project_does_not_increase_success_count"] is True
assert policy["reuse"]["technology_revalidation_required"] is True
assert policy["reuse"]["architecture_council_final_authority"] is True
assert policy["reuse"]["guardian_authority_preserved"] is True
assert policy["reuse"]["sentinel_authority_preserved"] is True
assert policy["privilege"]["trust_never_grants_production_permission"] is True
assert policy["privilege"]["protected_human_boundaries_preserved"] is True
assert policy["economics"]["automatic_external_spend_eur"]==0

orch=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert '"--trust-policy",cfg/"capability-trust-graduation.v1.json"' in orch
assert '"--trust-snapshot",capability_trust_snapshot' in orch
assert '"capability_trust_project_distinct":True' in orch
assert '"capability_trust_does_not_escalate_permissions":True' in orch

print("CHACHA_DEV_V643_PROJECT_CONTROL_VERIFIED_OBSERVATION=PASS")
print("CHACHA_DEV_V643_DISTINCT_PROJECT_COUNTING=PASS")
print("CHACHA_DEV_V643_REPLAY_TRUST_INFLATION=NO")
print("CHACHA_DEV_V643_THREE_DISTINCT_PROJECTS_TRUSTED=PASS")
print("CHACHA_DEV_V643_CRITICAL_INCIDENT_QUARANTINE=PASS")
print("CHACHA_DEV_V643_NEGATIVE_TRUST_REMOVED_FROM_REUSE=PASS")
print("CHACHA_DEV_V643_VERIFIED_RECOVERY_FRESH_EVIDENCE_REQUIRED=PASS")
print("CHACHA_DEV_V643_RECOVERY_RETURNS_PROVISIONAL_NOT_TRUSTED=PASS")
print("CHACHA_DEV_V643_TRUST_PERMISSION_ESCALATION=NO")
print("CHACHA_DEV_V643_TECHNOLOGY_WATCH_REVALIDATION_REQUIRED=YES")
print("CHACHA_DEV_V643_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V643_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
