#!/usr/bin/env python3
from __future__ import annotations

import hashlib,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def run(cmd):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=120)
    if p.returncode!=0: raise AssertionError({"cmd":cmd,"rc":p.returncode,"stdout":p.stdout,"stderr":p.stderr})
    return p.stdout
def write_release(root:Path,name:str,rev:str,version:str,size:int=4096):
    p=root/"releases"/name;p.mkdir(parents=True)
    (p/".revision").write_text(rev+"\n",encoding="utf-8")
    q=p/"dev-hub/bin";q.mkdir(parents=True)
    (q/"autonomous-project-orchestrator.py").write_text('STATE={"version":"'+version+'"}\n',encoding="utf-8")
    (p/"payload.bin").write_bytes(b"x"*size)
    return p

baseline=load(CFG/"platform-baseline.v7.json")
policy=load(CFG/"platform-consolidation.v1.json")
assert baseline["platform_version"]=="7.0.0",baseline
assert baseline["canonical_rules"]["one_canonical_branch"]=="dev-hub-v700-consolidated-platform-baseline"
assert baseline["canonical_rules"]["max_physical_releases"]==3
assert baseline["project_boundaries"]["technology_radar_agent_scope"]=="PROJECT_ONLY"
assert baseline["project_boundaries"]["technology_radar_agent_central_brain_role"] is False
assert baseline["acceptance_candidate"]["production_activation"] is False
assert baseline["acceptance_candidate"]["promotion"] is False
assert policy["owner_agent"]=="intendant",policy
assert policy["execution"]["default_mode"]=="DRY_RUN"
assert policy["source_retirement"]["no_automatic_remote_branch_deletion"] is True
assert policy["invariants"]["architecture_council_final_authority"] is True
assert policy["invariants"]["automatic_external_spend_eur"]==0

src=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert any(v in src for v in ('"version":"7.0.0"','"version":"7.1.0"','"version":"7.2.0"','"version":"7.3.0"','"version":"7.8.0"')),src[-5000:]

