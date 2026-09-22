#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ACCEPT=ROOT/"dev-hub/bin/acceptance-engine.py"
REG=ROOT/"dev-hub/bin/reusable-branch-registry.py"

with tempfile.TemporaryDirectory(prefix="chacha-v612-") as td:
    td=Path(td)
    contract={"criteria":[{"criterion_id":"c1","required":True,"dimension":"quality","owner":"qa"}]}
    evidence={"criteria":[{"criterion_id":"c1","state":"PASS","evidence":"synthetic"}]}
    pre={"schema":"chacha.dev/domain-plan/v1","packages":[{"id":"pkg","domain":"web-ui","kind":"primary","capabilities":["static-web"]}]}
    branch={"schema":"chacha.dev/branch-topology/v1","blocked":[],"decisions":[{
      "package_id":"pkg","branch_id":"project-x:web-ui:primary","domain":"web-ui","kind":"primary",
      "decision":"MATERIALIZE_EPHEMERAL_BRANCH","architecture":{"pattern":"static-edge","runtime":"none"},
      "chosen_cost":{"external_spend_eur":0},"candidate_count":3,"technology_watch":{"consulted":True}
    }]}
    snap={"schema":"chacha.dev/technology-watch-snapshot/v1","generated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"snapshot_digest":"snap-v612"}
    metrics={"branches":{"project-x:web-ui:primary":{"quality_score":98,"latency_ms":42,"memory_mb":64}}}
    incidents={"branches":{"project-x:web-ui:primary":[]}}
    for n,x in [("contract",contract),("evidence",evidence),("pre",pre),("branch",branch),("snap",snap),("metrics",metrics),("incidents",incidents)]:
        (td/(n+".json")).write_text(json.dumps(x))
    out=td/"acceptance.json"; learning=td/"learning.json"; db=td/"reuse.db"
    p=subprocess.run([
      "python3",str(ACCEPT),"--contract",str(td/"contract.json"),"--evidence",str(td/"evidence.json"),"--output",str(out),
      "--branch-topology",str(td/"branch.json"),"--preplan",str(td/"pre.json"),"--technology-snapshot",str(td/"snap.json"),
      "--reusable-registry",str(REG),"--reusable-registry-db",str(db),"--learning-output",str(learning),
      "--metrics",str(td/"metrics.json"),"--incidents",str(td/"incidents.json"),"--learning-nas-mode","DISABLED"
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    assert p.returncode==0,(p.stdout,p.stderr)
    assert "CHACHA_DEV_V612_ACCEPTANCE_TO_REUSE_MEMORY=PASS" in p.stdout
    learned=json.load(open(learning))
    assert learned["registered_count"]==1,learned
    assert learned["registered"][0]["state"]=="ADOPT",learned
    s=subprocess.run(["python3",str(REG),"--db",str(db),"search","--domain","web-ui","--capability","static-web"],
                     stdout=subprocess.PIPE,text=True,check=True)
    found=json.loads(s.stdout)
    assert found["candidates"][0]["reuse_ready"] is True,found
    assert found["candidates"][0]["latency_ms"]==42,found
    assert found["candidates"][0]["memory_mb"]==64,found
    assert found["candidates"][0]["success_rate"]==1.0,found

print("CHACHA_DEV_V612_ACCEPTANCE_AUTO_LEARNING=PASS")
print("CHACHA_DEV_V612_BEST_VERSION_EVIDENCE=PASS")
print("CHACHA_DEV_V612_FAST_REUSE_READY=PASS")
