#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ING=ROOT/"dev-hub/bin/learning-delta-ingest.py"; IDX=ROOT/"dev-hub/bin/global-project-memory-index.py"; CLIENT=ROOT/"dev-hub/bin/learning-uplink-client.py"
LF=json.load(open(ROOT/"dev-hub/config/learning-fabric.v1.json")); P=json.load(open(ROOT/"dev-hub/config/production-learning-policy.v1.json"))
assert LF["learner_registration"]["required_for_every_learning_capable_component"] is True
assert LF["central_brain_uplink"]["incremental_only"] is True
assert LF["central_brain_uplink"]["reports_when_application_is_used_by_other_users"] is True
assert LF["anomaly_feedback_loop"]["enabled"] is True
assert P["remediation"]["auto_generate_candidate"] is True
with tempfile.TemporaryDirectory() as td:
    td=Path(td);db=td/"delta.db";exp=td/"exp.db";out=td/"index.json";delta=td/"delta.json";spool=td/"spool"
    x={"schema":"chacha.dev/learning-delta/v1","delta_id":"delta-0001","project_id":"app-a","source_id":"agent-reco","source_kind":"embedded-application-agent","deployment_id":"prod-eu-1","sequence":1,"observed_at":"2026-09-22T14:30:00Z","changes":[{"path":"strategy.cache_ttl","before":30,"after":45}],"anomaly":{"severity":"high","class":"latency-regression"},"evidence_refs":["metric://latency/p95"],"privacy":{"raw_user_content":False,"contains_secrets":False,"personal_data_class":"aggregated"}}
    delta.write_text(json.dumps(x))
    p=subprocess.run(["python3",str(ING),"--db",str(db),"--delta",str(delta)],stdout=subprocess.PIPE,text=True,check=True);r=json.loads(p.stdout);assert r["remediation_candidate"] is True
    p=subprocess.run(["python3",str(ING),"--db",str(db),"--delta",str(delta)],stdout=subprocess.PIPE,text=True,check=True);assert json.loads(p.stdout)["status"]=="DEDUPLICATED"
    import sqlite3
    d=sqlite3.connect(exp);d.execute("CREATE TABLE experience(digest TEXT, observed_at TEXT, project_id TEXT, learner TEXT, intent_signature TEXT, context_signature TEXT, outcome TEXT, acceptance_score REAL, external_spend_eur REAL, latency_ms REAL, memory_mb REAL, payload TEXT)");d.execute("INSERT INTO experience VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",("x","2026-09-22T14:00:00Z","app-a","core-orchestrator","","","PASS",1,0,1,1,"{}"));d.commit();d.close()
    subprocess.run(["python3",str(IDX),"--experience-db",str(exp),"--delta-db",str(db),"--output",str(out)],check=True)
    idx=json.load(open(out));assert idx["projects"]["app-a"]["learning_delta_count"]==1;assert idx["projects"]["app-a"]["anomalies"]["high"]==1
    env=os.environ.copy();env["CHACHA_LEARNING_UPLINK_SECRET"]="test-secret"
    subprocess.run(["python3",str(CLIENT),"emit","--delta",str(delta),"--spool",str(spool),"--key-id","deploy-a"],env=env,check=True)
    packet=json.load(open(next(spool.glob("*.json"))));assert packet["delta"]["changes"]==x["changes"];assert "signature" in packet
print("CHACHA_DEV_V66_UNIVERSAL_LEARNER_UPLINK=PASS")
print("CHACHA_DEV_V66_INCREMENTAL_REMOTE_LEARNING=PASS")
print("CHACHA_DEV_V66_GLOBAL_PROJECT_MEMORY_INDEX=PASS")
print("CHACHA_DEV_V66_ANOMALY_REMEDIATION_FEEDBACK=PASS")
