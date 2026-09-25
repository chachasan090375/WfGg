#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

adapter=loadmod("v823_collector",ROOT/"dev-hub/adapters/collector-knowledge-adapter.py")

caps=json.loads((ROOT/"dev-hub/config/capability-registry.v1.json").read_text())
control=caps["capabilities"]["collector-knowledge-control"]["providers"]
inspect=caps["capabilities"]["collector-knowledge-inspect"]["providers"]
assert [x["id"] for x in control]==["collector-knowledge-bootstrap"],control
assert [x["id"] for x in inspect]==["collector-knowledge-runtime"],inspect

pa=json.loads((ROOT/"dev-hub/config/provider-adapters.v1.json").read_text())
assert pa["providers"]["collector-knowledge-bootstrap"]["adapter"]=="collector-knowledge-adapter"
assert pa["providers"]["collector-knowledge-runtime"]["adapter"]=="collector-knowledge-adapter"

probes=json.loads((ROOT/"dev-hub/config/provider-health-probes.v1.json").read_text())
bp=probes["providers"]["collector-knowledge-bootstrap"]
assert bp["probe"]=="adapter-provisioning-receipt"
assert bp["functional_check"]=="collector-knowledge-adapter-provisioned"

prov=json.loads((ROOT/"dev-hub/config/adapter-provisioning.v1.json").read_text())
p=prov["adapters"]["collector-knowledge-adapter"]["probe"]
assert p["input"]["bindings"]==[]
assert p["expected_exit_code"]==2
assert p["expected_status"]=="BLOCKED"

def req(action,provider,permission):
    return {
      "schema":"chacha.dev/dispatch-envelope/v1",
      "project":"wfgg-radar","task":{"id":"x","permission":permission},
      "bindings":[{"provider":provider,"adapter":"collector-knowledge-adapter"}],
      "metadata":{"collector_knowledge":{"action":action,"revision":"6ddbc5d848cf2aebc2c6175b2aa9ba1645c2e2ae","q":"x"}}
    }

for action,permission in [("pilot-install","workspace-write"),("pilot-probe","read")]:
    data,err=adapter.validate_request(req(action,"collector-knowledge-bootstrap",permission))
    assert err is None,(action,err)
    data,err=adapter.validate_request(req(action,"collector-knowledge-runtime",permission))
    assert err=="COLLECTOR_KNOWLEDGE_BINDING_MISSING:collector-knowledge-bootstrap",(action,err)

for action,permission in [("status","read"),("query","read")]:
    data,err=adapter.validate_request(req(action,"collector-knowledge-runtime",permission))
    assert err is None,(action,err)
    data,err=adapter.validate_request(req(action,"collector-knowledge-bootstrap",permission))
    assert err=="COLLECTOR_KNOWLEDGE_BINDING_MISSING:collector-knowledge-runtime",(action,err)

install=(ROOT/"dev-hub/bin/install-collector-knowledge-adapter-pilot.sh").read_text()
assert "collector-knowledge-bootstrap" in install
assert "COLLECTOR_KNOWLEDGE_BOOTSTRAP_HEALTH=HEALTHY" in install
assert "COLLECTOR_KNOWLEDGE_RUNTIME_HEALTH_ASSERTED=NO" in install
assert "['collector-knowledge-runtime']" not in install
assert "'runtime_health_asserted':False" in install

pilot=(ROOT/"dev-hub/bin/run-collector-knowledge-v1-pilot-via-chacha-dev.sh").read_text()
for marker in [
  "collector-knowledge-v1-bootstrap.task-graph.json",
  '"capabilities":["collector-knowledge-control"]',
  "COLLECTOR_KNOWLEDGE_RUNTIME_PROBE=PASS",
  "collector-knowledge-pilot-probe",
  "COLLECTOR_KNOWLEDGE_RUNTIME_HEALTH=HEALTHY",
  "collector-knowledge-v1-query.task-graph.json",
  '"capabilities":["collector-knowledge-inspect"]',
  "COLLECTOR_KNOWLEDGE_QUERY_PATH=PASS",
]:
    assert marker in pilot,marker
assert pilot.index("COLLECTOR_KNOWLEDGE_RUNTIME_HEALTH=HEALTHY") < pilot.index("QUERY_GRAPH=")
assert pilot.index("BOOTSTRAP_GRAPH=") < pilot.index("QUERY_GRAPH=")

for script in [
 ROOT/"dev-hub/bin/install-collector-knowledge-adapter-pilot.sh",
 ROOT/"dev-hub/bin/run-collector-knowledge-v1-pilot-via-chacha-dev.sh",
]:
    q=subprocess.run(["bash","-n",str(script)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert q.returncode==0,(script,q.stderr)

print("CHACHA_DEV_V823_BOOTSTRAP_RUNTIME_TRUST_SEPARATED=PASS")
print("CHACHA_DEV_V823_PROVISIONING_PROBE_RUNTIME_INDEPENDENT=PASS")
print("CHACHA_DEV_V823_BOOTSTRAP_ACTION_SCOPE=PASS")
print("CHACHA_DEV_V823_RUNTIME_ACTION_SCOPE=PASS")
print("CHACHA_DEV_V823_NO_PREMATURE_RUNTIME_HEALTH=PASS")
print("CHACHA_DEV_V823_TWO_PHASE_PILOT=PASS")
print("CHACHA_DEV_V823_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
