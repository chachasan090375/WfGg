#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sqlite3,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def mod(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

feedback=mod("plf",BIN/"production-lineage-feedback.py")
ul=mod("ulrt",BIN/"universal_learning_runtime.py")

with tempfile.TemporaryDirectory(prefix="v624-lineage-") as td:
    td=Path(td)
    branch_db=td/"branches.db";arch_db=td/"arch.db";source_db=td/"deltas.db";fb_db=td/"feedback.db"

    # Register reusable branch and architecture in isolated registries.
    branch_record={
      "schema":"chacha.dev/reusable-branch-record/v2","branch_id":"generic:graphics:primary","version":"arch-v1",
      "domain":"graphics","capabilities":["image-generation"],"architecture":{"pattern":"pilot"},
      "qualification_status":"PASS","state":"ADOPT","technology_revalidated_at":"2026-09-23T00:00:00Z",
      "technology_snapshot_digest":"tw1","external_spend_eur":0,"quality_score":99,
      "success_count":5,"failure_count":0,"incident_count":0,"increment_existing":False
    }
    bfile=td/"branch.json";bfile.write_text(json.dumps(branch_record),encoding="utf-8")
    subprocess.check_call([sys.executable,str(BIN/"reusable-branch-registry.py"),"--db",str(branch_db),"register","--record",str(bfile)],
                          stdout=subprocess.DEVNULL)

    arch_record={
      "schema":"chacha.dev/reusable-architecture-record/v1","architecture_id":"architecture-pilot","version":"system-v1",
      "functional_signature":"sig-pilot","components":{"packages":[]},"qualification_status":"PASS","state":"ADOPT",
      "technology_revalidated_at":"2026-09-23T00:00:00Z","technology_snapshot_digest":"tw1",
      "external_spend_eur":0,"quality_score":99,"success_count":5,"failure_count":0,"incident_count":0,
      "increment_existing":False
    }
    afile=td/"arch.json";afile.write_text(json.dumps(arch_record),encoding="utf-8")
    subprocess.check_call([sys.executable,str(BIN/"reusable-architecture-registry.py"),"--db",str(arch_db),"register","--record",str(afile)],
                          stdout=subprocess.DEVNULL)

    # Learning producer must preserve exact lineage.
    lineage={"schema":"chacha.dev/component-lineage/v1","components":[
      {"kind":"branch","component_id":"generic:graphics:primary","version":"arch-v1"},
      {"kind":"architecture","component_id":"architecture-pilot","version":"system-v1"},
      {"kind":"agent","component_id":"graphics-agent","version":"agent-v7"}
    ]}
    state_root=td/"state";outbox=td/"outbox"
    obs=ul.observe(project_id="p1",source_id="prod-agent",source_kind="embedded-application-agent",
                   deployment_id="deploy-1",state={"healthy":False},
                   anomaly={"severity":"critical","class":"render-regression"},
                   lineage=lineage,outbox_root=outbox,state_root=state_root)
    assert obs["status"]=="QUEUED",obs
    delta=json.load(open(obs["outbox"],encoding="utf-8"))
    assert delta["lineage"]==lineage,delta

    # Central source DB payload contains the same delta.
    db=sqlite3.connect(source_db)
    db.execute("""CREATE TABLE deltas(
      delta_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_id TEXT NOT NULL,source_kind TEXT NOT NULL,
      deployment_id TEXT NOT NULL,sequence INTEGER NOT NULL,observed_at TEXT NOT NULL,
      anomaly_severity TEXT,digest TEXT NOT NULL,payload TEXT NOT NULL)""")
    db.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",
      (delta["delta_id"],delta["project_id"],delta["source_id"],delta["source_kind"],delta["deployment_id"],
       delta["sequence"],delta["observed_at"],"critical","x",json.dumps(delta)))
    db.commit();db.close()

    class A:pass
    a=A();a.policy=CFG/"production-lineage-feedback.v1.json";a.source_db=source_db;a.db=fb_db
    a.branch_db=branch_db;a.architecture_db=arch_db;a.output=td/"out.json";a.nas=False
    out=feedback.reconcile(a)
    assert out["reuse_updates"]==2,out
    assert out["lineage_components"]==3,out
    assert out["verified_recovery_auto_adopt"] is False,out
    assert out["technology_revalidation_required"] is True,out

    b=sqlite3.connect(branch_db).execute("SELECT state,success_count,failure_count,incident_count FROM reusable_branches").fetchone()
    assert b==("QUARANTINED",5,1,1),b
    ar=sqlite3.connect(arch_db).execute("SELECT state,success_count,failure_count,incident_count FROM reusable_architectures").fetchone()
    assert ar==("QUARANTINED",5,1,1),ar

    # Reprocessing is idempotent: counters MUST NOT increment twice.
    out2=feedback.reconcile(a)
    b2=sqlite3.connect(branch_db).execute("SELECT state,success_count,failure_count,incident_count FROM reusable_branches").fetchone()
    ar2=sqlite3.connect(arch_db).execute("SELECT state,success_count,failure_count,incident_count FROM reusable_architectures").fetchone()
    assert b2==b and ar2==ar,(b,b2,ar,ar2)
    assert out2["reuse_updates"]==0,out2
    assert out2["deduplicated"]>=3,out2

    # Verified recovery is a candidate only, never automatic re-adoption.
    recovery={**delta,"delta_id":"ld-recovery-00000001","sequence":2,"observed_at":"2026-09-23T01:00:00Z",
              "anomaly":{"severity":"critical","class":"render-regression","status":"resolved","resolution_verified":True}}
    db=sqlite3.connect(source_db)
    db.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",
      (recovery["delta_id"],recovery["project_id"],recovery["source_id"],recovery["source_kind"],recovery["deployment_id"],
       recovery["sequence"],recovery["observed_at"],"critical","y",json.dumps(recovery)))
    db.commit();db.close()
    out3=feedback.reconcile(a)
    b3=sqlite3.connect(branch_db).execute("SELECT state,failure_count,incident_count FROM reusable_branches").fetchone()
    ar3=sqlite3.connect(arch_db).execute("SELECT state,failure_count,incident_count FROM reusable_architectures").fetchone()
    assert b3==("RECOVERY_CANDIDATE",1,1),b3
    assert ar3==("RECOVERY_CANDIDATE",1,1),ar3
    assert out3["verified_recovery_auto_adopt"] is False,out3

    # Missing lineage still belongs in central learning, but cannot mutate reusable assets.
    no_lineage={k:v for k,v in delta.items() if k!="lineage"}
    no_lineage["delta_id"]="ld-no-lineage-0000001";no_lineage["sequence"]=3
    db=sqlite3.connect(source_db)
    db.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",
      (no_lineage["delta_id"],no_lineage["project_id"],no_lineage["source_id"],no_lineage["source_kind"],no_lineage["deployment_id"],
       no_lineage["sequence"],"2026-09-23T01:05:00Z","critical","z",json.dumps(no_lineage)))
    db.commit();db.close()
    out4=feedback.reconcile(a)
    assert out4["missing_lineage"]>=1,out4
    b4=sqlite3.connect(branch_db).execute("SELECT failure_count,incident_count FROM reusable_branches").fetchone()
    assert b4==(1,1),b4

    rep=sqlite3.connect(fb_db).execute("""SELECT state,critical_anomaly_count,verified_recovery_count
      FROM component_reputation WHERE component_kind='agent' AND component_id='graphics-agent' AND version='agent-v7'""").fetchone()
    assert rep==("RECOVERY_CANDIDATE",1,1),rep

    # Invalid lineage is rejected at producer boundary.
    try:
        ul.observe(project_id="p",source_id="s",source_kind="agent",deployment_id="d",state={"x":1},
                   lineage={"schema":"bad","components":[]},outbox_root=td/"bad-o",state_root=td/"bad-s")
        raise AssertionError("invalid lineage accepted")
    except ValueError as exc:
        assert "LINEAGE_SCHEMA_INVALID" in str(exc),exc

