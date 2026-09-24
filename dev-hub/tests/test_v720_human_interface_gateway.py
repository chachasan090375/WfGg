#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"

def run(cmd,ok=True):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=60)
    if ok and p.returncode!=0:
        raise AssertionError({"cmd":cmd,"rc":p.returncode,"stdout":p.stdout,"stderr":p.stderr})
    return p

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))

policy=load(CFG/"human-interface-gateway.v1.json")
assert policy["component_type"]=="interface-adapter"
assert policy["is_agent"] is False
assert policy["decision_authority"]=="central-orchestrator"
assert policy["routing"]["exact_commands"]=={"allo":"STATUS","go":"CONTINUE","stop":"STOP"}
assert policy["invariants"]["interface_has_no_architecture_authority"] is True
assert policy["invariants"]["interface_has_no_direct_mutation"] is True
assert policy["failure"]["fail_closed"] is True

with tempfile.TemporaryDirectory(prefix="v720-interface-") as raw:
    td=Path(raw);runtime=td/"runtime";runtime.mkdir()
    fake_orch=td/"fake-orchestrator.py"
    fake_orch.write_text("""#!/usr/bin/env python3
import argparse,json
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--repo-root');ap.add_argument('--intent');ap.add_argument('--output-dir');a=ap.parse_args()
out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
c=out/'architecture-decision-council.json';c.write_text(json.dumps({'schema':'chacha.dev/architecture-decision-council/v1','dispatch_allowed':True})+'\\n')
b={'schema':'chacha.dev/autonomous-project-bootstrap/v1','version':'7.2.0','project_id':'gateway-test-project',
   'architecture_decision_allowed':True,'domain_dispatch_allowed':True,'runtime_schedulable':True,
   'central_compromise_found':True,'next_stage':'DOMAIN_FACTORIES','external_spend_eur':0,
   'architecture_decision_council':str(c)}
(out/'bootstrap-result.json').write_text(json.dumps(b,indent=2)+'\\n')
print('FAKE_ORCHESTRATOR=PASS')
""",encoding="utf-8")
    fake_stop=td/"fake-stop.py"
    fake_stop.write_text("""#!/usr/bin/env python3
import argparse,json
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--state');sub=ap.add_subparsers(dest='cmd',required=True)
a=sub.add_parser('activate');a.add_argument('--reason');a.add_argument('--actor')
args=ap.parse_args();p=Path(args.state);p.parent.mkdir(parents=True,exist_ok=True)
x={'schema':'chacha.dev/emergency-stop-state/v1','active':True,'actor':args.actor,'reason':args.reason}
p.write_text(json.dumps(x)+'\\n');print(json.dumps(x))
""",encoding="utf-8")
    bad_orch=td/"bad-orchestrator.py"
    bad_orch.write_text("import sys;print('no brain',file=sys.stderr);raise SystemExit(2)\n",encoding="utf-8")

    common=[sys.executable,str(BIN/"human-interface-gateway.py"),
      "--repo-root",str(ROOT),"--runtime-root",str(runtime),
      "--policy",str(CFG/"human-interface-gateway.v1.json")]

    # INSTRUCTION must invoke central orchestrator and produce a brain receipt.
    out1=runtime/"r1.json"
    p=run(common+["--text","Construis une passerelle d interface gouvernée","--request-id","req-1",
      "--project","chacha-dev-platform","--orchestrator",str(fake_orch),"--output",str(out1)])
    r1=load(out1)
    assert r1["command"]=="INSTRUCTION" and r1["route"]=="CHACHA_DEV",r1
    assert r1["status"]=="PLAN_READY" and r1["authority"]=="central-orchestrator",r1
    assert r1["brain_decision_obtained"] is True,r1
    assert r1["project_id"]=="gateway-test-project",r1
    assert r1["next_action"]=="DOMAIN_FACTORIES",r1
    assert len(r1["evidence_refs"])>=1,r1
    assert r1["interface_direct_technical_decision"] is False
    assert r1["interface_direct_mutation"] is False

    # GO continues the exact prior brain receipt; it creates no new decision.
    out2=runtime/"r2.json"
    p=run(common+["--text","Go","--request-id","req-2","--output",str(out2)])
    r2=load(out2)
    assert r2["command"]=="CONTINUE" and r2["status"]=="CONTINUE_ALLOWED",r2
    assert r2["authority"]=="central-orchestrator-prior-receipt",r2
    assert r2["continuation_of_request_id"]=="req-1",r2
    assert r2["next_action"]=="DOMAIN_FACTORIES",r2
    assert r2["new_technical_decision_created"] is False,r2

    # ALLO is status, not a reconstructed answer from the interface.
    out3=runtime/"r3.json"
    p=run(common+["--text","Allo","--request-id","req-3","--project","chacha-dev-platform","--output",str(out3)])
    r3=load(out3)
    assert r3["command"]=="STATUS" and r3["status"]=="OK",r3
    assert r3["authority"]=="central-orchestrator",r3
    assert r3["status_source"]=="canonical-platform-runtime",r3
    assert r3["interface_direct_technical_decision"] is False

    # STOP uses the existing out-of-band emergency control surface.
    out4=runtime/"r4.json";stop_state=runtime/"control/emergency-stop.json"
    p=run(common+["--text","Stop","--request-id","req-4",
      "--emergency-controller",str(fake_stop),"--emergency-state",str(stop_state),"--output",str(out4)])
    r4=load(out4)
    assert r4["command"]=="STOP" and r4["status"]=="STOP_ACTIVE",r4
    assert r4["authority"]=="emergency-stop-controller",r4
    assert load(stop_state)["active"] is True

    # GENERAL is only direct when explicitly requested and never claims a brain decision.
    out5=runtime/"r5.json"
    p=run(common+["--text","Bonjour","--route","GENERAL","--request-id","req-5","--output",str(out5)])
    r5=load(out5)
    assert r5["status"]=="DIRECT_ALLOWED" and r5["authority"]=="chat-interface",r5
    assert r5["brain_decision_obtained"] is False,r5

    # Brain failure must fail closed; interface cannot substitute its own technical answer.
    out6=runtime/"r6.json"
    p=run(common+["--text","Change l architecture","--request-id","req-6",
      "--orchestrator",str(bad_orch),"--output",str(out6)],ok=False)
    assert p.returncode!=0,p
    r6=load(out6)
    assert r6["status"]=="BRAIN_UNAVAILABLE",r6
    assert r6["brain_decision_obtained"] is False,r6
    assert r6["interface_direct_technical_decision"] is False,r6

    # Journal is append-only and hash chained.
    journal=runtime/"human-interface/audit.jsonl"
    rows=[json.loads(x) for x in journal.read_text().splitlines() if x.strip()]
    assert len(rows)==6,rows
    prev="GENESIS"
    for i,row in enumerate(rows,1):
        assert row["seq"]==i,row
        assert row["previous_event_digest"]==prev,row
        prev=row["event_digest"]

print("CHACHA_DEV_V720_HUMAN_INTERFACE_GATEWAY=PASS")
print("CHACHA_DEV_V720_INSTRUCTION_TO_CENTRAL_ORCHESTRATOR=PASS")
print("CHACHA_DEV_V720_GO_CONTINUES_PRIOR_BRAIN_RECEIPT=PASS")
print("CHACHA_DEV_V720_ALLO_CANONICAL_STATUS=PASS")
print("CHACHA_DEV_V720_STOP_OUT_OF_BAND=PASS")
print("CHACHA_DEV_V720_BRAIN_UNAVAILABLE_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V720_INTERFACE_TECHNICAL_DECISION_AUTHORITY=NO")
print("CHACHA_DEV_V720_INTERFACE_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V720_AUDIT_HASH_CHAIN=PASS")
print("CHACHA_DEV_V720_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
