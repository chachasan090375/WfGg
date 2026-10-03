#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sqlite3, time
from pathlib import Path
from typing import Any

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(x,dict): raise ValueError('JSON_ROOT_NOT_OBJECT:'+str(p))
    return x

def stable(v:Any)->str:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def sha(v:Any)->str:return 'sha256:'+hashlib.sha256((v if isinstance(v,bytes) else str(v).encode())).hexdigest()

def apply_migrations(db:sqlite3.Connection,root:Path)->list[str]:
    db.execute('CREATE TABLE IF NOT EXISTS _sovereign_schema_migrations(name TEXT PRIMARY KEY,digest TEXT NOT NULL,applied_at TEXT NOT NULL)')
    applied=[]
    for p in sorted(root.glob('*.sql')):
        text=p.read_text(encoding='utf-8'); digest=sha(text)
        row=db.execute('SELECT digest FROM _sovereign_schema_migrations WHERE name=?',(p.name,)).fetchone()
        if row:
            if row[0]!=digest: raise RuntimeError('MIGRATION_DIGEST_DRIFT:'+p.name)
            continue
        db.executescript(text)
        db.execute("INSERT INTO _sovereign_schema_migrations(name,digest,applied_at) VALUES(?,?,datetime('now'))",(p.name,digest))
        applied.append(p.name)
    return applied

def seed_identity(db:sqlite3.Connection,identity:dict[str,Any])->None:
    if identity.get('schema')!='chacha.dev/central-learning-public-key/v1':raise ValueError('IDENTITY_SCHEMA_INVALID')
    db.execute("INSERT INTO guardian_identities(key_id,status,public_key_spki_b64,created_at,revoked_at) VALUES(?,?,?,datetime('now'),NULL) ON CONFLICT(key_id) DO UPDATE SET status='ACTIVE',public_key_spki_b64=excluded.public_key_spki_b64,revoked_at=NULL",
      (identity['key_id'],'ACTIVE',identity['public_key_spki_b64']))

def seed_contracts(db:sqlite3.Connection,doc:dict[str,Any])->int:
    if doc.get('schema')!='chacha.dev/guardian-role-contracts/v1':raise ValueError('CONTRACT_SCHEMA_INVALID')
    n=0
    for c in doc.get('contracts') or []:
        normalized={k:c.get(k) for k in ['contract_id','kind','allowed_actions','forbidden_actions','allowed_permissions','required_evidence','unknown_role']}
        digest=sha(stable(normalized))
        db.execute("INSERT INTO role_contracts(contract_id,kind,allowed_actions_json,forbidden_actions_json,allowed_permissions_json,required_evidence_json,unknown_role,source_digest,updated_at) VALUES(?,?,?,?,?,?,?,?,datetime('now')) ON CONFLICT(contract_id) DO UPDATE SET kind=excluded.kind,allowed_actions_json=excluded.allowed_actions_json,forbidden_actions_json=excluded.forbidden_actions_json,allowed_permissions_json=excluded.allowed_permissions_json,required_evidence_json=excluded.required_evidence_json,unknown_role=excluded.unknown_role,source_digest=excluded.source_digest,updated_at=datetime('now') WHERE role_contracts.source_digest<>excluded.source_digest",
          (c['contract_id'],c.get('kind','role'),stable(c.get('allowed_actions') or []),stable(c.get('forbidden_actions') or []),stable(c.get('allowed_permissions') or []),stable(c.get('required_evidence') or []),1 if c.get('unknown_role') else 0,digest))
        n+=1
    return n

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--db',type=Path,required=True);ap.add_argument('--migrations',type=Path,required=True);ap.add_argument('--identity',type=Path,required=True);ap.add_argument('--contracts',type=Path,required=True);ap.add_argument('--receipt',type=Path,required=True);a=ap.parse_args()
    a.db.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(a.db);db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA busy_timeout=5000')
    applied=apply_migrations(db,a.migrations);seed_identity(db,load(a.identity));contracts=seed_contracts(db,load(a.contracts));db.commit()
    tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    identities=db.execute("SELECT count(*) FROM guardian_identities WHERE status='ACTIVE'").fetchone()[0];roles=db.execute('SELECT count(*) FROM role_contracts').fetchone()[0]
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.close()
    digest=sha(a.db.read_bytes())
    out={'schema':'chacha.dev/sovereign-state-bootstrap-receipt/v1','status':'PASS','db':str(a.db),'db_sha256':digest,'migrations_applied':applied,'table_count':len(tables),'active_identity_count':identities,'role_contract_count':roles,'contracts_seen':contracts,'production_activation_authorized':False,'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(out,indent=2)+'\n')
    print('CHACHA_DEV_SOVEREIGN_STATE_BOOTSTRAP=PASS');print('TABLE_COUNT='+str(len(tables)));print('ROLE_CONTRACT_COUNT='+str(roles));print('PRODUCTION_ACTIVATION=NO');return 0
if __name__=='__main__':raise SystemExit(main())
