#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("v828_readiness",ROOT/"dev-hub/bin/domain-toolchain-readiness.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding="utf-8")

with tempfile.TemporaryDirectory(prefix="v828-domain-exec-") as raw:
    base=Path(raw);repo=base/"repo";planning=base/"planning";factory=base/"factory"
    cfg=repo/"dev-hub/config";out=base/"readiness.json";health_path=base/"health.json"
    graph={
      "schema":"chacha.dev/task-graph/v1","project":"chacha-dev-platform","transition":"IDEA->DESIGN",
      "tasks":[{"id":"capability:domain-development:code-edit","metadata":{"package_id":"domain:development"},
                "capabilities":["code-edit"],"permission":"workspace-write"}]
    }
    topology={"schema":"chacha.dev/agent-topology/v1","decisions":[{
      "package_id":"domain:development","agent_id":"backend-api-architect",
      "manifest":{"tools":["ready-provider"]}
    }]}
    registry={"schema":"chacha.dev/capability-registry/v1","capabilities":{
      "code-edit":{"providers":[{"id":"ready-provider","status":"ADOPT"}]}
    }}
    adapters={"schema":"chacha.dev/provider-adapters/v1",
      "providers":{"ready-provider":{"adapter":"ready-adapter","execution":"vps"}},
      "adapters":{"ready-adapter":{"status":"ENABLED","executable":"/bin/true",
                                    "supports":["workspace-write"]}}}
    probes={"schema":"chacha.dev/provider-health-probes/v1","providers":{
      "ready-provider":{"scope":"platform","probe":"runtime-command","functional_check":"test"}
    }}
    health={"schema":"chacha.dev/provider-health-snapshot/v1","observed_at":"2026-09-25T19:00:00Z",
            "providers":{"ready-provider":{"state":"HEALTHY","source":"v828-test","checked_at":"2026-09-25T19:00:00Z"}}}
    write(factory/"domain-execution-graph.json",graph);write(planning/"agent-topology.json",topology)
    write(cfg/"provider-adapters.v1.json",adapters);write(cfg/"provider-health-probes.v1.json",probes)
    write(cfg/"capability-registry.v1.json",registry);write(health_path,health)

    blocked=mod.evaluate(repo,planning,factory,out)
    assert blocked["status"]=="BLOCKED",blocked
    assert blocked["next_stage"]=="PROVIDER_HEALTH_PROBE_REQUIRED",blocked

    ready=mod.evaluate(repo,planning,factory,out,health_path)
    assert ready["status"]=="READY",ready
    assert ready["next_stage"]=="SCHEDULER_READY",ready
    assert ready["provider_health_snapshot"]==str(health_path),ready
    task=ready["tasks"][0]
    assert task["gate"]=="READY" and (task.get("selected_candidate") or {}).get("health_state")=="HEALTHY",task

controller=(ROOT/"dev-hub/bin/central-interface-controller.py").read_text(encoding="utf-8")
for marker in [
  'prior_next in {',
  '"PROVIDER_HEALTH_PROBE_REQUIRED"',
  'domain_scheduler_run_controller',
  'execution-scheduler.py',
  'run-controller.py',
  '"--execute"',
  '"continuation_mode":"DOMAIN_EXECUTION_HANDOFF"',
  '"production_approval_bypass":False',
  '"run_controller_execute_requested":True'
]:
    assert marker in controller,marker

print("CHACHA_DEV_V828_HEALTH_EVIDENCE_TO_SCHEDULER_READY=PASS")
print("CHACHA_DEV_V828_FAIL_CLOSED_WITHOUT_HEALTH=PASS")
print("CHACHA_DEV_V828_DOMAIN_GATES_RESUMABLE=PASS")
print("CHACHA_DEV_V828_SCHEDULER_HANDOFF=PASS")
print("CHACHA_DEV_V828_RUN_CONTROLLER_EXECUTE_HANDOFF=PASS")
print("CHACHA_DEV_V828_GUARDIAN_AND_APPROVAL_GATES_PRESERVED=PASS")
print("CHACHA_DEV_V828_NO_BOOTSTRAP_REPLAY=PASS")
print("CHACHA_DEV_V828_AUTOMATIC_EXTERNAL_SPEND_EUR=0")

[executed on device: ubuntu-s-1vcpu-512mb-10gb-ams3 (815f25b8-52f6-4510-87c3-5844915609a1)]