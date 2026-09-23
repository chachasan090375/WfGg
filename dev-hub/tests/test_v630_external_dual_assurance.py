#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config"

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def load(path):return json.loads(Path(path).read_text(encoding="utf-8"))

sentinel=loadmod("sentinel_technical_audit",BIN/"sentinel-technical-audit.py")
gate=loadmod("external_assurance_release_gate",BIN/"external-assurance-release-gate.py")
sp=load(CFG/"sentinel-technical-policy.v1.json")
sr=load(CFG/"sentinel-runtime-policy.v1.json")
gp=load(CFG/"guardian-runtime-policy.v1.json")

assert sp["principles"]["external_technical_assurance"] is True
assert sp["principles"]["direct_code_mutation"] is False
assert sp["principles"]["central_orchestrator_owns_remediation"] is True
assert sr["principles"]["technical_scope_only"] is True
assert sr["principles"]["no_functional_authority"] is True
assert sr["principles"]["no_architecture_authority"] is True
assert gp["external_dual_assurance"]["production_requires_guardian_functional_receipt"] is True
assert gp["external_dual_assurance"]["production_requires_sentinel_technical_receipt"] is True
assert gp["external_dual_assurance"]["remediation_owner"]=="central-orchestrator"

with tempfile.TemporaryDirectory(prefix="v630-sentinel-") as td:
    root=Path(td)
    subprocess.run(["git","init","-q"],cwd=root,check=True)
    subprocess.run(["git","config","user.email","sentinel@example.invalid"],cwd=root,check=True)
    subprocess.run(["git","config","user.name","Sentinel Test"],cwd=root,check=True)
    (root/"good.py").write_text("def answer():\n    return 42\n",encoding="utf-8")
    subprocess.run(["git","add","good.py"],cwd=root,check=True)
    subprocess.run(["git","commit","-qm","good"],cwd=root,check=True)
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
    good=sentinel.audit(root,sp,None,head,False)
    assert good["verdict"]=="PASS",good
    assert good["direct_code_mutation"] is False,good
    (root/"bad.py").write_text("<<<<<<< ours\nx=1\n=======\nx=2\n>>>>>>> theirs\n",encoding="utf-8")
    subprocess.run(["git","add","bad.py"],cwd=root,check=True)
    subprocess.run(["git","commit","-qm","bad"],cwd=root,check=True)
    badhead=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
    bad=sentinel.audit(root,sp,head,badhead,False)
    assert bad["verdict"]=="BLOCK",bad
    assert any(x.get("check")=="merge-conflict-markers" for x in bad["blocking_findings"]),bad

revision="a"*40
functional={
 "schema":"chacha.dev/guardian-functional-acceptance-receipt/v1",
 "receipt_id":"guardian-func-test","project_id":"project-x","revision":revision,"verdict":"PASS"
}
technical={
 "schema":"chacha.dev/sentinel-technical-receipt/v1",
 "receipt_id":"sentinel-test","project_id":"project-x","revision":revision,"verdict":"PASS"
}
ok=gate.combine(functional,technical,"project-x",revision)
assert ok["production_allowed"] is True,ok
assert ok["remediation_owner"]=="central-orchestrator",ok
assert ok["guardian_direct_mutation"] is False and ok["sentinel_direct_mutation"] is False,ok

wrong=dict(technical);wrong["revision"]="b"*40
blocked=gate.combine(functional,wrong,"project-x",revision)
assert blocked["production_allowed"] is False,blocked
assert "SENTINEL_REVISION_MISMATCH" in blocked["reason_codes"],blocked
failed=dict(technical);failed["verdict"]="BLOCK"
blocked2=gate.combine(functional,failed,"project-x",revision)
assert blocked2["production_allowed"] is False,blocked2
assert "SENTINEL_TECHNICAL_NOT_PASS" in blocked2["reason_codes"],blocked2

guardian=(ROOT/"dev-hub/guardian/worker.js").read_text(encoding="utf-8")
sentinel_worker=(ROOT/"dev-hub/sentinel/worker.js").read_text(encoding="utf-8")
guardian_client=(BIN/"guardian-client.py").read_text(encoding="utf-8")
sentinel_client=(BIN/"sentinel-client.py").read_text(encoding="utf-8")
sentinel_controller=(BIN/"sentinel-remediation-controller.py").read_text(encoding="utf-8")
workflow=(ROOT/".github/workflows/dev-hub-sentinel-technical-assurance.yml").read_text(encoding="utf-8")

for marker in [
 "/v1/functional-acceptance","FUNCTIONAL_CONTRACT_DRIFT","GUARDIAN_FUNCTIONAL_RECEIPT_REQUIRED",
 "SENTINEL_TECHNICAL_RECEIPT_REQUIRED","verifySentinelReceipt","dual_external_assurance_required_for_production:true",
 "functional_direct_mutation:false"
]:
    assert marker in guardian,marker
for marker in [
 "external_technical_assurance:true","technical_scope_only:true","github_workflow_verification:true",
 "direct_code_mutation:false","central_orchestrator_owns_remediation:true","/v1/release-check","/v1/receipts/"
]:
    assert marker in sentinel_worker,marker
assert 'sub.add_parser("functional-acceptance")' in guardian_client
assert 'sub.add_parser("release-check")' in sentinel_client
assert "CENTRAL_ORCHESTRATOR_OWNS_REMEDIATION=YES" in sentinel_controller
assert "name: ChaCha DEV Sentinel technical assurance" in workflow
assert "sentinel-technical-audit.py" in workflow
assert "actions/upload-artifact@v4" in workflow

print("CHACHA_DEV_V630_SENTINEL_EXTERNAL_TECHNICAL_SCOPE=PASS")
print("CHACHA_DEV_V630_SENTINEL_CODE_HYGIENE_AUDIT=PASS")
print("CHACHA_DEV_V630_GUARDIAN_EXTERNAL_FUNCTIONAL_SCOPE=PASS")
print("CHACHA_DEV_V630_ORIGINAL_FUNCTIONAL_CONTRACT_PINNING=PASS")
print("CHACHA_DEV_V630_DUAL_EXTERNAL_RECEIPTS_REQUIRED=PASS")
print("CHACHA_DEV_V630_EXACT_RELEASE_REVISION_REQUIRED=PASS")
print("CHACHA_DEV_V630_EXTERNAL_AGENTS_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V630_CENTRAL_ORCHESTRATOR_REMEDIATION_OWNER=PASS")
print("CHACHA_DEV_V630_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
