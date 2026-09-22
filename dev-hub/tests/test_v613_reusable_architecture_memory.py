#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ARCH_REG=ROOT/"dev-hub/bin/reusable-architecture-registry.py"
BRANCH_REG=ROOT/"dev-hub/bin/reusable-branch-registry.py"
COUNCIL=ROOT/"dev-hub/bin/architecture-decision-council.py"
COUNCIL_POLICY=ROOT/"dev-hub/config/architecture-decision-council.v1.json"
ACCEPT=ROOT/"dev-hub/bin/acceptance-engine.py"

with tempfile.TemporaryDirectory(prefix="chacha-v613-") as td:
    td=Path(td)
    pre={"schema":"chacha.dev/domain-plan/v1","packages":[
      {"id":"web","domain":"web-ui","kind":"primary","capabilities":["static-web"]}
    ]}
    pre_path=td/"pre.json";pre_path.write_text(json.dumps(pre))

    # Register one proven complete architecture.
    sig=subprocess.check_output(
      ["python3","-c",
       "import importlib.util,json,sys; s=importlib.util.spec_from_file_location('r',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(m.project_signature(json.load(open(sys.argv[2]))))",
       str(ARCH_REG),str(pre_path)],text=True
    ).strip()
    arch_record={
      "schema":"chacha.dev/reusable-architecture-record/v1",
      "architecture_id":"architecture-"+sig[:20],"version":"system-proven",
      "functional_signature":sig,
      "components":{"packages":[{
        "domain":"web-ui","kind":"primary","capabilities":["static-web"],
        "architecture":{"pattern":"proven-static-edge","runtime":"none"},
        "architecture_source":"FOUNDRY_SYNTHESIS","agent_decision":"TOOL_ONLY"
      }],"agent_topology":[],"capability_foundry":[],"runtime_waves":[]},
      "qualification_status":"PASS","state":"ADOPT",
      "technology_revalidated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "technology_snapshot_digest":"snap-v613","external_spend_eur":0,"quality_score":99,
      "success_count":4,"failure_count":0,"incident_count":0
    }
    rec=td/"arch-record.json";rec.write_text(json.dumps(arch_record))
    arch_db=td/"architectures.db"
    subprocess.run(["python3",str(ARCH_REG),"--db",str(arch_db),"register","--record",str(rec)],check=True,stdout=subprocess.DEVNULL)

    # Council must consult full architecture memory while still requiring current Foundries.
    branch={"schema":"chacha.dev/branch-topology/v1","blocked":[],"decisions":[{
      "package_id":"web","domain":"web-ui","architecture":{"pattern":"new-foundry-candidate"},
      "chosen_cost":{"external_spend_eur":0}
    }]}
    agent={"schema":"chacha.dev/agent-topology/v1","decisions":[{"package_id":"web","domain":"web-ui","decision":"TOOL_ONLY"}]}
    cap={"schema":"chacha.dev/capability-foundry-plan/v1","plans":[]}
    for n,x in [("branch",branch),("agent",agent),("cap",cap)]:
        (td/(n+".json")).write_text(json.dumps(x))
    branch_db=td/"branches.db"
    out=td/"council.json"
    subprocess.run([
      "python3",str(COUNCIL),"--repo-root",str(ROOT),"--preplan",str(pre_path),
      "--branch-topology",str(td/"branch.json"),"--agent-topology",str(td/"agent.json"),
      "--capability-foundry",str(td/"cap.json"),"--policy",str(COUNCIL_POLICY),
      "--reuse-db",str(branch_db),"--architecture-memory-db",str(arch_db),"--output",str(out)
    ],check=True)
    council=json.load(open(out))
    assert council["dispatch_allowed"] is True,council
    assert len(council["mandatory_advisors"])==8,council
    assert council["architecture_memory"]["selected"]["version"]=="system-proven",council
    d=council["decisions"][0]
    assert d["architecture_source"]=="REUSE_REVALIDATED_COMPLETE_ARCHITECTURE",d
    assert d["architecture"]["pattern"]=="proven-static-edge",d
    assert d["mandatory_advisors"]["branch-foundry"]=="PASS"
    assert d["mandatory_advisors"]["agent-foundry"]=="PASS"
    assert d["mandatory_advisors"]["capability-foundry"]=="PASS"
    assert d["mandatory_advisors"]["technology-watch-pre"]=="PASS"
    assert d["mandatory_advisors"]["technology-watch-final"]=="PASS"

    # Accepted delivery learns both branches and complete architecture automatically.
    acceptance_contract={"criteria":[{"criterion_id":"c1","required":True,"dimension":"quality","owner":"qa"}]}
    acceptance_evidence={"criteria":[{"criterion_id":"c1","state":"PASS","evidence":"fixture"}]}
    snapshot={"schema":"chacha.dev/technology-watch-snapshot/v1","generated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"snapshot_digest":"snap-accepted"}
    waves={"schema":"chacha.dev/capsule-wave-plan/v1","waves":[]}
    branch_learn={"schema":"chacha.dev/branch-topology/v1","blocked":[],"decisions":[{
      "package_id":"web","branch_id":"proj:web-ui:primary","domain":"web-ui","kind":"primary",
      "decision":"MATERIALIZE_EPHEMERAL_BRANCH","architecture":{"pattern":"proven-static-edge","runtime":"none"},
      "chosen_cost":{"external_spend_eur":0},"candidate_count":2,"technology_watch":{"consulted":True}
    }]}
    metrics={"project":{"quality_score":99,"latency_ms":100,"memory_mb":256},
             "branches":{"proj:web-ui:primary":{"quality_score":99,"latency_ms":30,"memory_mb":64}}}
    incidents={"project":[],"branches":{"proj:web-ui:primary":[]}}
    docs={
      "contract":acceptance_contract,"evidence":acceptance_evidence,"snapshot":snapshot,"waves":waves,
      "branchlearn":branch_learn,"metrics":metrics,"incidents":incidents
    }
    for n,x in docs.items():(td/(n+".json")).write_text(json.dumps(x))
    acceptance_out=td/"acceptance.json";branch_learning=td/"branch-learning.json";arch_learning=td/"arch-learning.json"
    learned_branch_db=td/"learned-branches.db";learned_arch_db=td/"learned-architectures.db"
    p=subprocess.run([
      "python3",str(ACCEPT),"--contract",str(td/"contract.json"),"--evidence",str(td/"evidence.json"),"--output",str(acceptance_out),
      "--branch-topology",str(td/"branchlearn.json"),"--preplan",str(pre_path),"--technology-snapshot",str(td/"snapshot.json"),
      "--reusable-registry",str(BRANCH_REG),"--reusable-registry-db",str(learned_branch_db),"--learning-output",str(branch_learning),
      "--architecture-council",str(out),"--agent-topology",str(td/"agent.json"),"--capability-foundry",str(td/"cap.json"),
      "--runtime-wave-plan",str(td/"waves.json"),"--architecture-registry",str(ARCH_REG),
      "--architecture-registry-db",str(learned_arch_db),"--architecture-learning-output",str(arch_learning),
      "--metrics",str(td/"metrics.json"),"--incidents",str(td/"incidents.json"),"--learning-nas-mode","DISABLED"
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=90)
    assert p.returncode==0,(p.stdout,p.stderr)
    assert "CHACHA_DEV_V612_ACCEPTANCE_TO_REUSE_MEMORY=PASS" in p.stdout
    assert "CHACHA_DEV_V613_ACCEPTANCE_TO_ARCHITECTURE_MEMORY=PASS" in p.stdout
    learned=json.load(open(arch_learning))
    assert learned["state"]=="ADOPT",learned
    s=subprocess.run(["python3",str(ARCH_REG),"--db",str(learned_arch_db),"search","--preplan",str(pre_path)],
                     stdout=subprocess.PIPE,text=True,check=True)
    found=json.loads(s.stdout)
    assert found["candidates"][0]["reuse_ready"] is True,found
    assert found["candidates"][0]["success_rate"]==1.0,found

orch=(ROOT/"dev-hub/bin/autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert "apply_architecture_council" in orch
assert 'effective_branch_topology=out/"branch-topology-effective.json"' in orch
assert '"--topology",effective_branch_topology' in orch

print("CHACHA_DEV_V613_COMPLETE_ARCHITECTURE_MEMORY=PASS")
print("CHACHA_DEV_V613_CURRENT_FOUNDRIES_STILL_MANDATORY=PASS")
print("CHACHA_DEV_V613_ACCEPTANCE_AUTO_ARCHITECTURE_LEARNING=PASS")
print("CHACHA_DEV_V613_COUNCIL_ARCHITECTURE_EXECUTABLE=PASS")
