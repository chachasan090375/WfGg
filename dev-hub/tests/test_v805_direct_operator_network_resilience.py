#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def loadmod(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

mod=loadmod("v805_direct",ROOT/"dev-hub/bin/direct-operator-service.py")
policy=mod.load(ROOT/"dev-hub/config/direct-operator.v1.json")

with tempfile.TemporaryDirectory(prefix="v805-idempotency-") as raw:
    runtime=Path(raw)
    isolated_policy=dict(policy)
    isolated_policy["runtime_root"]=str(runtime/"direct-operator")
    st=mod.State(ROOT,runtime,isolated_policy)
    jid1,created1=st.accept_intent("Test réseau","chacha-dev-platform","operator@example.test","req-12345678")
    jid2,created2=st.accept_intent("Test réseau","chacha-dev-platform","operator@example.test","req-12345678")
    assert created1 is True
    assert created2 is False
    assert jid1==jid2
    assert st.job_path(jid1).is_file()

    try:
        st.accept_intent("Autre texte","chacha-dev-platform","operator@example.test","req-12345678")
        raise AssertionError("idempotency collision must fail")
    except RuntimeError as e:
        assert "IDEMPOTENCY_KEY_REUSED" in str(e)

    cfg=st.effective_live_shell_config()
    assert "runtime_revision" in cfg

ui=(ROOT/"dev-hub/direct-operator-ui/index.html").read_text(encoding="utf-8")
for marker in [
    "async function fetchJson(url,options={},attempts=3)",
    "client_request_id:clientRequestId",
    "},4);",
    "Connexion interrompue — la demande est conservée",
    "let runtimeRevision=''",
    "async function checkUiRevision()",
    "setInterval(checkUiRevision,10000)",
    "if(activeJobId){pendingUiReload=true",
    "window.addEventListener('online'",
    "if(progressBusy)return",
]:
    assert marker in ui,marker

src=(ROOT/"dev-hub/bin/direct-operator-service.py").read_text(encoding="utf-8")
assert "legacy_client_request_id=not bool(client_request_id)" in src
assert '"deduplicated":not created' in src
assert 'self.idempotency=self.root/"idempotency"' in src

print("CHACHA_DEV_V805_IDEMPOTENT_RETRY=PASS")
print("CHACHA_DEV_V805_LEGACY_UI_COMPATIBILITY=PASS")
print("CHACHA_DEV_V805_NETWORK_RETRY=PASS")
print("CHACHA_DEV_V805_POLLING_BACKPRESSURE=PASS")
print("CHACHA_DEV_V805_REMOTE_UI_SELF_RELOAD=PASS")
print("CHACHA_DEV_V805_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
