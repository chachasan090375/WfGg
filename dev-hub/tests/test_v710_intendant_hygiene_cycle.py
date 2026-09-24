#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,subprocess,sys,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";SYSTEMD=ROOT/"dev-hub/systemd"

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def run(cmd,timeout=120):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
    if p.returncode!=0:raise AssertionError({"cmd":cmd,"rc":p.returncode,"stdout":p.stdout,"stderr":p.stderr})
    return p.stdout
def write_release(root,name,rev,version,size=1024):
    p=root/"releases"/name;p.mkdir(parents=True)
    (p/".revision").write_text(rev+"\n")
    q=p/"dev-hub/bin";q.mkdir(parents=True)
    (q/"autonomous-project-orchestrator.py").write_text('STATE={"version":"'+version+'"}\n')
    (p/"payload.bin").write_bytes(b"x"*size)
    return p
def digest(p):return "sha256:"+hashlib.sha256(Path(p).read_bytes()).hexdigest()

hygiene=load(CFG/"intendant-hygiene-cycle.v1.json")
consolidation=load(CFG/"platform-consolidation.v1.json")
guardian_contracts=load(CFG/"guardian-role-contracts.v1.json")
assert hygiene["scheduler"]["single_timer"] is True
assert hygiene["scheduler"]["poll_interval_minutes"]==60
assert hygiene["cycles"]["LIGHT_DAILY"]["minimum_interval_hours"]==24
assert hygiene["cycles"]["WEEKLY_DRY_RUN"]["minimum_interval_hours"]==168
assert hygiene["cycles"]["MONTHLY_CONSOLIDATION"]["minimum_interval_hours"]==720
assert hygiene["cycles"]["THRESHOLD_WATCH"]["triggers"]["physical_release_count_gt"]==3
assert hygiene["invariants"]["rollback_slots_minimum"]==2
assert hygiene["invariants"]["intendant_direct_mutation"] is False
assert hygiene["invariants"]["physical_mutation_executor"]=="central-orchestrator"
assert hygiene["invariants"]["remote_branch_auto_delete"] is False
assert hygiene["invariants"]["source_code_auto_delete"] is False
assert consolidation["execution"]["planner_owner"]=="intendant"
assert consolidation["execution"]["physical_retirement_executor"]=="central-orchestrator"
assert consolidation["execution"]["intendant_direct_mutation"] is False
contracts=guardian_contracts.get("contracts") or guardian_contracts.get("role_contracts") or []
co=next(x for x in contracts if x["contract_id"]=="component:central-orchestrator")
ph=next(x for x in contracts if x["contract_id"]=="role:platform-hygiene-executor")
assert {"EXECUTE_SAFE_TEMP_CLEANUP","EXECUTE_PLATFORM_RETIREMENT"}<=set(co["allowed_actions"])
assert set(ph["allowed_actions"])=={"EXECUTE_SAFE_TEMP_CLEANUP","EXECUTE_PLATFORM_RETIREMENT"}
assert ph["allowed_permissions"]==["destructive-operation"]
assert not (BIN/"central-retirement-executor.py").exists(),"superseded executor must not remain"

service=(SYSTEMD/"chacha-dev-intendant-hygiene.service").read_text()
timer=(SYSTEMD/"chacha-dev-intendant-hygiene.timer").read_text()
assert "--hygiene-executor /opt/chacha-dev/platform/current/dev-hub/bin/central-platform-hygiene-executor.py" in service
assert "OnCalendar=hourly" in timer and "Persistent=true" in timer
assert "OnUnitActiveSec=" not in timer
assert len(list(SYSTEMD.glob("chacha-dev-intendant-hygiene.timer")))==1
installer=(BIN/"install-v710-intendant-hygiene-cycle.sh").read_text(encoding="utf-8")
assert 'flock -n 9' in installer
assert 'platform-deploy.lock' in installer
assert 'UNIT_MARKER="# ChaCha-DEV-V710-Revision: $REV"' in installer
assert 'grep -Fqx "$UNIT_MARKER" "$TIMER"' in installer
assert 'grep -Fqx "$UNIT_MARKER" "$SERVICE"' in installer
assert 'UNITS_TOUCHED=1' in installer
assert 'CHACHA_DEV_V710_ALREADY_ACTIVE_RECONCILED=PASS' in installer
assert 'NextElapseUSecRealtime' in installer
assert 'CHACHA_DEV_V710_PURGE_COMMITTED=NO_RETIREMENT_NEEDED' in installer
evidence_tail=installer[installer.index("stage evidence"):]
assert '[ "$PURGE_COMMITTED" -eq 1 ]' not in evidence_tail

src=(BIN/"autonomous-project-orchestrator.py").read_text()
assert '"version":"7.1.0"' in src,src[-5000:]

