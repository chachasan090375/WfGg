#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

spec=importlib.util.spec_from_file_location("ul",BIN/"universal_learning_runtime.py")
ul=importlib.util.module_from_spec(spec);spec.loader.exec_module(ul)

with tempfile.TemporaryDirectory(prefix="v621-learning-") as td:
    td=Path(td);outbox=td/"outbox";state_root=td/"state";sent=td/"sent"
    a=ul.observe(project_id="p1",source_id="agent-1",source_kind="agent",deployment_id="d1",
                 state={"quality":1,"status":"ok"},outbox_root=outbox,state_root=state_root)
    assert a["status"]=="QUEUED" and a["change_count"]==2,a
    b=ul.observe(project_id="p1",source_id="agent-1",source_kind="agent",deployment_id="d1",
                 state={"quality":1,"status":"ok"},outbox_root=outbox,state_root=state_root)
    assert b["status"]=="NO_CHANGE",b
    c=ul.observe(project_id="p1",source_id="agent-1",source_kind="agent",deployment_id="d1",
                 state={"quality":2,"status":"ok"},outbox_root=outbox,state_root=state_root)
    assert c["status"]=="QUEUED" and c["change_count"]==1,c
    files=sorted(outbox.glob("ld-*.json"));assert len(files)==2,files
    second=json.load(open(files[-1],encoding="utf-8"))
    assert second["privacy"]["raw_user_content"] is False
    assert second["privacy"]["contains_secrets"] is False
    assert second["source_kind"]=="agent"
    assert len(second["changes"])==1

    fake=td/"fake-ingest.py"
    fake.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps({"status":"RECORDED","nas":{"status":"PERSISTED"}}))\n',encoding="utf-8")
    fake.chmod(0o755)
    p=subprocess.run(["python3",str(BIN/"universal-learning-producer.py"),"flush","--transport","local",
                      "--outbox",str(outbox),"--sent",str(sent),"--ingest",str(fake),"--db",str(td/"x.db")],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    flushed=json.loads(p.stdout);assert len(flushed["sent"])==2 and flushed["pending"]==0,flushed
    assert [x["sequence"] for x in flushed["sent"]]==[1,2],flushed
    assert flushed["ordering"]=="SOURCE_DEPLOYMENT_SEQUENCE_ASC",flushed

    # Regression: filenames are intentionally reverse-ordered versus sequence.
    ordered_outbox=td/"ordered-outbox";ordered_sent=td/"ordered-sent"
    ordered_outbox.mkdir();ordered_sent.mkdir()
    base={"schema":"chacha.dev/learning-delta/v1","project_id":"p2","source_id":"agent-order",
          "source_kind":"agent","deployment_id":"deploy-order","observed_at":"2026-09-22T20:00:00Z",
          "changes":[{"path":"/x","op":"set","value":1}],
          "privacy":{"raw_user_content":False,"contains_secrets":False,"personal_data_class":"none"}}
    (ordered_outbox/"ld-z-seq1.json").write_text(json.dumps({**base,"delta_id":"ld-z-seq1","sequence":1}),encoding="utf-8")
    (ordered_outbox/"ld-a-seq2.json").write_text(json.dumps({**base,"delta_id":"ld-a-seq2","sequence":2}),encoding="utf-8")
    p2=subprocess.run(["python3",str(BIN/"universal-learning-producer.py"),"flush","--transport","local",
                       "--outbox",str(ordered_outbox),"--sent",str(ordered_sent),"--ingest",str(fake),"--db",str(td/"y.db")],
                      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p2.returncode==0,(p2.stdout,p2.stderr)
    ordered=json.loads(p2.stdout)
    assert [x["sequence"] for x in ordered["sent"]]==[1,2],ordered

cfg=json.load(open(CFG/"universal-learning.v1.json",encoding="utf-8"))
assert cfg["requirements"]["incremental_deltas_only"] is True
assert cfg["requirements"]["durable_outbox"] is True
assert cfg["requirements"]["nas_authoritative"] is True
assert cfg["remote_app_contract"]["learning_continues_without_owner_session"] is True
assert cfg["remote_app_contract"]["private_key_origin_local_only"] is True
assert cfg["anomaly_feedback_loop"]["high_or_critical_to_guardian"] is True
assert cfg["anomaly_feedback_loop"]["production_mutation_directly_by_guardian"] is False

agent_cfg=json.load(open(CFG/"agent-foundry.v1.json",encoding="utf-8"))
assert agent_cfg["principles"]["every_created_agent_has_learning_uplink"] is True
assert "learning_uplink" in agent_cfg["required_agent_manifest"]

planner=(BIN/"agent-foundry-planner.py").read_text(encoding="utf-8")
assert '"learning_uplink"' in planner
assert '"incremental-deltas-only"' in planner

worker=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
for marker in [
  "/v1/learning-anomalies/report","PRODUCTION_ANOMALY_",
  "INVESTIGATE_REPLAN_PATCH_AND_VERIFY_PRODUCTION_ANOMALY",
  "production_learning_anomaly_bridge:true","production_anomaly_direct_mutation:false"
]: assert marker in worker,marker

client=(BIN/"guardian-client.py").read_text(encoding="utf-8")
assert "report-anomaly" in client
assert "/v1/learning-anomalies/report" in client

bridge=(BIN/"production-anomaly-guardian-bridge.py").read_text(encoding="utf-8")
assert "automatic_production_mutation_authorized" in bridge
assert "DIRECTIVE_ISSUED" in bridge

for path in [BIN/"run-controller.py",BIN/"autonomous-project-orchestrator.py",BIN/"technology-watch-service.py"]:
    src=path.read_text(encoding="utf-8")
    assert "universal_learning_runtime as ulr" in src,path
    assert "observe_platform" in src,path

coverage=json.load(open(CFG/"guardian-coverage-manifest.v1.json",encoding="utf-8"))
ids={x["component_id"] for x in coverage["expected_components"]}
assert "universal-learning-producer" in ids
assert "production-anomaly-guardian-bridge" in ids

print("CHACHA_DEV_V621_INCREMENTAL_CHANGE_DETECTION=PASS")
print("CHACHA_DEV_V621_NO_CHANGE_NO_DELTA=PASS")
print("CHACHA_DEV_V621_DURABLE_OUTBOX=PASS")
print("CHACHA_DEV_V621_AGENT_LEARNING_UPLINK_REQUIRED=PASS")
print("CHACHA_DEV_V621_PLATFORM_LEARNING_HOOKS=PASS")
print("CHACHA_DEV_V621_REMOTE_APP_BACKGROUND_LEARNING_CONTRACT=PASS")
print("CHACHA_DEV_V621_PRODUCTION_ANOMALY_TO_GUARDIAN=PASS")
print("CHACHA_DEV_V621_GUARDIAN_DIRECT_PRODUCTION_MUTATION=NO")
print("CHACHA_DEV_V621_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
