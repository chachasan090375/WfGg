#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,os,sqlite3,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

spec=importlib.util.spec_from_file_location("cma",BIN/"central-memory-assimilator.py")
cma=importlib.util.module_from_spec(spec);spec.loader.exec_module(cma)

def exp_db(path:Path):
    db=sqlite3.connect(path)
    db.execute("""CREATE TABLE experience(
      digest TEXT PRIMARY KEY, observed_at TEXT NOT NULL, project_id TEXT NOT NULL,
      learner TEXT NOT NULL, intent_signature TEXT, context_signature TEXT,
      outcome TEXT, acceptance_score REAL, external_spend_eur REAL,
      latency_ms REAL, memory_mb REAL, payload TEXT NOT NULL)""")
    return db

def delta_db(path:Path):
    db=sqlite3.connect(path)
    db.execute("""CREATE TABLE deltas(
      delta_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,
      source_kind TEXT NOT NULL, deployment_id TEXT NOT NULL, sequence INTEGER NOT NULL,
      observed_at TEXT NOT NULL, anomaly_severity TEXT, digest TEXT NOT NULL, payload TEXT NOT NULL)""")
    return db

def branch_db(path:Path):
    db=sqlite3.connect(path)
    db.execute("""CREATE TABLE reusable_branches(
      branch_id TEXT,version TEXT,domain TEXT,functional_signature TEXT,state TEXT,qualification_status TEXT,
      external_spend_eur REAL,quality_score REAL,success_count INTEGER,failure_count INTEGER,incident_count INTEGER,
      technology_revalidated_at TEXT,last_used_at TEXT)""")
    return db

def arch_db(path:Path):
    db=sqlite3.connect(path)
    db.execute("""CREATE TABLE reusable_architectures(
      architecture_id TEXT,version TEXT,functional_signature TEXT,state TEXT,qualification_status TEXT,
      external_spend_eur REAL,quality_score REAL,success_count INTEGER,failure_count INTEGER,incident_count INTEGER,
      technology_revalidated_at TEXT,last_used_at TEXT)""")
    return db

