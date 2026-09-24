#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"
ADAPTER_ID="branch-foundry-source-integrator-v1"

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def sha(p):
    h=hashlib.sha256(Path(p).read_bytes()).hexdigest()
    return "sha256:"+h
def run(args):
    return subprocess.run([str(x) for x in args],cwd=str(ROOT),
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,check=False,timeout=60)

policy=load(CFG/"adapter-provisioning.v1.json")
item=policy["adapters"][ADAPTER_ID]
assert item["source"]=="dev-hub/adapters/platform-component-branch-foundry-source-integrator.py",item
assert item["namespace"]=="platform-component/branch-foundry-source-integrator",item
assert item["version"]=="1.0.1",item
assert item["probe"]["argv"]==["apply"],item
assert item["probe"]["expected_exit_code"]==2,item
assert item["probe"]["expected_schema"]=="chacha.dev/platform-component-source-integration-adapter-result/v1",item
assert item["probe"]["expected_status"]=="BLOCKED",item
assert item["probe"]["expected_reason"]=="APPLY_SCHEMA_INVALID",item

with tempfile.TemporaryDirectory(prefix="source-integrator-provisioning-") as raw:
    td=Path(raw);root=td/"adapters";receipt=td/"receipt.json"

    plan=run([sys.executable,BIN/"adapter-provision.py","--policy",CFG/"adapter-provisioning.v1.json",
              "--root",root,"plan","--adapter",ADAPTER_ID])
    assert plan.returncode==0,(plan.stdout,plan.stderr)
    pv=json.loads(plan.stdout)
    expected=root/"platform-component/branch-foundry-source-integrator/1.0.1/branch-foundry-source-integrator"
    current=root/"platform-component/branch-foundry-source-integrator/current"
    executable=current/"branch-foundry-source-integrator"
    assert Path(pv["installed_path"])==expected,pv
    assert Path(pv["current_link"])==current,pv
    assert Path(pv["executable_path"])==executable,pv
    assert pv["applied"] is False,pv
    assert not expected.exists()

    # No apply without the explicit provisioner flag.
    denied=run([sys.executable,BIN/"adapter-provision.py","--policy",CFG/"adapter-provisioning.v1.json",
                "--root",root,"apply","--adapter",ADAPTER_ID,
                "--actor","qualification","--receipt",receipt])
    assert denied.returncode==2,(denied.stdout,denied.stderr)
    assert "EXPLICIT_APPLY_FLAG_REQUIRED" in denied.stdout
    assert not expected.exists()

    applied=run([sys.executable,BIN/"adapter-provision.py","--policy",CFG/"adapter-provisioning.v1.json",
                 "--root",root,"apply","--adapter",ADAPTER_ID,
                 "--actor","qualification","--receipt",receipt,"--apply"])
    assert applied.returncode==0,(applied.stdout,applied.stderr)
    assert receipt.is_file(),receipt
    rv=load(receipt)
    source=ROOT/item["source"]
    assert rv["schema"]=="chacha.dev/adapter-provisioning-receipt/v1",rv
    assert rv["adapter"]==ADAPTER_ID,rv
    assert rv["version"]=="1.0.1",rv
    assert rv["applied"] is True and rv["idempotent"] is False,rv
    assert Path(rv["installed_path"])==expected,rv
    assert Path(rv["executable_path"])==executable,rv
    assert Path(rv["current_link"])==current,rv
    assert current.is_symlink(),current
    assert executable.is_file(),executable
    assert rv["source_digest"]==sha(source),rv
    assert rv["installed_digest"]==sha(expected)==rv["source_digest"],rv
    assert rv["executable_digest"]==sha(executable)==rv["source_digest"],rv
    assert rv["probe"]["status"]=="PASS",rv
    assert rv["probe"]["exit_code"]==2,rv
    assert rv["probe"]["expected_exit_code"]==2,rv
    assert rv["probe"]["result_schema"]=="chacha.dev/platform-component-source-integration-adapter-result/v1",rv
    assert rv["probe"]["result_status"]=="BLOCKED",rv
    assert rv["probe"]["result_reason"]=="APPLY_SCHEMA_INVALID",rv

    verified=run([sys.executable,BIN/"adapter-provision.py","--policy",CFG/"adapter-provisioning.v1.json",
                  "--root",root,"verify","--adapter",ADAPTER_ID,"--receipt",receipt])
    assert verified.returncode==0,(verified.stdout,verified.stderr)
    assert "PROVISIONING_VERIFY=PASS" in verified.stdout

    # Exact replay installs no new bytes and remains idempotent.
    replay=run([sys.executable,BIN/"adapter-provision.py","--policy",CFG/"adapter-provisioning.v1.json",
                "--root",root,"apply","--adapter",ADAPTER_ID,
                "--actor","qualification","--receipt",receipt,"--apply"])
    assert replay.returncode==0,(replay.stdout,replay.stderr)
    rv2=load(receipt)
    assert rv2["idempotent"] is True,rv2
    assert rv2["source_digest"]==rv["source_digest"],(rv,rv2)
    assert rv2["executable_digest"]==rv["executable_digest"],(rv,rv2)

    # Sandbox root proves CI never provisions /opt.
    assert str(expected).startswith(str(root.resolve())),expected
    assert not str(expected).startswith("/opt/chacha-dev/"),expected

# Provisioning is not registration/promotion.
live=load(CFG/"platform-component-apply-adapter-registry.v1.json")
assert live["default_admission"]=="DENY",live
assert live["adapters"]=={},live

source=(BIN/"adapter-provision.py").read_text(encoding="utf-8")
assert 'argv=[str(executable),*[str(x) for x in (cfg.get("argv") or [])]]' in source
assert 'expected_exit_code = int(cfg.get("expected_exit_code",0))' in source
assert "shell=False" in source
assert "os.system" not in source

print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_PROVISIONING=PASS")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_PROVISIONING_SANDBOX=YES")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_PROVISIONING_DIGEST_CHAIN=PASS")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_PROVISIONING_ATOMIC_CURRENT=PASS")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_PROVISIONING_FAIL_CLOSED_PROBE=PASS")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_PROVISIONING_IDEMPOTENT=YES")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_LIVE_REGISTRY=EMPTY")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_PROVISIONING_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
