#!/usr/bin/env python3
import importlib.util,json,tempfile,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

direct=loadmod("targeted_recovery_direct",ROOT/"dev-hub/bin/direct-operator-service.py")
request_id="dor-0123456789abcdef0123456789abcdef"
with tempfile.TemporaryDirectory(prefix="targeted-platform-recovery-") as raw:
    rt=Path(raw);(rt/"responses").mkdir(parents=True)
    prior={"schema":"chacha.dev/human-interface-response/v1","request_id":request_id,"project_id":"chacha-dev-platform","status":"BLOCKED","next_action":"ADAPTER_ENABLEMENT_REQUIRED"}
    (rt/"responses"/(request_id+".json")).write_text(json.dumps(prior)+"\n")
    (rt/"requests"/request_id).mkdir(parents=True)
    (rt/"requests"/request_id/"intent.json").write_text(json.dumps({"operator_identity":"owner@example.test"})+"\n")
    text=f"Réparer le blocage ADAPTER_ENABLEMENT_REQUIRED puis reprendre {request_id} sans reconstruire ce qui est PASS."
    assert direct.targeted_platform_recovery(text,"chacha-dev-platform",rt)==request_id
    assert direct.targeted_platform_recovery(text,"chacha-dev-platform",rt,"owner@example.test")==request_id
    assert direct.targeted_platform_recovery(text,"chacha-dev-platform",rt,"other@example.test") is None
    assert direct.targeted_platform_recovery(f"Fais un rapport sur {request_id}","chacha-dev-platform",rt) is None
    assert direct.targeted_platform_recovery(text,"wfgg",rt) is None
    assert direct.targeted_platform_recovery("Réparer dor-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","chacha-dev-platform",rt) is None


central=loadmod("targeted_recovery_central",ROOT/"dev-hub/bin/central-interface-controller.py")
with tempfile.TemporaryDirectory(prefix="targeted-central-recovery-") as raw:
    rt=Path(raw);(rt/"direct-operator/responses").mkdir(parents=True)
    request_id="dor-fedcba9876543210fedcba9876543210"
    prior={"schema":"chacha.dev/human-interface-response/v1","request_id":request_id,"project_id":"chacha-dev-platform","status":"BLOCKED","next_action":"ADAPTER_ENABLEMENT_REQUIRED"}
    (rt/"direct-operator/responses"/(request_id+".json")).write_text(json.dumps(prior)+"\n")
    intent=rt/"intent.json"
    intent.write_text(json.dumps({"schema":"chacha.dev/human-interface-intent/v1","request_id":"dor-11111111111111111111111111111111","project_id":"chacha-dev-platform","target_scope":"PLATFORM","user_text":f"Reprendre {request_id} après le blocage ADAPTER_ENABLEMENT_REQUIRED"})+"\n")
    called={"continue":False,"orchestrate":False}
    def fake_continue(a):
        called["continue"]=True
        assert a.prior_response.name==request_id+".json"
        return {"schema":"chacha.dev/central-interface-receipt/v1","status":"BLOCKED","next_action":"ADAPTER_ENABLEMENT_REQUIRED","project_id":"chacha-dev-platform","decision":{},"evidence_refs":[],"brain_decision_obtained":True}
    def forbidden_orchestrate(*a,**k):
        called["orchestrate"]=True
        raise AssertionError("generic bootstrap must not run")
    central.handle_continue=fake_continue;central.orchestrate=forbidden_orchestrate
    args=type("A",(),{})();args.intent=intent;args.runtime_root=rt;args.repo_root=ROOT;args.orchestrator=ROOT/"missing";args.output_dir=rt/"out"
    got=central.handle_instruction(args)
    assert called["continue"] is True and called["orchestrate"] is False
    proof=got["decision"]["targeted_platform_recovery"]
    assert proof["target_request_id"]==request_id and proof["generic_bootstrap_replayed"] is False

src=(ROOT/"dev-hub/bin/direct-operator-service.py").read_text(encoding="utf-8")
assert 'elif command=="INSTRUCTION" and recovery_target:' in src
assert '"generic_bootstrap_replayed":False' in src
assert '"functional_translator_replayed":False' in src
cfg=json.loads((ROOT/"dev-hub/config/direct-operator.v1.json").read_text())
assert cfg["invariants"]["platform_recovery_instruction_never_bootstraps_new_project"] is True
assert cfg["platform_recovery"]["canonical_resume_command"]=="CONTINUE"
assert cfg["platform_recovery"]["automatic_external_spend_eur"]==0
print("CHACHA_DEV_TARGETED_PLATFORM_RECOVERY=PASS")
