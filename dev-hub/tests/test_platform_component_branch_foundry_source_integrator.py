#!/usr/bin/env python3
from __future__ import annotations
import json,os,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ADAPTER=ROOT/"dev-hub/adapters/platform-component-branch-foundry-source-integrator.py"
POLICY=ROOT/"dev-hub/config/platform-component-branch-foundry-source-integrator.v1.json"

def run(argv,cwd=None,env=None,stdin=None):
    return subprocess.run([str(x) for x in argv],cwd=str(cwd) if cwd else None,env=env,
                          input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,check=False,timeout=30)

def git(cwd,*args):
    p=run(["/usr/bin/git",*args],cwd=cwd)
    assert p.returncode==0,(args,p.stdout,p.stderr)
    return p.stdout.strip()

def call(repo,operation,payload,qualification=True):
    env=os.environ.copy()
    env["CHACHA_PLATFORM_SOURCE_INTEGRATOR_POLICY"]=str(POLICY)
    env["CHACHA_PLATFORM_SOURCE_INTEGRATION_REPO"]=str(repo)
    if qualification:
        env["CHACHA_PLATFORM_SOURCE_INTEGRATOR_QUALIFICATION"]="1"
    else:
        env.pop("CHACHA_PLATFORM_SOURCE_INTEGRATOR_QUALIFICATION",None)
    p=run([sys.executable,ADAPTER,operation],env=env,stdin=json.dumps(payload))
    value=json.loads(p.stdout)
    return p,value

with tempfile.TemporaryDirectory(prefix="branch-source-integrator-") as raw:
    td=Path(raw);work=td/"work";bare=td/"source.git"
    work.mkdir()
    git(work,"init","-b","main")
    git(work,"config","user.email","qualification@example.invalid")
    git(work,"config","user.name","ChaCha DEV Qualification")

    (work/"component.txt").write_text("base\n",encoding="utf-8")
    git(work,"add","component.txt");git(work,"commit","-m","base")
    base=git(work,"rev-parse","HEAD")

    (work/"component.txt").write_text("incumbent\n",encoding="utf-8")
    git(work,"commit","-am","incumbent")
    incumbent=git(work,"rev-parse","HEAD")

    (work/"component.txt").write_text("candidate\n",encoding="utf-8")
    git(work,"commit","-am","candidate")
    candidate=git(work,"rev-parse","HEAD")

    git(work,"switch","-c","divergent",base)
    (work/"other.txt").write_text("divergent\n",encoding="utf-8")
    git(work,"add","other.txt");git(work,"commit","-m","divergent")
    divergent=git(work,"rev-parse","HEAD")
    git(work,"switch","main")

    p=run(["/usr/bin/git","clone","--bare",str(work),str(bare)])
    assert p.returncode==0,(p.stdout,p.stderr)

    heads_before=git(bare,"for-each-ref","--format=%(refname) %(objectname)","refs/heads")
    apply={
      "schema":"chacha.dev/platform-component-source-integration-request/v1",
      "handoff_id":"test-handoff","component_id":"central-orchestrator",
      "candidate_owner":"branch-foundry",
      "candidate_revision":candidate,"incumbent_revision":incumbent,
      "candidate_artifact_ref":"git:candidate@"+candidate,
      "incumbent_artifact_ref":"git:incumbent@"+incumbent,
      "apply_mode":"SOURCE_RELEASE_CANDIDATE_INTEGRATION",
      "direct_runtime_mutation":False,"production_activation":False,
      "production_deployment":False,"merge_to_production_branch":False,
      "automatic_external_spend_eur":0
    }

    p1,r1=call(bare,"apply",apply)
    assert p1.returncode==0,(p1.stdout,p1.stderr)
    assert r1["schema"]=="chacha.dev/platform-component-source-integration-receipt/v1",r1
    assert r1["status"]=="PASS" and r1["source_release_candidate_integrated"] is True,r1
    assert r1["candidate_revision"]==candidate and r1["incumbent_revision"]==incumbent,r1
    assert r1["candidate_owner"]=="branch-foundry",r1
    assert r1["idempotent"] is False,r1
    assert r1["release_candidate_ref"]==f"refs/chacha-dev/release-candidates/central-orchestrator/{candidate}",r1
    assert r1["rollback_token"].startswith("sha256:"),r1
    assert r1["direct_runtime_mutation"] is False and r1["production_activation"] is False,r1
    assert r1["production_deployment"] is False and r1["merge_to_production_branch"] is False,r1
    assert git(bare,"rev-parse",r1["release_candidate_ref"])==candidate
    assert git(bare,"for-each-ref","--format=%(refname) %(objectname)","refs/heads")==heads_before

    # Exact replay is idempotent and does not create any branch mutation.
    p2,r2=call(bare,"apply",apply)
    assert p2.returncode==0,(p2.stdout,p2.stderr)
    assert r2["status"]=="PASS" and r2["idempotent"] is True,r2
    assert r2["rollback_token"]==r1["rollback_token"],(r1,r2)
    assert git(bare,"for-each-ref","--format=%(refname) %(objectname)","refs/heads")==heads_before

    rollback={
      "schema":"chacha.dev/platform-component-source-integration-rollback-request/v1",
      "handoff_id":"test-handoff","component_id":"central-orchestrator",
      "candidate_revision":candidate,"incumbent_revision":incumbent,
      "rollback_token":r1["rollback_token"],
      "reason":"qualification","automatic_external_spend_eur":0
    }
    pr,rr=call(bare,"rollback",rollback)
    assert pr.returncode==0,(pr.stdout,pr.stderr)
    assert rr["schema"]=="chacha.dev/platform-component-source-integration-rollback/v1",rr
    assert rr["status"]=="PASS" and rr["rollback_proven"] is True,rr
    assert rr["source_candidate_integration_reverted"] is True,rr
    assert rr["already_reverted"] is False,rr
    verify=run(["/usr/bin/git","--git-dir",bare,"rev-parse","--verify",r1["release_candidate_ref"]])
    assert verify.returncode!=0,(verify.stdout,verify.stderr)
    assert git(bare,"for-each-ref","--format=%(refname) %(objectname)","refs/heads")==heads_before

    # Rollback exact replay is safe/idempotent.
    pr2,rr2=call(bare,"rollback",rollback)
    assert pr2.returncode==0,(pr2.stdout,pr2.stderr)
    assert rr2["status"]=="PASS" and rr2["already_reverted"] is True,rr2

    # Candidate must descend from incumbent.
    bad_desc={**apply,
      "candidate_revision":divergent,
      "candidate_artifact_ref":"git:candidate@"+divergent}
    pd,rd=call(bare,"apply",bad_desc)
    assert pd.returncode==2,rd
    assert "CANDIDATE_NOT_DESCENDANT_OF_INCUMBENT" in rd["reason"],rd

    # Component IDs cannot escape the trusted ref namespace.
    bad_component={**apply,"component_id":"../heads/main"}
    pc,rc=call(bare,"apply",bad_component)
    assert pc.returncode==2,rc
    assert "COMPONENT_ID_INVALID" in rc["reason"],rc

    # Owner and exact artifact bindings are fail-closed.
    bad_owner={**apply,"candidate_owner":"capability-foundry"}
    po,ro=call(bare,"apply",bad_owner)
    assert po.returncode==2 and "CANDIDATE_OWNER_INVALID" in ro["reason"],ro
    bad_artifact={**apply,"candidate_artifact_ref":"git:candidate@"+"0"*40}
    pa,ra=call(bare,"apply",bad_artifact)
    assert pa.returncode==2 and "CANDIDATE_ARTIFACT_REF_MISMATCH" in ra["reason"],ra

    # Repository override cannot be used outside explicit qualification mode.
    pq,rq=call(bare,"apply",apply,qualification=False)
    assert pq.returncode==2,rq
    assert "SOURCE_REPOSITORY_OVERRIDE_QUALIFICATION_ONLY" in rq["reason"],rq

    # Rollback token cannot be forged.
    fake={**rollback,"rollback_token":"sha256:"+"0"*64}
    pf,rf=call(bare,"rollback",fake)
    assert pf.returncode==2 and "ROLLBACK_TOKEN_MISMATCH" in rf["reason"],rf