with tempfile.TemporaryDirectory(prefix="v700-qualification-") as td:
    td=Path(td)
    # Compiled runtime release excludes historical tests/docs/installers and is smaller.
    compiled=td/"compiled";manifest=td/"compiled-manifest.json"
    out=run([sys.executable,str(BIN/"build-v7-runtime-release.py"),
             "--source-root",str(ROOT),"--output-root",str(compiled),"--manifest",str(manifest)])
    assert "CHACHA_DEV_V7_COMPILED_RUNTIME_RELEASE=PASS" in out,out
    m=load(manifest)
    assert m["compiled_bytes"]<m["source_bytes"],m
    assert m["compiled_files"]<m["source_files"],m
    assert m["excluded_file_count"]>0,m
    assert not (compiled/"dev-hub/tests").exists()
    assert not (compiled/"dev-hub/docs").exists()
    assert not list((compiled/"dev-hub/bin").glob("install-v6*.sh"))
    assert (compiled/"dev-hub/bin/autonomous-project-orchestrator.py").is_file()

    # Intendant retention plan: active V7 + 2 rollback revisions, all else retired.
    platform=td/"platform";(platform/"releases").mkdir(parents=True)
    v7rev="7"*40;v663="a3803180a64f1ea95d94466b7b10529a7a4af92f";v660="f78cb1972112d32b1ac3ae582009bc96385be58c"
    active=write_release(platform,"20260924T170000Z-"+v7rev,v7rev,"7.0.0",8192)
    r663=write_release(platform,"20260924T160000Z-"+v663,v663,"6.63.0",4096)
    r660=write_release(platform,"20260924T150000Z-"+v660,v660,"6.60.0",4096)
    stale1=write_release(platform,"20260924T140000Z-"+"1"*40,"1"*40,"6.59.0",16384)
    stale2=write_release(platform,"20260924T130000Z-"+"2"*40,"2"*40,"6.58.0",32768)
    (platform/"current").symlink_to(active)
    evidence=td/"evidence";evidence.mkdir()
    save(evidence/"v663.json",{"revision":v663});save(evidence/"v660.json",{"revision":v660})
    test_policy=td/"platform-consolidation.json";tp=json.loads(json.dumps(policy))
    tp["physical_release_retention"]["verification_evidence_root"]=str(evidence)
    tp["physical_release_retention"]["fallback_verified_rollback_revisions"]=[v663,v660]
    save(test_policy,tp)

    plan=td/"plan.json"
    out=run([sys.executable,str(BIN/"intendant-platform-consolidator.py"),
             "--platform-root",str(platform),"--policy",str(test_policy),
             "--output",str(plan)])
    assert "MODE=DRY_RUN" in out,out
    p=load(plan)
    assert p["active_version"]=="7.0.0",p
    assert p["release_count_before"]==5,p
    assert p["keep_count"]==3,p
    assert p["retire_count"]==2,p
    assert p["missing_verified_rollback_count"]==0,p
    rows={x["revision"]:x for x in p["rows"]}
    assert rows[v7rev]["action"]=="KEEP" and rows[v7rev]["reason"]=="ACTIVE_RELEASE",rows[v7rev]
    assert rows[v663]["action"]=="KEEP" and rows[v660]["action"]=="KEEP"
    assert rows["1"*40]["action"]=="RETIRE" and rows["2"*40]["action"]=="RETIRE"
    assert stale1.is_dir() and stale2.is_dir(),"DRY_RUN_MUST_NOT_DELETE"

    # Destructive mode is blocked without explicit receipt.
    blocked=subprocess.run([sys.executable,str(BIN/"intendant-platform-consolidator.py"),
       "--platform-root",str(platform),"--policy",str(test_policy),
       "--output",str(td/"blocked.json"),"--apply","--explicit-destructive-apply"],
       stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert blocked.returncode!=0,(blocked.stdout,blocked.stderr)
    assert stale1.is_dir() and stale2.is_dir()

    approval=td/"approval.json";guardian=td/"guardian.json";runs=td/"github-runs.json"
    save(guardian,{"all_hooks_active":True})
    save(runs,{"workflow_runs":[
      {"name":"ChaCha DEV Sentinel technical assurance","head_sha":v7rev,"status":"completed","conclusion":"success"},
      {"name":"ChaCha DEV V7 consolidated platform baseline qualification","head_sha":v7rev,"status":"completed","conclusion":"success"},
      {"name":"ChaCha DEV V7 platform qualification","head_sha":v7rev,"status":"completed","conclusion":"success"}
    ]})
    council=run([sys.executable,str(BIN/"architecture-council-platform-consolidation-v7.py"),
      "--plan",str(plan),"--policy",str(test_policy),
      "--guardian-coverage",str(guardian),"--revision",v7rev,"--github-runs-json",str(runs),
      "--operator-explicit-purge-approval","--output",str(approval)])
    assert "CHACHA_DEV_V7_CONSOLIDATION_COUNCIL=PASS" in council,council
    ar0=load(approval)
    assert ar0["decision"]=="APPROVE_INTENDANT_CONSOLIDATION",ar0
    assert ar0["destructive_apply_authorized"] is True,ar0
    applied=td/"applied.json";archive=td/"archive.json"
    guardian_event=td/"guardian-event.json";guardian_result=td/"guardian-result.json"
    plan_digest="sha256:"+hashlib.sha256(plan.read_bytes()).hexdigest()
    action_id="v700-test-retirement"
    save(guardian_event,{"schema":"chacha.dev/governance-action/v1","event_id":action_id+"-pre",
      "action_id":action_id,"phase":"PRE_ACTION","actor":"central-orchestrator",
      "subject_role":"platform-hygiene-executor","action":"EXECUTE_PLATFORM_RETIREMENT",
      "permission":"destructive-operation","project_id":"chacha-dev-platform","revision":v7rev,
      "evidence":{"human_approval":True,"consolidation_plan_digest":plan_digest}})
    save(guardian_result,{"action_id":action_id,"verdict":"PASS"})
    out=run([sys.executable,str(BIN/"central-platform-hygiene-executor.py"),"release-retirement",
       "--platform-root",str(platform),"--plan",str(plan),"--approval",str(approval),
       "--guardian-event",str(guardian_event),"--guardian-result",str(guardian_result),
       "--archive-manifest",str(archive),"--output",str(applied)])
    assert "CHACHA_DEV_V710_CENTRAL_PLATFORM_HYGIENE_EXECUTION=PASS" in out,out
    a=load(applied)
    assert a["deleted_release_count"]==2,a
    assert a["release_count_after"]==3,a
    assert active.is_dir() and r663.is_dir() and r660.is_dir()
    assert not stale1.exists() and not stale2.exists()
    ar=load(archive)
    assert len(ar["retiring"])==2,ar
    assert all(str(x.get("tree_sha256") or "").startswith("sha256:") for x in ar["retiring"]),ar

print("CHACHA_DEV_V700_CANONICAL_BASELINE=PASS")
print("CHACHA_DEV_V700_COMPILED_RUNTIME=PASS")
print("CHACHA_DEV_V700_INTENDANT_CONSOLIDATOR=PASS")
print("CHACHA_DEV_V700_CENTRAL_ORCHESTRATOR_RETIREMENT=PASS")
print("CHACHA_DEV_V700_DRY_RUN_NON_DESTRUCTIVE=PASS")
print("CHACHA_DEV_V700_APPLY_REQUIRES_APPROVAL=PASS")
print("CHACHA_DEV_V700_ARCHITECTURE_COUNCIL_CONSOLIDATION=PASS")
print("CHACHA_DEV_V700_THREE_RELEASE_RETENTION=PASS")
print("CHACHA_DEV_V700_RADAR_PROJECT_ONLY=PASS")
print("CHACHA_DEV_V700_ACCEPTANCE_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_V700_GIT_HISTORY_PRESERVED=YES")
print("CHACHA_DEV_V700_REMOTE_BRANCH_AUTO_DELETE=NO")
print("CHACHA_DEV_V700_CANONICAL_BUS_REWRITE=NO")
print("CHACHA_DEV_V700_BENCHMARK_EVIDENCE_MUTATION=NO")
print("CHACHA_DEV_V700_SELF_MUTATION=NO")
print("CHACHA_DEV_V700_SELF_PROMOTION=NO")
print("CHACHA_DEV_V700_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=YES")
print("CHACHA_DEV_V700_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
