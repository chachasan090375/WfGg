#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"
spec=importlib.util.spec_from_file_location("progress_coordinator",BIN/"progress-coordinator.py")
assert spec and spec.loader
pc=importlib.util.module_from_spec(spec);spec.loader.exec_module(pc)
policy=pc.load(CFG/"progress-coordinator.v1.json");pc.validate_policy(policy)

with tempfile.TemporaryDirectory(prefix="progress-coordinator-") as raw:
    state=Path(raw)/"platform.json"
    a=pc.begin(policy,state,"chacha-dev-platform","ChaCha GPT","Démarrage")
    rid=a["run_id"];assert a["overall_percent"]==5 and a["stage"]=="QUEUED",a
    b=pc.update(policy,state,run_id=rid,stage="TRANSLATING",message="Traduction",
                module="functional-translator-satellite",module_state="RUNNING",module_percent=60)
    assert b["overall_percent"]==25,b
    assert b["modules"]["functional-translator-satellite"]["percent"]==60,b
    c=pc.update(policy,state,run_id=rid,stage="CENTRAL_ORCHESTRATION",message="Cerveau central",
                module="central-orchestrator",module_state="RUNNING",module_percent=40)
    assert c["overall_percent"]==55,c
    d=pc.update(policy,state,run_id=rid,stage="VALIDATING",message="Contrôles",
                module="guardian",module_state="RUNNING",module_percent=50)
    assert d["overall_percent"]==82,d
    e=pc.update(policy,state,run_id=rid,stage="FINALIZING",message="Finalisation",
                module="sentinel",module_state="RUNNING",module_percent=70)
    assert e["overall_percent"]==94,e
    f=pc.update(policy,state,run_id=rid,stage="COMPLETE",label="Terminé",message="Prêt",
                module="direct-operator-service",module_state="COMPLETE",module_percent=100)
    assert f["overall_percent"]==100 and f["state"]=="COMPLETE",f
    assert len(f["history"])>=6,f
    try:pc.update(policy,state,run_id=rid,stage="TRANSLATING")
    except RuntimeError as exc:assert "PROGRESS_NON_MONOTONIC" in str(exc),exc
    else:raise AssertionError("non-monotonic progress accepted")
    weak=json.loads(json.dumps(policy));weak["invariants"]["single_canonical_progress_source"]=False
    try:pc.validate_policy(weak)
    except RuntimeError as exc:assert "PROGRESS_POLICY_WEAKENED" in str(exc),exc
    else:raise AssertionError("weakened progress policy accepted")
print("CHACHA_DEV_PROGRESS_COORDINATOR=PASS")
print("CHACHA_DEV_PROGRESS_SINGLE_CANONICAL_SOURCE=YES")
print("CHACHA_DEV_PROGRESS_PERSISTENT_STATE=YES")
print("CHACHA_DEV_PROGRESS_MODULE_BREAKDOWN=YES")
print("CHACHA_DEV_PROGRESS_MONOTONIC=YES")
print("CHACHA_DEV_PROGRESS_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
