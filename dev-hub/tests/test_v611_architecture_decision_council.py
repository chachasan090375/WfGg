#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
REG=ROOT/"dev-hub/bin/reusable-branch-registry.py"
COUNCIL=ROOT/"dev-hub/bin/architecture-decision-council.py"
POLICY=ROOT/"dev-hub/config/architecture-decision-council.v1.json"
ORCH=ROOT/"dev-hub/bin/autonomous-project-orchestrator.py"

with tempfile.TemporaryDirectory(prefix="chacha-v611-") as td:
    td=Path(td);db=td/"reuse.db"
    rec={
      "branch_id":"generic:web-ui:primary","version":"2.3.0","domain":"web-ui",
      "capabilities":["static-web","browser-automation"],
      "architecture":{"pattern":"static-edge","runtime":"none"},
      "qualification_status":"PASS","state":"ADOPT",
      "technology_revalidated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "technology_snapshot_digest":"test-snapshot","external_spend_eur":0,
      "quality_score":96,"success_count":8,"failure_count":0
    }
    r=td/"record.json";r.write_text(json.dumps(rec))
    subprocess.run(["python3",str(REG),"--db",str(db),"register","--record",str(r)],check=True,stdout=subprocess.DEVNULL)

    pre={"schema":"chacha.dev/domain-plan/v1","intent":{"kind":"build"},"packages":[
      {"id":"pkg-web","domain":"web-ui","kind":"primary","capabilities":["static-web","browser-automation"],"roles":[]}
    ]}
    branch={"schema":"chacha.dev/branch-topology/v1","blocked":[],"decisions":[{
      "package_id":"pkg-web","domain":"web-ui","architecture":{"pattern":"fresh-foundry"},
      "chosen_cost":{"external_spend_eur":0}
    }]}
    agent={"schema":"chacha.dev/agent-topology/v1","decisions":[{
      "package_id":"pkg-web","domain":"web-ui","decision":"TOOL_ONLY","manifest":None
    }]}
    cap={"schema":"chacha.dev/capability-foundry-plan/v1","plans":[],"created_domain_count":0,"created_capability_count":0}
    for name,x in [("pre",pre),("branch",branch),("agent",agent),("cap",cap)]:
        (td/(name+".json")).write_text(json.dumps(x))
    out=td/"council.json"
    subprocess.run([
      "python3",str(COUNCIL),"--repo-root",str(ROOT),
      "--preplan",str(td/"pre.json"),"--branch-topology",str(td/"branch.json"),
      "--agent-topology",str(td/"agent.json"),"--capability-foundry",str(td/"cap.json"),
      "--policy",str(POLICY),"--reuse-db",str(db),"--output",str(out)
    ],check=True)
    x=json.load(open(out))
    assert x["dispatch_allowed"] is True,x
    d=x["decisions"][0]
    assert d["architecture_source"]=="REUSE_REVALIDATED_BRANCH",d
    assert d["selected_reuse"]["version"]=="2.3.0",d
    assert d["technology_watch_pre"]["consumer"]=="architecture-decision-council"
    assert d["technology_watch_final"]["consumer"]=="architecture-decision-council"
    assert len(x["mandatory_advisors"])==7
    assert d["dynamic_expert_advisors"][0]["domain"]=="web-ui"

import importlib.util
spec=importlib.util.spec_from_file_location("tw",ROOT/"dev-hub/bin/technology_watch_runtime.py")
tw=importlib.util.module_from_spec(spec);spec.loader.exec_module(tw)
with tempfile.TemporaryDirectory(prefix="chacha-v611-tax-") as td:
    db=Path(td)/"reuse.db"
    rec={"branch_id":"generic:data:primary","version":"1.0.0","domain":"data-backend","capabilities":["database-sql"],
         "architecture":{"pattern":"sql"},"qualification_status":"PASS","state":"ADOPT",
         "technology_revalidated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"external_spend_eur":0}
    p=Path(td)/"r.json";p.write_text(json.dumps(rec))
    subprocess.run(["python3",str(REG),"--db",str(db),"register","--record",str(p)],check=True,stdout=subprocess.DEVNULL)
    os.environ["CHACHA_REUSABLE_BRANCH_DB"]=str(db)
    snap=tw.build_snapshot(ROOT)
    assert snap["technology_taxonomy"]["known_domain_count"]>0
    assert snap["reusable_branch_taxonomy"]["branch_count"]==1

orch=ORCH.read_text(encoding="utf-8")
assert 'architecture-decision-council.py' in orch
assert 'architecture_decision_allowed' in orch
assert 'final_v["dispatch_allowed"]=bool(final_v.get("dispatch_allowed")) and bool(architecture_council_v.get("dispatch_allowed"))' in orch

print("CHACHA_DEV_V611_REUSABLE_BRANCH_REGISTRY=PASS")
print("CHACHA_DEV_V611_TECHNOLOGY_TAXONOMY=PASS")
print("CHACHA_DEV_V611_DOUBLE_TECHNOLOGY_WATCH=PASS")
print("CHACHA_DEV_V611_ARCHITECTURE_COUNCIL_GATE=PASS")
