#!/usr/bin/env python3
from __future__ import annotations
import base64,hashlib,importlib.util,json,subprocess,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
GUARDIAN_CLIENT=ROOT/"dev-hub/bin/guardian-client.py"
RUN_CONTROLLER=ROOT/"dev-hub/bin/run-controller.py"
ORCH=ROOT/"dev-hub/bin/autonomous-project-orchestrator.py"
TECH=ROOT/"dev-hub/bin/technology_watch_runtime.py"
PORTFOLIO=ROOT/"dev-hub/bin/architecture-portfolio-optimizer.py"
ARCH_REG=ROOT/"dev-hub/bin/reusable-architecture-registry.py"
PILOT=ROOT/"dev-hub/bin/architecture-comparative-pilot.py"
FIXTURE=ROOT/"dev-hub/tests/fixtures/comparative-pilot-harness.py"

# 1) Ed25519 client signs with the same public identity derivation as the central brain.
spec=importlib.util.spec_from_file_location("guardian_client",GUARDIAN_CLIENT)
gc=importlib.util.module_from_spec(spec);spec.loader.exec_module(gc)
with tempfile.TemporaryDirectory(prefix="chacha-v615-key-") as td:
    td=Path(td);key=td/"key.pem";pub=td/"pub.pem";msg=td/"msg";sig=td/"sig"
    subprocess.run(["openssl","genpkey","-algorithm","ED25519","-out",str(key)],check=True)
    subprocess.run(["openssl","pkey","-in",str(key),"-pubout","-out",str(pub)],check=True)
    payload=b"guardian-v615"
    signature=gc.sign(key,payload)
    sig.write_bytes(base64.urlsafe_b64decode(signature+"="*((4-len(signature)%4)%4)))
    msg.write_bytes(payload)
    subprocess.run(["openssl","pkeyutl","-verify","-rawin","-pubin","-inkey",str(pub),
                    "-sigfile",str(sig),"-in",str(msg)],check=True,stdout=subprocess.DEVNULL)
    assert gc.key_id(key).startswith("central-")

# 2) Role contracts keep the external auditor non-architectural.
roles=json.load(open(ROOT/"dev-hub/config/guardian-role-contracts.v1.json",encoding="utf-8"))
assert roles["principles"]["guardian_is_external_to_central_brain"] is True
assert roles["principles"]["guardian_cannot_build_or_choose_architecture"] is True
contracts={x["contract_id"]:x for x in roles["contracts"]}
assert "FINAL_ARCHITECTURE_DECISION" in contracts["role:branch-foundry"]["forbidden_actions"]
assert "FINAL_ARCHITECTURE_DECISION" in contracts["component:central-orchestrator"]["allowed_actions"]
assert "RUN_COMPARATIVE_PILOT" in contracts["role:comparative-pilot"]["allowed_actions"]

# 3) Main execution and orchestration paths are actually guarded.
rc=RUN_CONTROLLER.read_text(encoding="utf-8")
assert 'guardian_gate(' in rc
assert '"PRE_ACTION"' in rc and '"POST_ACTION"' in rc
assert "GUARDIAN_UNAVAILABLE_FAIL_CLOSED" in rc
orch=ORCH.read_text(encoding="utf-8")
assert "guardian_stage(" in orch
assert 'architecture-comparative-pilot.py' in orch
assert '--comparative-pilot-result' in orch
tech=TECH.read_text(encoding="utf-8")
assert "_guardian_observe_consult" in tech
assert '"actor":"technology-watch"' in tech

