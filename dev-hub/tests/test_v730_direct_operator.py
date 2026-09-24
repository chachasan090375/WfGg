#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
spec=importlib.util.spec_from_file_location("direct_operator",BIN/"direct-operator-service.py")
mod=importlib.util.module_from_spec(spec);assert spec and spec.loader;spec.loader.exec_module(mod)

def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")

assert mod.normalize("Allo")=="STATUS"
assert mod.normalize("Go!")=="CONTINUE"
assert mod.normalize("STOP.")=="STOP"
assert mod.normalize("Ajoute un widget")=="INSTRUCTION"

# Guardian D1 zero-cost write budget must stay coherent across timer and freshness policy.
guardian_policy=mod.load(ROOT/"dev-hub/config/guardian-runtime-policy.v1.json")
coverage_manifest=mod.load(ROOT/"dev-hub/config/guardian-coverage-manifest.v1.json")
coverage_timer=(ROOT/"dev-hub/systemd/chacha-dev-guardian-coverage-heartbeat.timer").read_text(encoding="utf-8")
assert guardian_policy["coverage_heartbeat_max_age_seconds"]==900,guardian_policy
assert coverage_manifest["heartbeat_max_age_seconds"]==900,coverage_manifest
assert guardian_policy["d1_write_budget"]["coverage_heartbeat_interval_seconds"]==300,guardian_policy
assert guardian_policy["d1_write_budget"]["automatic_paid_upgrade"] is False,guardian_policy
assert coverage_manifest["d1_write_budget"]["automatic_paid_upgrade"] is False,coverage_manifest
assert "OnUnitActiveSec=300s" in coverage_timer,coverage_timer
assert "OnUnitActiveSec=60s" not in coverage_timer,coverage_timer
coverage_sync=(ROOT/".github/workflows/dev-hub-v7-guardian-coverage-sync.yml").read_text(encoding="utf-8")
contract_sync=(ROOT/".github/workflows/dev-hub-v7-guardian-contract-sync.yml").read_text(encoding="utf-8")
assert "WHERE expected_components.source_digest<>excluded.source_digest" in coverage_sync,coverage_sync
assert "FULL_TABLE_REWRITE=NO" in coverage_sync,coverage_sync
assert "WHERE role_contracts.source_digest<>excluded.source_digest" in contract_sync,contract_sync

satellite=mod.load(ROOT/"dev-hub/config/functional-translator-satellite.v1.json")
assert satellite["scope"]=="PLATFORM_EDGE_SATELLITE",satellite
assert satellite["fleet_membership"]=="EXCLUDED_EDGE_SATELLITE",satellite
assert satellite["permissions"]["repository_write"] is False,satellite
assert satellite["permissions"]["production_change"] is False,satellite
assert satellite["handoff"]["central_orchestrator_recompiles_independently"] is True,satellite

