#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/guardian-governed-deploy-transaction-policy/v1"

def load(path:Path)->Any:
    return json.loads(path.read_text(encoding="utf-8"))

def save(path:Path,value:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def sha(path:Path)->str:
    return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()

def ident(value:str)->str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",value):
        raise ValueError("SQL_IDENTIFIER_INVALID:"+value)
    return value

def sql_value(value:Any)->str:
    if value is None:return "NULL"
    if isinstance(value,bool):return "1" if value else "0"
    if isinstance(value,(int,float)):return str(value)
    return "'"+str(value).replace("'","''")+"'"

def plan(policy:dict[str,Any],revision:str,tree:str)->dict[str,Any]:
    if policy.get("schema")!=SCHEMA:raise ValueError("POLICY_SCHEMA_INVALID")
    if not re.fullmatch(r"[0-9a-f]{40}",revision):raise ValueError("REVISION_INVALID")
    if not re.fullmatch(r"[0-9a-f]{40}",tree):raise ValueError("TREE_INVALID")
    return {
      "schema":"chacha.dev/guardian-governed-deploy-plan/v1",
      "status":"PREPARED_NOT_AUTHORIZED","candidate_revision":revision,"candidate_tree":tree,
      "scope":"GUARDIAN_EXTERNAL_PLANE_ONLY","preconditions":policy["required_preconditions"],
      "steps":["CAPTURE_D1_SNAPSHOTS","CAPTURE_WORKER_VERSION","BUILD_D1_RESTORE_SQL",
               "APPLY_ADDITIVE_MIGRATIONS","SYNC_CONTRACTS_AND_COVERAGE","DEPLOY_WORKER",
               "VERIFY_HEALTH_AND_CONTRACTS","APPLY_PREVERIFIED_RECONCILIATIONS"],
      "forbidden":policy["forbidden"],"automatic_external_spend_eur":0
    }

def snapshot_rows(raw:Any)->list[dict[str,Any]]:
    if isinstance(raw,list):
        if raw and isinstance(raw[0],dict) and isinstance(raw[0].get("results"),list):return raw[0]["results"]
        if all(isinstance(x,dict) for x in raw):return raw
    if isinstance(raw,dict) and isinstance(raw.get("results"),list):return raw["results"]
    raise ValueError("D1_SNAPSHOT_FORMAT_INVALID")

def restore_sql(table:str,rows:list[dict[str,Any]])->str:
    table=ident(table);lines=["BEGIN TRANSACTION;",f"DELETE FROM {table};"]
    for row in rows:
        cols=[ident(str(c)) for c in row]
        lines.append(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(sql_value(row[c]) for c in row)});")
    lines.extend(["COMMIT;",""])
    return "\n".join(lines)

def snapshot_manifest(policy:dict[str,Any],snapshot_dir:Path)->dict[str,Any]:
    files=[]
    worker=snapshot_dir/"worker-deployments.json"
    if not worker.is_file():raise ValueError("WORKER_VERSION_SNAPSHOT_MISSING")
    files.append({"kind":"worker_deployments","path":str(worker),"digest":sha(worker)})
    for table in policy.get("snapshot_tables") or []:
        p=snapshot_dir/(str(table)+".json")
        if not p.is_file():raise ValueError("D1_SNAPSHOT_MISSING:"+str(table))
        snapshot_rows(load(p))
        files.append({"kind":"d1_table","table":table,"path":str(p),"digest":sha(p)})
    return {"schema":"chacha.dev/guardian-deploy-snapshot-manifest/v1","status":"PASS","files":files}

def build_restore(policy:dict[str,Any],snapshot_dir:Path,output:Path)->dict[str,Any]:
    manifest=snapshot_manifest(policy,snapshot_dir);parts=[]
    for table in policy.get("snapshot_tables") or []:
        rows=snapshot_rows(load(snapshot_dir/(str(table)+".json")))
        parts.append(restore_sql(str(table),rows))
    output.write_text("\n".join(parts),encoding="utf-8")
    return {"schema":"chacha.dev/guardian-d1-restore/v1","status":"PASS",
            "restore_sql":str(output),"restore_digest":sha(output),"snapshot":manifest}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--policy",type=Path,required=True)
    sub=ap.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("plan");p.add_argument("--revision",required=True);p.add_argument("--tree",required=True);p.add_argument("--output",type=Path,required=True)
    s=sub.add_parser("verify-snapshot");s.add_argument("--snapshot-dir",type=Path,required=True);s.add_argument("--output",type=Path,required=True)
    r=sub.add_parser("build-restore");r.add_argument("--snapshot-dir",type=Path,required=True);r.add_argument("--restore-sql",type=Path,required=True);r.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();policy=load(a.policy)
    if policy.get("schema")!=SCHEMA:raise SystemExit("POLICY_SCHEMA_INVALID")
    if a.cmd=="plan":out=plan(policy,a.revision,a.tree)
    elif a.cmd=="verify-snapshot":out=snapshot_manifest(policy,a.snapshot_dir)
    else:out=build_restore(policy,a.snapshot_dir,a.restore_sql)
    save(a.output,out)
    print("CHACHA_DEV_GUARDIAN_GOVERNED_DEPLOY_TRANSACTION=PASS")
    print("MODE="+a.cmd.upper().replace("-","_"))
    print("PRODUCTION_MUTATION=NO")
    print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
    return 0

if __name__=="__main__":raise SystemExit(main())
