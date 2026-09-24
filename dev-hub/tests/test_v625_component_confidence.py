#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sqlite3,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))

def mod(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

ul=mod("ul_v625",BIN/"universal_learning_runtime.py")
plf=mod("plf_v625",BIN/"production-lineage-feedback.py")
conf=mod("conf_v625",BIN/"component-confidence-engine.py")
assim=mod("assim_v625",BIN/"central-memory-assimilator.py")
recall=mod("recall_v625",BIN/"central-memory-recall.py")

with tempfile.TemporaryDirectory(prefix="v625-confidence-") as td:
    td=Path(td)
    source_db=td/"deltas.db";fb_db=td/"feedback.db";branch_db=td/"branches.db";arch_db=td/"arch.db"
    conf_db=td/"confidence.db";conf_snap=td/"confidence.json"

    # Two versions make the Current Best exclusion test meaningful.
    branch_records=[
      {"schema":"chacha.dev/reusable-branch-record/v2","branch_id":"generic:graphics:primary","version":"v1",
       "domain":"graphics","capabilities":["image-generation"],"architecture":{"pattern":"v1"},
       "qualification_status":"PASS","state":"ADOPT","technology_revalidated_at":"2026-09-23T00:00:00Z",
       "technology_snapshot_digest":"tw1","external_spend_eur":0,"quality_score":99,
       "success_count":0,"failure_count":0,"incident_count":0,"increment_existing":False},
      {"schema":"chacha.dev/reusable-branch-record/v2","branch_id":"generic:graphics:primary","version":"v2",
       "domain":"graphics","capabilities":["image-generation"],"architecture":{"pattern":"v2"},
       "qualification_status":"PASS","state":"ADOPT","technology_revalidated_at":"2026-09-23T00:00:00Z",
       "technology_snapshot_digest":"tw2","external_spend_eur":0,"quality_score":95,
       "success_count":2,"failure_count":0,"incident_count":0,"increment_existing":False}
    ]
    for i,r in enumerate(branch_records):
        p=td/f"branch-{i}.json";p.write_text(json.dumps(r),encoding="utf-8")
        subprocess.check_call([sys.executable,str(BIN/"reusable-branch-registry.py"),"--db",str(branch_db),"register","--record",str(p)],stdout=subprocess.DEVNULL)

    arch_record={"schema":"chacha.dev/reusable-architecture-record/v1","architecture_id":"graphics-stack","version":"a1",
      "functional_signature":"graphics:image-generation","components":{"packages":[]},"qualification_status":"PASS","state":"ADOPT",
      "technology_revalidated_at":"2026-09-23T00:00:00Z","technology_snapshot_digest":"tw1",
      "external_spend_eur":0,"quality_score":98,"success_count":0,"failure_count":0,"incident_count":0,"increment_existing":False}
    p=td/"arch.json";p.write_text(json.dumps(arch_record),encoding="utf-8")
    subprocess.check_call([sys.executable,str(BIN/"reusable-architecture-registry.py"),"--db",str(arch_db),"register","--record",str(p)],stdout=subprocess.DEVNULL)

    # Central delta DB used by the real feedback reconciler.
    db=sqlite3.connect(source_db)
    db.execute("""CREATE TABLE deltas(
      delta_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_id TEXT NOT NULL,source_kind TEXT NOT NULL,
      deployment_id TEXT NOT NULL,sequence INTEGER NOT NULL,observed_at TEXT NOT NULL,
      anomaly_severity TEXT,digest TEXT NOT NULL,payload TEXT NOT NULL)""")
    db.commit();db.close()

    lineage={"schema":"chacha.dev/component-lineage/v1","components":[
      {"kind":"branch","component_id":"generic:graphics:primary","version":"v1"},
      {"kind":"architecture","component_id":"graphics-stack","version":"a1"},
      {"kind":"agent","component_id":"graphics-agent","version":"agent-7"}
    ]}
    evaluation={"schema":"chacha.dev/component-evaluation/v1","verified":True,"outcome":"PASS",
                "acceptance_score":1.0,"evidence_refs":["acceptance:pipeline"]}

    # Three explicit verified successes => TRUSTED. Mere silence never counts.
    outbox=td/"outbox";state_root=td/"state-root"
    deltas=[]
    for n in range(1,4):
        obs=ul.observe(project_id="p-confidence",source_id="graphics-runtime",source_kind="agent",
                       deployment_id="prod-1",state={"counter":n},lineage=lineage,evaluation=evaluation,
                       evidence_refs=[f"acceptance:{n}"],outbox_root=outbox,state_root=state_root)
        assert obs["status"]=="QUEUED",obs
        d=json.load(open(obs["outbox"],encoding="utf-8"))
        assert d["evaluation"]["verified"] is True,d
        assert d["lineage"]==lineage,d
        deltas.append(d)

    db=sqlite3.connect(source_db)
    for d in deltas:
        db.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",
          (d["delta_id"],d["project_id"],d["source_id"],d["source_kind"],d["deployment_id"],d["sequence"],
           d["observed_at"],None,"x"+str(d["sequence"]),json.dumps(d)))
    db.commit();db.close()

    class A:pass
    a=A();a.policy=CFG/"production-lineage-feedback.v1.json";a.source_db=source_db;a.db=fb_db
    a.branch_db=branch_db;a.architecture_db=arch_db;a.output=td/"feedback.json";a.nas=False
    rep=plf.reconcile(a)
    assert rep["reuse_updates"]==6,rep

    db=sqlite3.connect(fb_db)
    agent=db.execute("""SELECT verified_success_count,verified_failure_count,anomaly_count,state
      FROM component_reputation WHERE component_kind='agent' AND component_id='graphics-agent' AND version='agent-7'""").fetchone()
    assert agent==(3,0,0,"PROVISIONAL"),agent
    db.close()

    class C:pass
    ca=C();ca.policy=CFG/"component-confidence.v1.json";ca.feedback_db=fb_db;ca.branch_db=branch_db
    ca.architecture_db=arch_db;ca.db=conf_db;ca.snapshot=conf_snap;ca.nas=False
    snap=conf.build(ca)
    ix={(x["component_kind"],x["component_id"],x["version"]):x for x in snap["items"]}
    assert ix[("agent","graphics-agent","agent-7")]["state"]=="TRUSTED",ix
    assert ix[("branch","generic:graphics:primary","v1")]["state"]=="TRUSTED",ix
    assert ix[("architecture","graphics-stack","a1")]["state"]=="TRUSTED",ix
    assert ix[("agent","graphics-agent","agent-7")]["verified_success_count"]==3
    trusted_score=ix[("agent","graphics-agent","agent-7")]["confidence"]
    assert 0<trusted_score<=1,trusted_score

    # Critical production anomaly immediately quarantines exact versions.
    anomaly={"severity":"critical","class":"renderer-corruption"}
    obs=ul.observe(project_id="p-confidence",source_id="graphics-runtime",source_kind="agent",
                   deployment_id="prod-1",state={"counter":4},lineage=lineage,anomaly=anomaly,
                   outbox_root=outbox,state_root=state_root)
    d=json.load(open(obs["outbox"],encoding="utf-8"))
    db=sqlite3.connect(source_db)
    db.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",
      (d["delta_id"],d["project_id"],d["source_id"],d["source_kind"],d["deployment_id"],d["sequence"],
       d["observed_at"],"critical","critical",json.dumps(d)))
    db.commit();db.close()
    plf.reconcile(a);snap=conf.build(ca)
    ix={(x["component_kind"],x["component_id"],x["version"]):x for x in snap["items"]}
    for key in [("agent","graphics-agent","agent-7"),("branch","generic:graphics:primary","v1"),("architecture","graphics-stack","a1")]:
        assert ix[key]["state"]=="QUARANTINED",(key,ix[key])
        assert ix[key]["reuse_advisory_eligible"] is False,(key,ix[key])

    # A verified recovery is only a recovery candidate, never automatic readoption.
    recovery={"severity":"critical","class":"renderer-corruption","status":"resolved","resolution_verified":True}
    obs=ul.observe(project_id="p-confidence",source_id="graphics-runtime",source_kind="agent",
                   deployment_id="prod-1",state={"counter":5},lineage=lineage,anomaly=recovery,
                   outbox_root=outbox,state_root=state_root)
    d=json.load(open(obs["outbox"],encoding="utf-8"))
    db=sqlite3.connect(source_db)
    db.execute("INSERT INTO deltas VALUES(?,?,?,?,?,?,?,?,?,?)",
      (d["delta_id"],d["project_id"],d["source_id"],d["source_kind"],d["deployment_id"],d["sequence"],
       d["observed_at"],"critical","recovery",json.dumps(d)))
    db.commit();db.close()
    plf.reconcile(a);snap=conf.build(ca)
    ix={(x["component_kind"],x["component_id"],x["version"]):x for x in snap["items"]}
    assert ix[("branch","generic:graphics:primary","v1")]["state"]=="RECOVERY_CANDIDATE",ix
    assert ix[("branch","generic:graphics:primary","v1")]["reuse_advisory_eligible"] is False,ix

    # Central memory must not call the recovered/quarantined version CURRENT_BEST.
    ci={"available":True,"snapshot_digest":snap["snapshot_digest"],"generated_at":snap["generated_at"],
        "component_count":snap["component_count"],"trusted_count":snap["trusted_count"],
        "negative_state_count":snap["negative_state_count"],"items":snap["items"]}
    catalog=assim.reuse_catalog(branch_db,arch_db,ci)
    b1=next(x for x in catalog["branches"] if x["version"]=="v1")
    b2=next(x for x in catalog["branches"] if x["version"]=="v2")
    assert b1["version_status"]=="BLOCKED_BY_CONFIDENCE",b1
    assert b2["version_status"]=="CURRENT_BEST",b2

    # Recall has defense in depth even if a bad row were incorrectly marked CURRENT_BEST.
    recall_policy=json.load(open(CFG/"central-memory-recall.v1.json",encoding="utf-8"))
    bad={**b1,"version_status":"CURRENT_BEST"}
    assert recall.reuse_score(bad,{"graphics","image-generation"},{"graphics"},{"image-generation"},recall_policy)<0,bad

    # Evaluation-only event is legitimate and privacy-safe.
    obs2=ul.observe(project_id="p2",source_id="agent2",source_kind="agent",deployment_id="d2",
                    state={},lineage={"schema":"chacha.dev/component-lineage/v1","components":[
                      {"kind":"agent","component_id":"agent2","version":"1"}]},
                    evaluation=evaluation,outbox_root=td/"o2",state_root=td/"s2")
    d2=json.load(open(obs2["outbox"],encoding="utf-8"))
    assert d2["changes"][0]["path"]=="/evaluation",d2
    assert d2["privacy"]["raw_user_content"] is False,d2