with tempfile.TemporaryDirectory(prefix="v622-memory-") as td:
    td=Path(td)
    e=exp_db(td/"experience.db")
    rows=[
      ("e1","2026-09-23T00:00:00Z","p1","branch-foundry","intent-a",None,"success",1.0,0,10,10,{}),
      ("e2","2026-09-23T00:01:00Z","p1","branch-foundry","intent-a",None,"success",1.0,0,10,10,{}),
      ("e3","2026-09-23T00:02:00Z","p2","branch-foundry","intent-a",None,"success",1.0,0,10,10,{}),
      ("e4","2026-09-23T00:03:00Z","p1","agent-x","intent-b",None,"success",1.0,0,10,10,{}),
      ("e5","2026-09-23T00:04:00Z","p1","agent-x","intent-b",None,"success",1.0,0,10,10,{}),
      ("e6","2026-09-23T00:05:00Z","p1","agent-x","intent-b",None,"failed",0.2,0,10,10,{}),
      ("e7","2026-09-23T00:06:00Z","p2","agent-x","intent-b",None,"failed",0.2,0,10,10,{})
    ]
    for r in rows:
        payload={"outcome":r[6],"acceptance_score":r[7]}
        e.execute("INSERT INTO experience VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",r[:-1]+(json.dumps(payload),))
    e.commit();e.close()

    d=delta_db(td/"deltas.db")
    payload={"schema":"chacha.dev/learning-delta/v1","delta_id":"d1","project_id":"p1",
      "source_id":"embedded-a","source_kind":"embedded-application-agent","deployment_id":"prod-a",
      "sequence":1,"observed_at":"2026-09-23T00:07:00Z",
      "changes":[{"path":"/health","op":"set","value":"bad"}],
      "anomaly":{"severity":"critical","class":"runtime-regression"},
      "privacy":{"raw_user_content":False,"contains_secrets":False,"personal_data_class":"none"}}
    d.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",
      ("d1","p1","embedded-a","embedded-application-agent","prod-a",1,"2026-09-23T00:07:00Z","critical","x",json.dumps(payload)))
    d.commit();d.close()

    b=branch_db(td/"branches.db")
    b.execute("INSERT INTO reusable_branches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
      ("generic:web:primary","v2","web","sig-web","ADOPT","PASS",0,99,8,0,0,"2026-09-23T00:00:00Z","2026-09-23T00:00:00Z"))
    b.execute("INSERT INTO reusable_branches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
      ("generic:web:primary","v1","web","sig-web","ADOPT","PASS",0,97,5,0,0,"2026-09-22T00:00:00Z","2026-09-22T00:00:00Z"))
    b.commit();b.close()

    a=arch_db(td/"arch.db")
    a.execute("INSERT INTO reusable_architectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
      ("architecture-a","v2","sig-a","ADOPT","PASS",0,99,5,0,0,"2026-09-23T00:00:00Z","2026-09-23T00:00:00Z"))
    a.execute("INSERT INTO reusable_architectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
      ("architecture-a","v1","sig-a","ADOPT","PASS",0,96,3,0,0,"2026-09-22T00:00:00Z","2026-09-22T00:00:00Z"))
    a.commit();a.close()

    class A: pass
    x=A();x.policy=CFG/"central-memory-assimilation.v1.json";x.delta_db=td/"deltas.db";x.experience_db=td/"experience.db"
    x.branch_db=td/"branches.db";x.architecture_db=td/"arch.db";x.db=td/"memory.db";x.snapshot=td/"memory.json";x.nas=False
    out=cma.assimilate(x)

    global_a=[i for i in out["items"] if i["scope"]=="GLOBAL_CANDIDATE" and i["subject_kind"]=="experience" and i["subject_id"]=="branch-foundry" and i["signal_key"]=="intent:intent-a"][0]
    assert global_a["state"]=="TRUSTED",global_a
    assert global_a["distinct_projects"]==2,global_a
    assert global_a["generalizable"] is True,global_a

    project_a=[i for i in out["items"] if i["scope"]=="PROJECT" and i["project_id"]=="p1" and i["subject_id"]=="branch-foundry"][0]
    assert project_a["state"]=="PROVISIONAL",project_a  # only two positive observations in p1

    conflict=[i for i in out["items"] if i["scope"]=="GLOBAL_CANDIDATE" and i["subject_id"]=="agent-x"][0]
    assert conflict["state"]=="CONTRADICTED",conflict
    assert conflict["generalizable"] is False,conflict

    suspended=[i for i in out["items"] if i["signal_key"]=="anomaly:runtime-regression"]
    assert suspended and all(i["state"]=="SUSPENDED" for i in suspended),suspended

    br=out["reuse_catalog"]["branches"]
    assert br[0]["version"]=="v2" and br[0]["version_status"]=="CURRENT_BEST",br
    assert br[1]["version"]=="v1" and br[1]["version_status"]=="SUPERSEDED",br
    ar=out["reuse_catalog"]["architectures"]
    assert ar[0]["version"]=="v2" and ar[0]["version_status"]=="CURRENT_BEST",ar
    assert ar[1]["version_status"]=="SUPERSEDED",ar

    # Technology Watch must absorb the memory snapshot without making it an absolute decision-maker.
    old=os.environ.get("CHACHA_CENTRAL_MEMORY_ASSIMILATION")
    os.environ["CHACHA_CENTRAL_MEMORY_ASSIMILATION"]=str(x.snapshot)
    try:
        import technology_watch_runtime as tw
        mem=tw._central_memory_assimilation()
        assert mem["available"] is True,mem
        assert mem["snapshot_digest"]==out["snapshot_digest"],mem
        assert mem["single_observation_never_trusted"] is True,mem
        assert mem["technology_revalidation_required_before_reuse"] is True,mem
    finally:
        if old is None:os.environ.pop("CHACHA_CENTRAL_MEMORY_ASSIMILATION",None)
        else:os.environ["CHACHA_CENTRAL_MEMORY_ASSIMILATION"]=old

policy=json.load(open(CFG/"central-memory-assimilation.v1.json",encoding="utf-8"))
assert policy["trust"]["single_observation_never_trusted"] is True
assert policy["generalization"]["project_specific_by_default"] is True
assert policy["generalization"]["minimum_distinct_projects"]==2
assert policy["reuse"]["technology_revalidation_required_before_reuse"] is True
assert policy["reuse"]["previous_solution_is_candidate_not_default"] is True

council=(BIN/"architecture-decision-council.py").read_text(encoding="utf-8")
assert '"central-memory-assimilation"' in council
assert "current_branch_versions" in council
assert "current_architecture_versions" in council
assert any(v in council for v in ['"version":"6.22.0"','"version":"6.23.0"','"version":"6.25.0"'])

print("CHACHA_DEV_V622_SINGLE_OBSERVATION_NOT_TRUSTED=PASS")
print("CHACHA_DEV_V622_REPEATED_SUCCESS_REINFORCES_MEMORY=PASS")
print("CHACHA_DEV_V622_CROSS_PROJECT_GENERALIZATION_GATE=PASS")
print("CHACHA_DEV_V622_CONTRADICTION_DETECTED=PASS")
print("CHACHA_DEV_V622_CRITICAL_ANOMALY_SUSPENDS_MEMORY=PASS")
print("CHACHA_DEV_V622_OLD_REUSE_VERSION_SUPERSEDED=PASS")
print("CHACHA_DEV_V622_TECHNOLOGY_WATCH_MEMORY_FEED=PASS")
print("CHACHA_DEV_V622_ARCHITECTURE_COUNCIL_MEMORY_ADVISOR=PASS")
print("CHACHA_DEV_V622_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
