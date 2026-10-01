#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path
from typing import Any

SCHEMA_FREEZE="chacha.dev/chantier-freeze-receipt/v1"
SCHEMA_TRAIN="chacha.dev/release-train/v1"
SCHEMA_PLAN="chacha.dev/release-train-plan/v1"
SCHEMA_COMPOSITE="chacha.dev/release-train-composite/v1"
HEX40=re.compile(r"^[0-9a-f]{40}$")

def iso()->str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_OBJECT_REQUIRED:"+str(p))
    return x

def atomic(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp")
    t.write_text(json.dumps(x,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8");os.replace(t,p)

def digest_bytes(b:bytes)->str:return "sha256:"+hashlib.sha256(b).hexdigest()
def digest_file(p:Path)->str:return digest_bytes(p.read_bytes())

def run(argv:list[str],cwd:Path|None=None,input_bytes:bytes|None=None)->subprocess.CompletedProcess:
    return subprocess.run(argv,cwd=cwd,input=input_bytes,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)

def git(repo:Path,*args:str)->str:
    p=run(["git","-C",str(repo),*args])
    if p.returncode: raise ValueError("GIT_FAILED:"+" ".join(args)+":"+p.stderr.decode(errors="replace")[-800:])
    return p.stdout.decode().strip()

def refs(rows:list[Any],label:str)->list[dict[str,str]]:
    out=[]
    for raw in rows:
        p=Path(str(raw)).resolve()
        if not p.is_file(): raise ValueError(label+"_MISSING:"+str(p))
        out.append({"path":str(p),"digest":digest_file(p)})
    if not out: raise ValueError(label+"_REQUIRED")
    return out

def policy(path:Path)->dict[str,Any]: return load(path)

def freeze(args)->dict[str,Any]:
    req=load(args.manifest);pol=policy(args.policy);repo=Path(str(req.get("repository") or "")).resolve()
    if not (repo/".git").exists() and not git(repo,"rev-parse","--git-dir"): raise ValueError("REPOSITORY_REQUIRED")
    cid=str(req.get("chantier_id") or "").strip();base=str(req.get("base_revision") or "");cand=str(req.get("candidate_revision") or "")
    if not cid: raise ValueError("CHANTIER_ID_REQUIRED")
    if not HEX40.match(base) or not HEX40.match(cand): raise ValueError("EXACT_SHA_REQUIRED")
    git(repo,"cat-file","-e",base+"^{commit}");git(repo,"cat-file","-e",cand+"^{commit}")
    if git(repo,"merge-base",base,cand)!=base: raise ValueError("BASE_NOT_ANCESTOR")
    deps=[str(x) for x in (req.get("dependencies") or [])]
    if pol.get("independent_chantiers_required") and deps: raise ValueError("DEPENDENCIES_FORBIDDEN_IN_V1")
    changed=[x for x in git(repo,"diff","--name-only",base,cand).splitlines() if x]
    if not changed: raise ValueError("EMPTY_CHANGESET")
    diff=run(["git","-C",str(repo),"diff","--binary",base,cand]).stdout
    ev=refs(list(req.get("evidence_refs") or []),"EVIDENCE")
    rb=req.get("rollback") if isinstance(req.get("rollback"),dict) else {}
    rbrefs=refs(list(rb.get("refs") or []),"ROLLBACK_EVIDENCE")
    budget=req.get("d1_budget") if isinstance(req.get("d1_budget"),dict) else {}
    writes=max(0,int(budget.get("rows_written") or 0));reads=max(0,int(budget.get("rows_read") or 0))
    tree=git(repo,"rev-parse",cand+"^{tree}")
    commits=[x for x in git(repo,"rev-list","--reverse",base+".."+cand).splitlines() if x]
    out={"schema":SCHEMA_FREEZE,"status":"PASS","state":str(pol.get("frozen_state")),"chantier_id":cid,
         "base_revision":base,"candidate_revision":cand,"candidate_tree":tree,"repository":str(repo),
         "changed_files":sorted(changed),"source_commits":commits,"change_set_digest":digest_bytes(diff),"dependencies":deps,
         "evidence":ev,"rollback":{"strategy":str(rb.get("strategy") or "git-revert"),"target_revision":str(rb.get("target_revision") or base),"evidence":rbrefs},
         "d1_budget":{"rows_read":reads,"rows_written":writes},"automatic_external_spend_eur":0,"frozen_at":iso()}
    atomic(args.output,out);return out

def train_init(args)->dict[str,Any]:
    if not HEX40.match(args.base_revision): raise ValueError("EXACT_BASE_SHA_REQUIRED")
    out={"schema":SCHEMA_TRAIN,"status":"OPEN","train_id":args.train_id,"base_revision":args.base_revision,
         "chantiers":[],"automatic_external_spend_eur":0,"created_at":iso()};atomic(args.output,out);return out

def verify_receipt(path:Path,pol:dict[str,Any])->dict[str,Any]:
    r=load(path)
    if r.get("schema")!=SCHEMA_FREEZE or r.get("status")!="PASS" or r.get("state")!=pol.get("frozen_state"): raise ValueError("CHANTIER_NOT_FROZEN")
    for group in (r.get("evidence") or [],(r.get("rollback") or {}).get("evidence") or []):
        for row in group:
            p=Path(row["path"])
            if not p.is_file() or digest_file(p)!=row.get("digest"): raise ValueError("FROZEN_EVIDENCE_DRIFT:"+str(p))
    return r

def train_add(args)->dict[str,Any]:
    pol=policy(args.policy);t=load(args.train);r=verify_receipt(args.chantier_receipt,pol)
    if t.get("schema")!=SCHEMA_TRAIN or t.get("status")!="OPEN": raise ValueError("TRAIN_NOT_OPEN")
    if pol.get("same_baseline_required") and r.get("base_revision")!=t.get("base_revision"): raise ValueError("BASELINE_MISMATCH")
    existing=[x for x in t.get("chantiers") or [] if isinstance(x,dict)]
    if any(x.get("chantier_id")==r.get("chantier_id") for x in existing): raise ValueError("CHANTIER_ALREADY_PRESENT")
    used={f for x in existing for f in (x.get("changed_files") or [])};overlap=sorted(used.intersection(r.get("changed_files") or []))
    if pol.get("file_overlap_forbidden") and overlap: raise ValueError("FILE_OVERLAP:"+",".join(overlap))
    item={"chantier_id":r["chantier_id"],"receipt_path":str(args.chantier_receipt.resolve()),"receipt_digest":digest_file(args.chantier_receipt),
          "candidate_revision":r["candidate_revision"],"candidate_tree":r["candidate_tree"],"changed_files":r["changed_files"],"d1_budget":r["d1_budget"]}
    t["chantiers"]=existing+[item];t["updated_at"]=iso();atomic(args.output,t);return t

def build_plan(train_path:Path,policy_path:Path)->dict[str,Any]:
    pol=policy(policy_path);t=load(train_path)
    if t.get("schema")!=SCHEMA_TRAIN or t.get("status")!="OPEN": raise ValueError("TRAIN_NOT_OPEN")
    rows=[];ledger=[];provenance={};writes=reads=0
    for item in t.get("chantiers") or []:
        p=Path(item["receipt_path"])
        if not p.is_file() or digest_file(p)!=item.get("receipt_digest"): raise ValueError("CHANTIER_RECEIPT_DRIFT:"+str(p))
        r=verify_receipt(p,pol)
        if r.get("base_revision")!=t.get("base_revision"): raise ValueError("BASELINE_DRIFT")
        for f in r.get("changed_files") or []:
            if f in provenance: raise ValueError("FILE_OVERLAP:"+f)
            provenance[f]=r["chantier_id"]
        b=r.get("d1_budget") or {};writes+=int(b.get("rows_written") or 0);reads+=int(b.get("rows_read") or 0);rows.append(r);ledger.append({"chantier_id":r["chantier_id"],"candidate_revision":r["candidate_revision"],"candidate_tree":r["candidate_tree"],"source_commits":r.get("source_commits") or [],"changed_files":r["changed_files"],"change_set_digest":r["change_set_digest"],"evidence":[x["path"] for x in r.get("evidence") or []],"rollback_strategy":(r.get("rollback") or {}).get("strategy"),"rollback_evidence":[x["path"] for x in (r.get("rollback") or {}).get("evidence") or []]})
    if not rows: raise ValueError("TRAIN_EMPTY")
    lim=int(((pol.get("d1_budget") or {}).get("daily_write_limit_rows") or 0));frac=(writes/lim if lim else 0.0)
    if lim and frac>float((pol.get("d1_budget") or {}).get("hard_block_fraction") or 1.0): raise ValueError("D1_WRITE_BUDGET_EXCEEDED")
    return {"schema":SCHEMA_PLAN,"status":"PASS","state":str(pol.get("composite_state")),"train_id":t["train_id"],"base_revision":t["base_revision"],
            "chantier_order":[r["chantier_id"] for r in rows],"chantier_count":len(rows),"chantier_ledger":ledger,"file_provenance":provenance,
            "d1_budget":{"rows_read":reads,"rows_written":writes,"daily_write_limit_rows":lim,"write_fraction":round(frac,6),
                         "warning":bool(lim and frac>=float((pol.get("d1_budget") or {}).get("warning_fraction") or .5))},
            "automatic_external_spend_eur":0,"planned_at":iso()}

def plan(args)->dict[str,Any]:
    out=build_plan(args.train,args.policy);atomic(args.output,out);return out

def compose(args)->dict[str,Any]:
    pol=policy(args.policy);t=load(args.train);pl=build_plan(args.train,args.policy);repo=args.repository.resolve();dest=args.destination.resolve()
    if dest.exists(): raise ValueError("DESTINATION_EXISTS")
    if git(repo,"cat-file","-t",t["base_revision"])!="commit": raise ValueError("BASE_COMMIT_MISSING")
    p=run(["git","-C",str(repo),"worktree","add","--detach",str(dest),t["base_revision"]])
    if p.returncode: raise ValueError("WORKTREE_CREATE_FAILED:"+p.stderr.decode(errors="replace")[-600:])
    commits=[]
    try:
        for item in t.get("chantiers") or []:
            r=verify_receipt(Path(item["receipt_path"]),pol)
            patch=run(["git","-C",str(repo),"diff","--binary",r["base_revision"],r["candidate_revision"]]).stdout
            a=run(["git","-C",str(dest),"apply","--index","--whitespace=nowarn","-"],input_bytes=patch)
            if a.returncode: raise ValueError("PATCH_APPLY_FAILED:"+r["chantier_id"]+":"+a.stderr.decode(errors="replace")[-600:])
            env=os.environ.copy();env.update({"GIT_AUTHOR_NAME":"ChaCha DEV Release Train","GIT_AUTHOR_EMAIL":"release-train@localhost",
                "GIT_COMMITTER_NAME":"ChaCha DEV Release Train","GIT_COMMITTER_EMAIL":"release-train@localhost",
                "GIT_AUTHOR_DATE":r["frozen_at"],"GIT_COMMITTER_DATE":r["frozen_at"]})
            msg=f"release-train({t['train_id']}): {r['chantier_id']}\n\nSource-Candidate: {r['candidate_revision']}\nChange-Set-Digest: {r['change_set_digest']}\n"
            c=subprocess.run(["git","-C",str(dest),"commit","-m",msg],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,check=False)
            if c.returncode: raise ValueError("COMMIT_FAILED:"+r["chantier_id"]+":"+c.stderr.decode(errors="replace")[-600:])
            commits.append({"chantier_id":r["chantier_id"],"train_commit":git(dest,"rev-parse","HEAD"),"rollback":"git revert <train_commit>"})
        head=git(dest,"rev-parse","HEAD");tree=git(dest,"rev-parse","HEAD^{tree}")
        out={"schema":SCHEMA_COMPOSITE,"status":"PASS","state":"COMPOSITE_CANDIDATE_NOT_PROMOTED","train_id":t["train_id"],"base_revision":t["base_revision"],
             "composite_revision":head,"composite_tree":tree,"destination":str(dest),"commits":commits,"plan":pl,
             "production_mutation":False,"automatic_external_spend_eur":0,"composed_at":iso()};atomic(args.output,out);return out
    except Exception:
        subprocess.run(["git","-C",str(repo),"worktree","remove","--force",str(dest)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        raise

def main()->int:
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest="cmd",required=True)
    p=sp.add_parser("freeze");p.add_argument("--manifest",type=Path,required=True);p.add_argument("--policy",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p=sp.add_parser("train-init");p.add_argument("--train-id",required=True);p.add_argument("--base-revision",required=True);p.add_argument("--output",type=Path,required=True)
    p=sp.add_parser("train-add");p.add_argument("--train",type=Path,required=True);p.add_argument("--chantier-receipt",type=Path,required=True);p.add_argument("--policy",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p=sp.add_parser("plan");p.add_argument("--train",type=Path,required=True);p.add_argument("--policy",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p=sp.add_parser("compose");p.add_argument("--train",type=Path,required=True);p.add_argument("--policy",type=Path,required=True);p.add_argument("--repository",type=Path,required=True);p.add_argument("--destination",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:
        out={"freeze":freeze,"train-init":train_init,"train-add":train_add,"plan":plan,"compose":compose}[a.cmd](a)
        print(json.dumps(out,ensure_ascii=False,sort_keys=True));return 0
    except Exception as e:
        print(json.dumps({"schema":"chacha.dev/release-train-error/v1","status":"BLOCK","reason":str(e),"automatic_external_spend_eur":0},ensure_ascii=False));return 20
if __name__=="__main__": raise SystemExit(main())