policy=json.load(open(CFG/"component-confidence.v1.json",encoding="utf-8"))
assert policy["evidence"]["explicit_verified_success_required"] is True
assert policy["evidence"]["absence_of_anomaly_is_not_success"] is True
assert policy["reuse"]["technology_revalidation_required"] is True
assert policy["reuse"]["architecture_council_final_authority"] is True
assert policy["safety"]["no_automatic_re_adoption_after_recovery"] is True
assert policy["economics"]["automatic_external_spend_eur"]==0

council=(BIN/"architecture-decision-council.py").read_text(encoding="utf-8")
assert '"component-confidence"' in council
assert "MANDATORY=" in council
worker=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
assert '"component_confidence"' in worker
assert "component_confidence_evidence_required:true" in worker
contracts=json.load(open(CFG/"guardian-role-contracts.v1.json",encoding="utf-8"))
assert any(x["contract_id"]=="role:component-confidence-engine" for x in contracts["contracts"])
cc=next(x for x in contracts["contracts"] if x["contract_id"]=="role:architecture-decision-council")
assert "component_confidence" in cc["required_evidence"]
coverage=json.load(open(CFG/"guardian-coverage-manifest.v1.json",encoding="utf-8"))
assert any(x["component_id"]=="component-confidence-engine" for x in coverage["expected_components"])

print("CHACHA_DEV_V625_EXPLICIT_VERIFIED_SUCCESS=PASS")
print("CHACHA_DEV_V625_THREE_SUCCESS_TRUSTED=PASS")
print("CHACHA_DEV_V625_CRITICAL_ANOMALY_QUARANTINE=PASS")
print("CHACHA_DEV_V625_RECOVERY_NOT_AUTO_READOPT=PASS")
print("CHACHA_DEV_V625_NEGATIVE_CONFIDENCE_EXCLUDED_FROM_CURRENT_BEST=PASS")
print("CHACHA_DEV_V625_RECALL_DEFENSE_IN_DEPTH=PASS")
print("CHACHA_DEV_V625_GUARDIAN_COMPONENT_CONFIDENCE_GATE=PASS")
print("CHACHA_DEV_V625_TECHNOLOGY_REVALIDATION_REMAINS_REQUIRED=PASS")
print("CHACHA_DEV_V625_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
