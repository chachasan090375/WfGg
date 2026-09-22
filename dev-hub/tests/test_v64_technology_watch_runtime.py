#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess,sys,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))
import technology_watch_runtime as tw

def run(args):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
    if p.returncode!=0:
        raise AssertionError(f"command failed {args}: {p.stdout} {p.stderr}")
    return p.stdout

with tempfile.TemporaryDirectory(prefix="chacha-tech-watch-") as td:
    td=Path(td)
    snap=td/"optimizer-input.json"
    os.environ["CHACHA_TECHNOLOGY_WATCH_SNAPSHOT"]=str(snap)
    full=tw.write_full_snapshot(ROOT)
    assert snap.is_file(),full
    assert full["automatic_external_spend_eur"]==0,full

    pre={
      "schema":"chacha.dev/domain-plan/v1","mode":"focused_change","implementation_allowed":True,
      "intent":"render reusable graphics","packages":[{
        "id":"domain:graphics","domain":"graphics","kind":"primary","roles":["graphics-specialist"],
        "capabilities":["graphics-pipeline"],"toolchain":[]
      }]
    }
    (td/"pre.json").write_text(json.dumps(pre))
    run([sys.executable,str(BIN/"agent-foundry-planner.py"),"--preplan",str(td/"pre.json"),
         "--config",str(CFG/"agent-foundry.v1.json"),"--routing",str(CFG/"agent-routing.v1.json"),
         "--project-id","tech-watch-test","--output",str(td/"agent.json")])
    a=json.loads((td/"agent.json").read_text())
    assert a["technology_watch_consulted"] is True,a
    assert a["decisions"][0]["technology_watch"]["consulted"] is True,a
    assert a["decisions"][0]["technology_watch"]["zero_spend_candidate_available"] is True,a

    run([sys.executable,str(BIN/"branch-foundry-planner.py"),"--preplan",str(td/"pre.json"),
         "--config",str(CFG/"branch-foundry.v1.json"),"--project-id","tech-watch-test",
         "--agent-topology",str(td/"agent.json"),"--output",str(td/"branch.json")])
    b=json.loads((td/"branch.json").read_text())
    assert b["technology_watch_consulted"] is True,b
    assert b["summary"]["external_spend_eur"]==0,b
    assert b["decisions"][0]["technology_watch"]["consulted"] is True,b

    gap={"project_id":"tech-watch-test","missing_capabilities":[{"id":"music-composition","domain":"creative-audio"}]}
    (td/"gap.json").write_text(json.dumps(gap))
    run([sys.executable,str(BIN/"capability-foundry.py"),"--request",str(td/"gap.json"),
         "--policy",str(CFG/"capability-foundry.v1.json"),"--domains",str(CFG/"domain-orchestration.v1.json"),
         "--capabilities",str(CFG/"capability-registry.v1.json"),"--output",str(td/"cap.json")])
    c=json.loads((td/"cap.json").read_text())
    assert c["technology_watch_consulted"] is True,c
    assert c["plans"][0]["technology_watch"]["consulted"] is True,c

    stale=json.loads(snap.read_text())
    stale["generated_at"]="2000-01-01T00:00:00Z"
    snap.write_text(json.dumps(stale))
    feed=tw.consult(ROOT,consumer="branch-foundry",domain="graphics",capabilities=["graphics-pipeline"])
    assert feed["targeted_refresh_performed"] is True,feed
    assert feed["automatic_external_spend_eur"]==0,feed

print("CHACHA_DEV_V64_TECHNOLOGY_WATCH_SERVICE=PASS")
print("CHACHA_DEV_V64_TECHNOLOGY_WATCH_FOUNDRIES=PASS")
print("CHACHA_DEV_V64_TECHNOLOGY_WATCH_ZERO_SPEND=PASS")
print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