policy=json.loads(POLICY.read_text(encoding="utf-8"))
assert policy["candidate_owner"]=="branch-foundry",policy
assert policy["repository"]["bare_repository_required"] is True,policy
assert policy["repository"]["working_tree_mutation_forbidden"] is True,policy
assert policy["repository"]["network_access_forbidden"] is True,policy
assert policy["repository"]["push_forbidden"] is True,policy
assert policy["repository"]["merge_forbidden"] is True,policy
assert policy["repository"]["checkout_forbidden"] is True,policy
assert policy["repository"]["production_branch_mutation_forbidden"] is True,policy
assert policy["refs"]["prefix"]=="refs/chacha-dev/release-candidates",policy
assert policy["safety"]["direct_runtime_mutation"] is False,policy
assert policy["safety"]["production_activation"] is False,policy
assert policy["safety"]["production_deployment"] is False,policy
assert policy["safety"]["merge_to_production_branch"] is False,policy
assert policy["safety"]["automatic_external_spend_eur"]==0,policy

source=ADAPTER.read_text(encoding="utf-8")
assert "shell=False" in source
assert "os.system" not in source
assert '["update-ref",ref,candidate,ZERO]' in source
assert '["update-ref","-d",ref,candidate]' in source
assert '["merge-base","--is-ancestor",incumbent,candidate]' in source
assert '["push"' not in source
assert '["checkout"' not in source
assert '["switch"' not in source
assert '["merge",' not in source

print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR=PASS")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_BARE_REPO=YES")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_DESCENDANT_REQUIRED=YES")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_NAMESPACED_REF=PASS")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_IDEMPOTENT=YES")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_ROLLBACK=PASS")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_BRANCH_MUTATION=NO")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_PUSH=NO")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_NETWORK=NO")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_RUNTIME_MUTATION=NO")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_PRODUCTION_ACTIVATION=NO")
print("CHACHA_DEV_BRANCH_FOUNDRY_SOURCE_INTEGRATOR_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