policy=json.load(open(CFG/"production-lineage-feedback.v1.json",encoding="utf-8"))
assert policy["exact_lineage_required_for_reuse_mutation"] is True
assert policy["missing_lineage_still_learns_centrally"] is True
assert policy["branch_and_architecture_feedback"]["verified_recovery_does_not_auto_adopt"] is True
assert policy["branch_and_architecture_feedback"]["technology_revalidation_required"] is True
assert policy["all_components"]["positive_success_inferred_from_absence_of_anomaly"] is False
assert policy["safety"]["guardian_governed"] is True
assert policy["economics"]["automatic_external_spend_eur"]==0

univ=json.load(open(CFG/"universal-learning.v1.json",encoding="utf-8"))
assert univ["requirements"]["exact_lineage_required_for_reuse_feedback"] is True
assert univ["requirements"]["missing_lineage_must_not_mutate_reuse_registry"] is True
assert univ["remote_app_contract"]["lineage_manifest_required_for_reuse_feedback"] is True

contracts=json.load(open(CFG/"guardian-role-contracts.v1.json",encoding="utf-8"))
assert any(x["contract_id"]=="role:production-lineage-feedback" for x in contracts["contracts"])
coverage=json.load(open(CFG/"guardian-coverage-manifest.v1.json",encoding="utf-8"))
assert any(x["component_id"]=="production-lineage-feedback" for x in coverage["expected_components"])

wrapper=(BIN/"guardian-governed-production-lineage-feedback.py").read_text(encoding="utf-8")
assert '"subject_role":"production-lineage-feedback"' in wrapper
assert '"action":"INVOKE_COMPONENT"' in wrapper
assert "direct_application_mutation" in wrapper

print("CHACHA_DEV_V624_LINEAGE_IN_LEARNING_DELTA=PASS")
print("CHACHA_DEV_V624_EXACT_BRANCH_FEEDBACK=PASS")
print("CHACHA_DEV_V624_EXACT_ARCHITECTURE_FEEDBACK=PASS")
print("CHACHA_DEV_V624_ALL_COMPONENT_REPUTATION=PASS")
print("CHACHA_DEV_V624_CRITICAL_ANOMALY_QUARANTINE=PASS")
print("CHACHA_DEV_V624_FEEDBACK_IDEMPOTENCY=PASS")
print("CHACHA_DEV_V624_VERIFIED_RECOVERY_NOT_AUTO_ADOPT=PASS")
print("CHACHA_DEV_V624_MISSING_LINEAGE_NO_REUSE_MUTATION=PASS")
print("CHACHA_DEV_V624_GUARDIAN_GOVERNED=PASS")
print("CHACHA_DEV_V624_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