# 4) A real historical/current conflict is unresolved until comparative evidence exists.
with tempfile.TemporaryDirectory(prefix="chacha-v615-portfolio-") as td:
    td=Path(td);db=td/"arch.db"
    pre={"schema":"chacha.dev/domain-plan/v1","packages":[{"id":"web","domain":"web-ui","kind":"primary","capabilities":["static-web"]}]}
    branch={"schema":"chacha.dev/branch-topology/v1","blocked":[],"decisions":[{
      "package_id":"web","domain":"web-ui","architecture":{"pattern":"current-edge","runtime":"none"},
      "chosen_cost":{"external_spend_eur":0}
    }]}
    agent={"schema":"chacha.dev/agent-topology/v1","decisions":[{"package_id":"web","domain":"web-ui","decision":"TOOL_ONLY"}]}
    for n,x in [("pre",pre),("branch",branch),("agent",agent)]:(td/(n+".json")).write_text(json.dumps(x))
    sig=subprocess.check_output([
      "python3","-c",
      "import importlib.util,json,sys;s=importlib.util.spec_from_file_location('r',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(m.project_signature(json.load(open(sys.argv[2]))))",
      str(ARCH_REG),str(td/"pre.json")],text=True).strip()
    rec={
      "architecture_id":"architecture-"+sig[:20],"version":"historical-best","functional_signature":sig,
      "components":{"packages":[{"domain":"web-ui","kind":"primary","capabilities":["static-web"],
        "architecture":{"pattern":"historical-edge","runtime":"none"},"agent_decision":"TOOL_ONLY"}]},
      "qualification_status":"PASS","state":"ADOPT",
      "technology_revalidated_at":time.strftime("%Y-%m-%dT%H:%M:%S",time.gmtime())+".123456Z",
      "technology_snapshot_digest":"v615","external_spend_eur":0,"quality_score":99,
      "success_count":20,"failure_count":0,"incident_count":0,"latency_ms":25,"memory_mb":64
    }
    rp=td/"record.json";rp.write_text(json.dumps(rec))
    subprocess.run(["python3",str(ARCH_REG),"--db",str(db),"register","--record",str(rp)],check=True,stdout=subprocess.DEVNULL)
    p1=td/"portfolio1.json"
    subprocess.run(["python3",str(PORTFOLIO),"--repo-root",str(ROOT),"--preplan",str(td/"pre.json"),
                    "--branch-topology",str(td/"branch.json"),"--agent-topology",str(td/"agent.json"),
                    "--architecture-memory-db",str(db),"--policy",str(ROOT/"dev-hub/config/architecture-portfolio-optimizer.v1.json"),
                    "--output",str(p1)],check=True,stdout=subprocess.DEVNULL)
    x1=json.load(open(p1));assert x1["mode"]=="COMPARATIVE_PILOT_REQUIRED" and x1["decision_ready"] is False

    # No harness => fail closed; explicit identical harness => dry-run plumbing works.
    blocked=td/"pilot-blocked.json"
    subprocess.run(["python3",str(PILOT),"--repo-root",str(ROOT),"--portfolio",str(p1),"--output",str(blocked)],
                   check=True,stdout=subprocess.DEVNULL)
    assert json.load(open(blocked))["reason"]=="REAL_BENCHMARK_HARNESS_REQUIRED"
    harness={
      "schema":"chacha.dev/comparative-pilot-harness/v1",
      "argv":["/usr/bin/python3",str(FIXTURE),"--architecture","{architecture_json}",
              "--output","{result_json}","--variant","{variant}"],
      "resource_budget":{"memory_mb":128,"cpu_weight":25,"tasks_max":4,"timeout_seconds":30}
    }
    hp=td/"harness.json";hp.write_text(json.dumps(harness))
    dry=td/"pilot-dry.json"
    subprocess.run(["python3",str(PILOT),"--repo-root",str(ROOT),"--portfolio",str(p1),
                    "--harness",str(hp),"--output",str(dry),"--runtime-root",str(td/"runtime"),"--dry-run"],
                   check=True,stdout=subprocess.DEVNULL)
    assert json.load(open(dry))["status"]=="DRY_RUN"

    # Valid pilot evidence resolves the same functional signature deterministically.
    pilot_result={
      "schema":"chacha.dev/architecture-comparative-pilot-result/v1","status":"PASS","resolved":True,
      "winner":"CURRENT","reason":"LEXICOGRAPHIC_RUNTIME_EVIDENCE","functional_signature":sig,
      "same_benchmark_contract":True,"isolated_capsules":True
    }
    pp=td/"pilot.json";pp.write_text(json.dumps(pilot_result))
    p2=td/"portfolio2.json"
    subprocess.run(["python3",str(PORTFOLIO),"--repo-root",str(ROOT),"--preplan",str(td/"pre.json"),
                    "--branch-topology",str(td/"branch.json"),"--agent-topology",str(td/"agent.json"),
                    "--architecture-memory-db",str(db),"--policy",str(ROOT/"dev-hub/config/architecture-portfolio-optimizer.v1.json"),
                    "--comparative-pilot-result",str(pp),"--output",str(p2)],check=True,stdout=subprocess.DEVNULL)
    x2=json.load(open(p2))
    assert x2["mode"]=="COMPARATIVE_PILOT_RESOLVED",x2
    assert x2["decision_ready"] is True,x2
    assert x2["selected"]["source"]=="CURRENT_FOUNDRY_SYNTHESIS",x2

poller=(ROOT/"dev-hub/bin/guardian-alert-poller.py").read_text(encoding="utf-8")
assert '"auto_stop_executed":False' in poller
assert "emergency-stop-controller" not in poller

print("CHACHA_DEV_V615_GUARDIAN_ED25519=PASS")
print("CHACHA_DEV_V615_ROLE_CONTRACTS=PASS")
print("CHACHA_DEV_V615_RUNTIME_GUARDIAN_GATES=PASS")
print("CHACHA_DEV_V615_TECHNOLOGY_WATCH_GUARDIAN=PASS")
print("CHACHA_DEV_V615_COMPARATIVE_PILOT_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V615_COMPARATIVE_PILOT_RESOLUTION=PASS")
print("CHACHA_DEV_V615_GUARDIAN_NO_AUTOSTOP=PASS")
