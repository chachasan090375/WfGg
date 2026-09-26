#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,subprocess,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/existing-candidate-resume/v1"
SHA_RE=r"[0-9a-fA-F]{40}"

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def git(repo:Path,*args:str)->tuple[int,str]:
    p=subprocess.run(["git","-C",str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=20)
    return p.returncode,p.stdout.strip()
def one(rx:str,text:str)->str|None:
    m=re.search(rx,text,re.I|re.M)
    return m.group(1).strip() if m else None
def emit(status:str,next_stage:str,**extra:Any)->dict[str,Any]:
    return {"schema":SCHEMA,"observed_at":now_iso(),"status":status,"next_stage":next_stage,
            "automatic_external_spend_eur":0,"mutation_performed":False,**extra}

def inspect(text:str,allowed_root:Path,active_revision_file:Path)->dict[str,Any]:
    low=text.casefold()
    resume_signal=any(x in low for x in ("reprise exacte","reprendre le commit","reprendre le candidat","resume existing candidate","resume exact","continue from the existing candidate"))
    immutable_signal=any(x in low for x in ("ne pas reconstruire","ne pas recommencer","do not rebuild","already built","déjà figé","candidate already built"))
    worktree=one(r"(?:worktree|working tree)(?:\s+[^:\n]{0,50})?\s*:\s*\n?\s*(/[^\s]+)",text)
    candidate=one(r"(?:commit(?:\s+local)?|candidate(?:\s+(?:revision|sha))?)(?:\s+[^:\n]{0,60})?\s*:\s*\n?\s*("+SHA_RE+r")",text)
    expected_tree=one(r"(?:tree(?:\s+(?:exact|sha))?)(?:\s+[^:\n]{0,30})?\s*:\s*\n?\s*("+SHA_RE+r")",text)
    branch=one(r"(?:branche|branch)(?:\s+(?:locale|local|candidate))?\s*:\s*\n?\s*([^\s]+)",text)
    claim={"resume_signal":resume_signal,"immutable_candidate_signal":immutable_signal,"worktree":worktree,
           "candidate_revision":candidate.lower() if candidate else None,"expected_tree":expected_tree.lower() if expected_tree else None,"branch":branch}
    if not (resume_signal and immutable_signal and worktree and candidate and expected_tree):
        return emit("NOT_APPLICABLE","CENTRAL_BOOTSTRAP",claim=claim)
    p=Path(worktree).resolve(); allowed=allowed_root.resolve()
    try:p.relative_to(allowed)
    except ValueError:return emit("BLOCKED","CANDIDATE_WORKTREE_OUTSIDE_ALLOWED_ROOT",claim=claim,worktree=str(p),allowed_root=str(allowed))
    if not p.is_dir() or not (p/".git").exists():
        return emit("BLOCKED","CANDIDATE_WORKTREE_INVALID",claim=claim,worktree=str(p))
    rc,dirty=git(p,"status","--porcelain")
    if rc!=0:return emit("BLOCKED","CANDIDATE_GIT_STATE_UNAVAILABLE",claim=claim,worktree=str(p))
    if dirty:return emit("BLOCKED","CANDIDATE_WORKTREE_DIRTY",claim=claim,worktree=str(p),dirty_entries=dirty.splitlines()[:50])
    rc,head=git(p,"rev-parse","HEAD")
    rc2,tree=git(p,"rev-parse","HEAD^{tree}")
    if rc or rc2 or not re.fullmatch(SHA_RE,head) or not re.fullmatch(SHA_RE,tree):
        return emit("BLOCKED","CANDIDATE_GIT_OBJECT_INVALID",claim=claim,worktree=str(p))
    head=head.lower();tree=tree.lower();candidate=candidate.lower();expected_tree=expected_tree.lower()
    rc3,_=git(p,"cat-file","-e",candidate+"^{commit}")
    if rc3!=0:return emit("BLOCKED","CANDIDATE_REVISION_MISSING",claim=claim,worktree=str(p),actual_revision=head,actual_tree=tree)
    if candidate!=head:
        return emit("BLOCKED","REFRESH_CANDIDATE_REFERENCE",claim=claim,worktree=str(p),provided_revision=candidate,actual_revision=head,actual_tree=tree,reference_state="STALE")
    if expected_tree!=tree:
        return emit("BLOCKED","CANDIDATE_TREE_MISMATCH",claim=claim,worktree=str(p),candidate_revision=head,provided_tree=expected_tree,actual_tree=tree)
    active=None
    if active_revision_file.is_file():active=active_revision_file.read_text(encoding="utf-8").strip().lower()
    if not active or not re.fullmatch(SHA_RE,active or ""):
        return emit("BLOCKED","ACTIVE_BASE_REVISION_UNAVAILABLE",claim=claim,worktree=str(p),candidate_revision=head,candidate_tree=tree)
    rc4,_=git(p,"cat-file","-e",active+"^{commit}")
    if rc4!=0:return emit("BLOCKED","ACTIVE_BASE_NOT_IN_CANDIDATE_REPOSITORY",claim=claim,worktree=str(p),active_revision=active,candidate_revision=head,candidate_tree=tree)
    rc5,_=git(p,"merge-base","--is-ancestor",active,head)
    if rc5!=0:return emit("BLOCKED","CANDIDATE_LINEAGE_INVALID",claim=claim,worktree=str(p),active_revision=active,candidate_revision=head,candidate_tree=tree)
    return emit("READY","EXISTING_CANDIDATE_RELEASE",claim=claim,worktree=str(p),branch=branch,
                active_revision=active,candidate_revision=head,candidate_tree=tree,
                candidate_immutable=True,domain_factories_required=False,new_project_required=False,
                guardian_preserved=True,sentinel_preserved=True,human_production_approval_preserved=True)

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--text",required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--allowed-root",type=Path,default=Path("/opt/chacha-dev/runtime"))
    ap.add_argument("--active-revision-file",type=Path,default=Path("/opt/chacha-dev/platform/current/.revision"))
    a=ap.parse_args(); result=inspect(a.text,a.allowed_root,a.active_revision_file)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result["status"] in {"READY","NOT_APPLICABLE"} else 2

if __name__=="__main__":raise SystemExit(main())