with tempfile.TemporaryDirectory(prefix="v710-hygiene-") as td:
    td=Path(td)
    # Central executor safe-temp path: Intendant plans, Guardian binds, Central Orchestrator deletes.
    safe=td/"safe";safe.mkdir();old=safe/"chacha-old";old.mkdir();(old/"x.bin").write_bytes(b"x"*4096)
    old_ts=time.time()-72*3600;os.utime(old,(old_ts,old_ts));os.utime(old/"x.bin",(old_ts,old_ts))
    hp=json.loads(json.dumps(hygiene))
    hp["cycles"]["LIGHT_DAILY"]["safe_temp_cleanup"]["roots"]=[{"path":str(safe),"glob":"chacha-*"}]
    hp_path=td/"hygiene.json";save(hp_path,hp)
    plan=td/"temp-plan.json"
    save(plan,{"schema":"chacha.dev/safe-temp-cleanup-plan/v1","generated_at":"2026-09-24T00:00:00Z",
      "owner_agent":"intendant","candidates":[{"path":str(old),"size_bytes":4096}],
      "standing_operator_approval":True,"automatic_external_spend_eur":0})
    action="v710-temp-test";event=td/"event.json";result=td/"guardian.json";out=td/"temp-result.json"
    save(event,{"schema":"chacha.dev/governance-action/v1","event_id":action+"-pre","action_id":action,
      "phase":"PRE_ACTION","actor":"central-orchestrator","subject_role":"platform-hygiene-executor",
      "action":"EXECUTE_SAFE_TEMP_CLEANUP","permission":"destructive-operation",
      "evidence":{"human_approval":True,"safe_temp_manifest_digest":digest(plan)}})
    save(result,{"action_id":action,"verdict":"PASS"})
    txt=run([sys.executable,str(BIN/"central-platform-hygiene-executor.py"),"safe-temp-cleanup",
      "--manifest",str(plan),"--hygiene-config",str(hp_path),"--guardian-event",str(event),
      "--guardian-result",str(result),"--output",str(out)])
    assert "CHACHA_DEV_V710_CENTRAL_PLATFORM_HYGIENE_EXECUTION=PASS" in txt
    assert not old.exists(),load(out)
    assert load(out)["deleted_candidate_count"]==1,load(out)

    # Scheduler threshold forces weekly dry-run but does not mutate in dry-run mode.
    platform=td/"platform";(platform/"releases").mkdir(parents=True)
    active_rev="7"*40;prev71="8"*40;v700="b061f1405fc758ff22be241c5c791a3ecb58c9ec";v663="a3803180a64f1ea95d94466b7b10529a7a4af92f";v660="f78cb1972112d32b1ac3ae582009bc96385be58c"
    active=write_release(platform,"20260924T180000Z-"+active_rev,active_rev,"7.1.0")
    duplicate_active=write_release(platform,"20260924T175500Z-duplicate-"+active_rev,active_rev,"7.1.0")
    previous_v71=write_release(platform,"20260924T171500Z-"+prev71,prev71,"7.1.0")
    r700=write_release(platform,"20260924T170000Z-"+v700,v700,"7.0.0")
    # Simulate an old acquired rollback physically restored later than V7.0.
    # Selection must follow acquisition evidence time, not directory timestamp.
    r663=write_release(platform,"20260924T175900Z-restored-"+v663,v663,"6.63.0")
    r660=write_release(platform,"20260924T150000Z-"+v660,v660,"6.60.0")
    (platform/"current").symlink_to(active)
    evidence=td/"evidence";evidence.mkdir()
    save(evidence/"prev71.json",{"revision":prev71,"observed_at":"20260924T162520Z"})
    save(evidence/"v700.json",{"revision":v700,"observed_at":"20260924T153443Z"})
    save(evidence/"v663.json",{"revision":v663,"observed_at":"20260924T144805Z"})
    cp=json.loads(json.dumps(consolidation));cp["physical_release_retention"]["verification_evidence_root"]=str(evidence)
    cp["physical_release_retention"]["fallback_verified_rollback_revisions"]=[v700,v663]
    cp_path=td/"consolidation.json";save(cp_path,cp)
    runtime=td/"runtime";(runtime/"guardian").mkdir(parents=True);save(runtime/"guardian/coverage-latest.json",{"all_hooks_active":True})
    hp2=json.loads(json.dumps(hygiene));hp2["scheduler"]["state_file"]=str(runtime/"intendant/state.json")
    hp2["scheduler"]["report_dir"]=str(runtime/"intendant/reports");hp2["scheduler"]["latest_report"]=str(runtime/"intendant/latest.json")
    hp2["scheduler"]["lock_file"]=str(runtime/"intendant/hygiene.lock")
    hp2["cycles"]["LIGHT_DAILY"]["enabled"]=False;hp2["cycles"]["MONTHLY_CONSOLIDATION"]["enabled"]=False
    hp2["cycles"]["LIGHT_DAILY"]["safe_temp_cleanup"]["roots"]=[{"path":str(td/"none"),"glob":"*"}]
    hp2_path=td/"hygiene-scheduler.json";save(hp2_path,hp2)
    txt=run([sys.executable,str(BIN/"intendant-hygiene-cycle.py"),"--repo-root",str(ROOT),
      "--runtime-root",str(runtime),"--platform-root",str(platform),"--policy",str(hp2_path),
      "--consolidation-policy",str(cp_path),"--guardian-client",str(BIN/"guardian-client.py"),
      "--guardian-policy",str(CFG/"guardian-runtime-policy.v1.json"),
      "--guardian-coverage",str(runtime/"guardian/coverage-latest.json"),
      "--council",str(BIN/"architecture-council-platform-consolidation-v7.py"),
      "--consolidator",str(BIN/"intendant-platform-consolidator.py"),
      "--hygiene-executor",str(BIN/"central-platform-hygiene-executor.py"),
      "--now","2026-09-24T12:00:00Z","--dry-run"])
    assert "CHACHA_DEV_V710_INTENDANT_HYGIENE_CYCLE=PASS" in txt,txt
    latest=load(runtime/"intendant/latest.json")
    assert "RELEASE_OVERAGE" in latest["threshold_reasons"],latest
    weekly=next(x for x in latest["results"] if x["cycle"]=="WEEKLY_DRY_RUN")
    action=next(x for x in weekly["actions"] if x["action"]=="RELEASE_RETIREMENT_DRY_RUN")
    assert action["retire_count"]==3,action
    assert action["selected_rollback_revisions"]==[prev71,v700],action
    assert action.get("rollback_selection_basis")=="PLATFORM_VERSION_THEN_ACQUISITION_EVIDENCE_TIME",action
    assert all(x.exists() for x in (active,duplicate_active,previous_v71,r700,r663,r660)),"dry-run mutated releases"
    assert active_rev not in action["selected_rollback_revisions"],action

    # Forced cycles are exclusive: daily means daily only; monthly remains review-only.
    hp3=json.loads(json.dumps(hygiene))
    hp3["scheduler"]["state_file"]=str(runtime/"intendant/forced-state.json")
    hp3["scheduler"]["report_dir"]=str(runtime/"intendant/forced-reports")
    hp3["scheduler"]["latest_report"]=str(runtime/"intendant/forced-latest.json")
    hp3["scheduler"]["lock_file"]=str(runtime/"intendant/forced.lock")
    hp3["cycles"]["LIGHT_DAILY"]["safe_temp_cleanup"]["roots"]=[{"path":str(td/"none"),"glob":"*"}]
    hp3_path=td/"hygiene-forced.json";save(hp3_path,hp3)
    common=[sys.executable,str(BIN/"intendant-hygiene-cycle.py"),"--repo-root",str(ROOT),
      "--runtime-root",str(runtime),"--platform-root",str(platform),"--policy",str(hp3_path),
      "--consolidation-policy",str(cp_path),"--guardian-client",str(BIN/"guardian-client.py"),
      "--guardian-policy",str(CFG/"guardian-runtime-policy.v1.json"),
      "--guardian-coverage",str(runtime/"guardian/coverage-latest.json"),
      "--council",str(BIN/"architecture-council-platform-consolidation-v7.py"),
      "--consolidator",str(BIN/"intendant-platform-consolidator.py"),
      "--hygiene-executor",str(BIN/"central-platform-hygiene-executor.py"),"--dry-run"]
    txt=run(common+["--force-cycle","LIGHT_DAILY","--now","2026-09-24T13:00:00Z"])
    forced=load(runtime/"intendant/forced-latest.json")
    assert forced["cycles_requested"]==["LIGHT_DAILY"],forced
    txt=run(common+["--force-cycle","MONTHLY_CONSOLIDATION","--now","2026-09-24T14:00:00Z"])
    forced=load(runtime/"intendant/forced-latest.json")
    assert forced["cycles_requested"]==["MONTHLY_CONSOLIDATION"],forced
    monthly=forced["results"][0]["actions"][0]
    assert monthly["action"]=="DEEP_CONSOLIDATION_REVIEW",monthly
    assert monthly["remote_branch_deletion"] is False and monthly["source_code_deletion"] is False,monthly

    # Intendant can never apply its own plan.
    p=td/"manual-plan.json"
    run([sys.executable,str(BIN/"intendant-platform-consolidator.py"),"--platform-root",str(platform),
      "--policy",str(cp_path),"--output",str(p)])
    blocked=subprocess.run([sys.executable,str(BIN/"intendant-platform-consolidator.py"),
      "--platform-root",str(platform),"--policy",str(cp_path),"--output",str(td/"x.json"),"--apply",
      "--explicit-destructive-apply"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert blocked.returncode!=0 and "INTENDANT_DIRECT_MUTATION_FORBIDDEN" in (blocked.stdout+blocked.stderr)

    # Full governed weekly apply: Council -> Guardian PRE -> Central executor -> Guardian POST.
    fake_guardian=td/"fake-guardian.py"
    fake_guardian.write_text("""#!/usr/bin/env python3
import json,sys
event=json.load(open(sys.argv[sys.argv.index('--event')+1]))
assert event['schema']=='chacha.dev/governance-action/v1'
assert event['actor']=='central-orchestrator'
assert event['subject_role']=='platform-hygiene-executor'
assert event['permission']=='destructive-operation'
assert event['phase'] in {'PRE_ACTION','POST_ACTION'}
print(json.dumps({'schema':'chacha.dev/guardian-verdict/v3','event_id':event['event_id'],'action_id':event['action_id'],'verdict':'PASS'}))
""",encoding="utf-8")
    guardian_policy=td/"guardian-policy.json";save(guardian_policy,{})
    runs=td/"github-runs.json";save(runs,{"workflow_runs":[
      {"name":"ChaCha DEV Sentinel technical assurance","head_sha":active_rev,"status":"completed","conclusion":"success"},
      {"name":"ChaCha DEV V7 platform qualification","head_sha":active_rev,"status":"completed","conclusion":"success"}
    ]})
    txt=run([sys.executable,str(BIN/"intendant-hygiene-cycle.py"),"--repo-root",str(ROOT),
      "--runtime-root",str(runtime),"--platform-root",str(platform),"--policy",str(hp2_path),
      "--consolidation-policy",str(cp_path),"--guardian-client",str(fake_guardian),
      "--guardian-policy",str(guardian_policy),"--guardian-coverage",str(runtime/"guardian/coverage-latest.json"),
      "--council",str(BIN/"architecture-council-platform-consolidation-v7.py"),
      "--consolidator",str(BIN/"intendant-platform-consolidator.py"),
      "--hygiene-executor",str(BIN/"central-platform-hygiene-executor.py"),
      "--github-runs-json",str(runs),"--force-cycle","WEEKLY_DRY_RUN","--now","2026-09-24T13:00:00Z"])
    assert "CHACHA_DEV_V710_INTENDANT_HYGIENE_CYCLE=PASS" in txt,txt
    latest=load(runtime/"intendant/latest.json")
    weekly=next(x for x in latest["results"] if x["cycle"]=="WEEKLY_DRY_RUN")
    applied=next(x for x in weekly["actions"] if x["action"]=="SAFE_RELEASE_RETIREMENT_APPLY")
    assert applied["executor"]=="central-orchestrator" and applied["deleted_release_count"]==3,applied
    assert applied["guardian_post_action"] is True,applied
    assert active.is_dir() and previous_v71.is_dir() and r700.is_dir()
    assert not r663.exists() and not r660.exists() and not duplicate_active.exists()
    assert sum(1 for p in (platform/"releases").iterdir() if p.is_dir())==3

print("CHACHA_DEV_V710_SINGLE_HYGIENE_TIMER=PASS")
print("CHACHA_DEV_V710_DEPLOY_SERIALIZATION=PASS")
print("CHACHA_DEV_V710_OWNED_UNIT_ROLLBACK=PASS")
print("CHACHA_DEV_V710_DAILY_LIGHT_CYCLE=PASS")
print("CHACHA_DEV_V710_WEEKLY_DRY_RUN=PASS")
print("CHACHA_DEV_V710_MONTHLY_REVIEW_ONLY=PASS")
print("CHACHA_DEV_V710_THRESHOLD_WATCH=PASS")
print("CHACHA_DEV_V710_DYNAMIC_TWO_ROLLBACK_RETENTION=PASS")
print("CHACHA_DEV_V710_INTENDANT_DIRECT_MUTATION=NO")
print("CHACHA_DEV_V710_PHYSICAL_EXECUTOR=central-orchestrator")
print("CHACHA_DEV_V710_REALTIME_GUARDIAN_GATE=PASS")
print("CHACHA_DEV_V710_GUARDIAN_HYGIENE_CONTRACT=PASS")
print("CHACHA_DEV_V710_COUNCIL_GUARDIAN_PRE_EXECUTOR_POST_CHAIN=PASS")
print("CHACHA_DEV_V710_REMOTE_BRANCH_AUTO_DELETE=NO")
print("CHACHA_DEV_V710_SOURCE_CODE_AUTO_DELETE=NO")
print("CHACHA_DEV_V710_GIT_HISTORY_PRESERVED=YES")
print("CHACHA_DEV_V710_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