with tempfile.TemporaryDirectory(prefix="v730-direct-") as raw:
    td=Path(raw);runtime=td/"runtime";runtime.mkdir()
    auth=td/"authorized.json";save(auth,{"authorized_logins":["operator@example.test"]})
    fake_controller=td/"fake-controller.py"
    fake_controller.write_text("""#!/usr/bin/env python3
import json,sys,uuid
from pathlib import Path
args=sys.argv[1:]
out=Path(args[args.index('--output')+1])
command=next((x for x in ('status','instruction','continue') if x in args),'status')
project='direct-test-project'
status='OK' if command=='status' else ('CONTINUED_PLAN_READY' if command=='continue' else 'PLAN_READY')
decision={'continuation_mode':'FRESH_CENTRAL_REORCHESTRATION'} if command=='continue' else {'source':'fake-central'}
x={'schema':'chacha.dev/central-interface-receipt/v1','receipt_id':'fake-'+uuid.uuid4().hex,
   'observed_at':'2026-09-24T00:00:00Z','command':command.upper(),'project_id':project,
   'status':status,'authority':'central-orchestrator','brain_decision_obtained':True,
   'next_action':'DOMAIN_FACTORIES','evidence_refs':['fake-evidence'],'decision':decision,
   'automatic_external_spend_eur':0}
if command=='continue':x['continuation_of_request_id']='previous'
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(x)+'\\n')
print(json.dumps(x))
""",encoding="utf-8")
    fake_stop=td/"fake-stop.py"
    fake_stop.write_text("""#!/usr/bin/env python3
import json
print(json.dumps({'schema':'chacha.dev/emergency-stop-state/v1','active':True}))
""",encoding="utf-8")
    policy={
      "schema":"chacha.dev/direct-operator-policy/v1","version":"test",
      "bind":"127.0.0.1","port":18792,"runtime_root":str(runtime/"direct-operator"),
      "ui_root":str(ROOT/"dev-hub/direct-operator-ui"),"max_request_bytes":65536,
      "default_project":"chacha-dev-platform",
      "authentication":{"mode":"TAILSCALE_SERVE_IDENTITY","login_header":"Tailscale-User-Login",
        "authorized_users_file":str(auth),"fail_closed_if_identity_missing":True,"backend_must_bind_loopback":True},
      "transport":{"public_funnel_forbidden":True,"tailscale_serve_private_only":True,"tailscale_https_port":8443},
      "translator":{"id":"functional-translator-satellite","script":"dev-hub/bin/functional-translator-agent.py",
        "execution_authority":False,"architecture_authority":False,"raw_text_preserved":True},
      "central_controller":str(fake_controller),"emergency_controller":str(fake_stop),
      "invariants":{"chatgpt_not_in_direct_path":True,"direct_operator_has_no_technical_decision_authority":True,
        "direct_operator_has_no_direct_mutation":True,"central_orchestrator_required":True,
        "guardian_and_platform_governance_preserved":True,"automatic_external_spend_eur":0}
    }
    assert mod.operator_from_headers({},policy) is None
    assert mod.operator_from_headers({"Tailscale-User-Login":"intruder@example.test"},policy) is None
    assert mod.operator_from_headers({"Tailscale-User-Login":"operator@example.test"},policy)=="operator@example.test"

    st=mod.State(ROOT,runtime,policy)
    jid="job-instruction"
    st.process(jid,"Ajoute un widget Android d accès direct","chacha-dev-platform","operator@example.test")
    j=mod.load(st.job_path(jid));assert j["state"]=="COMPLETE",j
    r=j["response"];assert r["status"]=="PLAN_READY" and r["brain_decision_obtained"] is True,r
    assert r["interface_direct_technical_decision"] is False and r["interface_direct_mutation"] is False,r
    req=next((runtime/"direct-operator/requests").iterdir())
    translation=mod.load(req/"translation/translation.json")
    assert translation["translator_execution_authority"] is False,translation
    assert translation["translator_architecture_authority"] is False,translation
    assert translation["raw_text_preserved"] is True,translation
    assert Path(translation["functional_contract"]).is_file(),translation

    jid2="job-go";st.process(jid2,"Go","direct-test-project","operator@example.test")
    j2=mod.load(st.job_path(jid2));assert j2["state"]=="COMPLETE",j2
    assert j2["response"]["status"]=="CONTINUED_PLAN_READY",j2
    assert j2["response"]["brain_receipt"]["decision"]["continuation_mode"]=="FRESH_CENTRAL_REORCHESTRATION",j2

    jid3="job-status";st.process(jid3,"Allo","direct-test-project","operator@example.test")
    j3=mod.load(st.job_path(jid3));assert j3["state"]=="COMPLETE" and j3["response"]["status"]=="OK",j3

    jid4="job-stop";st.process(jid4,"Stop","direct-test-project","operator@example.test")
    j4=mod.load(st.job_path(jid4));assert j4["state"]=="COMPLETE" and j4["response"]["status"]=="STOP_ACTIVE",j4

print("CHACHA_DEV_V730_DIRECT_OPERATOR=PASS")
print("CHACHA_DEV_V730_TAILSCALE_IDENTITY_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V730_FUNCTIONAL_TRANSLATOR=PASS")
print("CHACHA_DEV_V730_TRANSLATOR_FLEET_MEMBERSHIP=EXCLUDED_EDGE_SATELLITE")
print("CHACHA_DEV_V730_TRANSLATOR_EXECUTION_AUTHORITY=NO")
print("CHACHA_DEV_V730_TRANSLATOR_ARCHITECTURE_AUTHORITY=NO")
print("CHACHA_DEV_V730_CHATGPT_IN_DIRECT_PATH=NO")
print("CHACHA_DEV_V730_DIRECT_OPERATOR_MUTATION_AUTHORITY=NO")
print("CHACHA_DEV_V730_GO_CENTRAL_CONTINUATION=PASS")
print("CHACHA_DEV_V730_STOP_OUT_OF_BAND=PASS")
print("CHACHA_DEV_V730_GUARDIAN_D1_BUDGET=PASS")
print("CHACHA_DEV_V730_GUARDIAN_HEARTBEAT_SECONDS=300")
print("CHACHA_DEV_V730_GUARDIAN_HEARTBEAT_MAX_AGE_SECONDS=900")
print("CHACHA_DEV_V730_GUARDIAN_D1_SYNC_MODE=DIGEST_AWARE_DELTA")
print("CHACHA_DEV_V730_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
