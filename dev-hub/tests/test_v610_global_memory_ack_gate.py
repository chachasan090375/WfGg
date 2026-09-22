#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, sqlite3, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PULLER=ROOT/"dev-hub/bin/central-learning-relay-puller.py"
INDEXER=ROOT/"dev-hub/bin/global-project-memory-index.py"
INSTALLER=ROOT/"dev-hub/bin/install-central-learning-relay-puller.sh"
SERVICE=ROOT/"dev-hub/systemd/chacha-dev-central-learning-relay-pull.service"

spec=importlib.util.spec_from_file_location("puller",PULLER)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

with tempfile.TemporaryDirectory(prefix="chacha-v610-index-") as td:
    td=Path(td); exp=td/"experience.db"; delta=td/"learning.db"; out=td/"global.json"
    e=sqlite3.connect(exp)
    e.execute("""CREATE TABLE experience(
      digest TEXT PRIMARY KEY, observed_at TEXT NOT NULL, project_id TEXT NOT NULL,
      learner TEXT NOT NULL, intent_signature TEXT, context_signature TEXT,
      outcome TEXT, acceptance_score REAL, external_spend_eur REAL,
      latency_ms REAL, memory_mb REAL, payload TEXT NOT NULL)""")
    e.execute("INSERT INTO experience VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
              ("x","2026-09-22T16:00:00Z","generic-app","core-orchestrator","","","PASS",1,0,1,1,"{}"))
    e.commit();e.close()
    d=sqlite3.connect(delta)
    d.execute("""CREATE TABLE deltas(
      delta_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
      source_kind TEXT NOT NULL, deployment_id TEXT NOT NULL, sequence INTEGER NOT NULL,
      observed_at TEXT NOT NULL, anomaly_severity TEXT, digest TEXT NOT NULL, payload TEXT NOT NULL)""")
    d.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",
              ("delta-1","generic-app","embedded-agent","embedded-application-agent","prod-1",1,
               "2026-09-22T16:01:00Z","high","d","{}"))
    d.commit();d.close()
    m.rebuild_global_index(INDEXER,exp,delta,out)
    assert out.is_file()
    import json
    x=json.load(open(out,encoding="utf-8"))
    assert x["projects"]["generic-app"]["learning_delta_count"]==1
    assert x["projects"]["generic-app"]["anomalies"]["high"]==1

src=PULLER.read_text(encoding="utf-8")
run=src[src.index("def run_once"):]
assert run.index("rebuild_global_index(indexer,experience_db,db,global_index)") < run.index('ack_url=relay_url.rstrip("/")+"/v1/central/ack"')
installer=INSTALLER.read_text(encoding="utf-8")
service=SERVICE.read_text(encoding="utf-8")
assert 'global-project-memory-index.py' in installer
assert '--global-indexer /opt/chacha-dev/learning-relay/current/global-project-memory-index.py' in service
assert '--global-index /opt/chacha-dev/runtime/knowledge/global-project-memory-index.json' in service

print("CHACHA_DEV_V610_GLOBAL_MEMORY_REBUILD=PASS")
print("CHACHA_DEV_V610_ACK_AFTER_NAS_AND_GLOBAL_INDEX=PASS")
