#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,time
from pathlib import Path

def load(p):return json.loads(Path(p).read_text())
def sha(t):return 'sha256:'+hashlib.sha256(t.encode()).hexdigest()
def migrations(db,root):
 db.execute('create table if not exists _sovereign_schema_migrations(name text primary key,digest text not null,applied_at text not null)');ap=[]
 for p in sorted(Path(root).glob('*.sql')):
  text=p.read_text();dg=sha(text);r=db.execute('select digest from _sovereign_schema_migrations where name=?',(p.name,)).fetchone()
  if r:
   if r[0]!=dg:raise RuntimeError('MIGRATION_DIGEST_DRIFT:'+p.name)
   continue
  db.executescript(text);db.execute("insert into _sovereign_schema_migrations values(?,?,datetime('now'))",(p.name,dg));ap.append(p.name)
 return ap
def identity(db,service,x):
 kid=x['key_id'];pub=x['public_key_spki_b64']
 if service=='guardian':table='guardian_identities';db.execute(f"insert into {table}(key_id,status,public_key_spki_b64,created_at,revoked_at) values(?,'ACTIVE',?,datetime('now'),null) on conflict(key_id) do update set status='ACTIVE',public_key_spki_b64=excluded.public_key_spki_b64,revoked_at=null",(kid,pub))
 elif service=='sentinel':table='sentinel_identities';db.execute(f"insert into {table}(key_id,status,public_key_spki_b64,created_at,revoked_at) values(?,'ACTIVE',?,datetime('now'),null) on conflict(key_id) do update set status='ACTIVE',public_key_spki_b64=excluded.public_key_spki_b64,revoked_at=null",(kid,pub))
 elif service=='assurance-exchange':table='exchange_identities';db.execute(f"insert into {table}(key_id,status,public_key_spki_b64,created_at,revoked_at) values(?,'ACTIVE',?,datetime('now'),null) on conflict(key_id) do update set status='ACTIVE',public_key_spki_b64=excluded.public_key_spki_b64,revoked_at=null",(kid,pub))
 elif service=='learning-relay':table='identities';db.execute("insert into identities(key_id,role,status,public_key_spki_b64,project_id,deployment_id,created_at,revoked_at) values(?,'CENTRAL','ACTIVE',?,null,null,datetime('now'),null) on conflict(key_id) do update set role='CENTRAL',status='ACTIVE',public_key_spki_b64=excluded.public_key_spki_b64,revoked_at=null",(kid,pub))
 else:raise ValueError('SERVICE_UNSUPPORTED')
 return table
def contracts(db,path):
 x=load(path);n=0
 for c in x.get('contracts',[]):
  st=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'))
  dg=sha(st({k:c.get(k) for k in ['contract_id','kind','allowed_actions','forbidden_actions','allowed_permissions','required_evidence','unknown_role']}))
  db.execute("insert into role_contracts(contract_id,kind,allowed_actions_json,forbidden_actions_json,allowed_permissions_json,required_evidence_json,unknown_role,source_digest,updated_at) values(?,?,?,?,?,?,?,?,datetime('now')) on conflict(contract_id) do update set kind=excluded.kind,allowed_actions_json=excluded.allowed_actions_json,forbidden_actions_json=excluded.forbidden_actions_json,allowed_permissions_json=excluded.allowed_permissions_json,required_evidence_json=excluded.required_evidence_json,unknown_role=excluded.unknown_role,source_digest=excluded.source_digest,updated_at=datetime('now') where role_contracts.source_digest<>excluded.source_digest",(c['contract_id'],c.get('kind','role'),st(c.get('allowed_actions',[])),st(c.get('forbidden_actions',[])),st(c.get('allowed_permissions',[])),st(c.get('required_evidence',[])),1 if c.get('unknown_role') else 0,dg));n+=1
 return n
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--service',choices=['guardian','sentinel','assurance-exchange','learning-relay'],required=True);ap.add_argument('--db',type=Path,required=True);ap.add_argument('--migrations',type=Path,required=True);ap.add_argument('--identity',type=Path,required=True);ap.add_argument('--contracts',type=Path);ap.add_argument('--receipt',type=Path,required=True);a=ap.parse_args();a.db.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(a.db);db.execute('pragma journal_mode=wal');db.execute('pragma synchronous=full');db.execute('pragma foreign_keys=on');db.execute('pragma busy_timeout=5000');applied=migrations(db,a.migrations);table=identity(db,a.service,load(a.identity));nc=contracts(db,a.contracts) if a.service=='guardian' and a.contracts else 0;db.commit();nt=db.execute("select count(*) from sqlite_master where type='table' and name not like 'sqlite_%'").fetchone()[0];db.execute('pragma wal_checkpoint(truncate)');db.close();out={'schema':'chacha.dev/sovereign-d1-service-bootstrap/v1','status':'PASS','service':a.service,'db':str(a.db),'identity_table':table,'migrations_applied':applied,'table_count':nt,'role_contract_count':nc,'production_activation_authorized':False,'automatic_external_spend_eur':0,'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(out,indent=2)+'\n');print('CHACHA_DEV_SOVEREIGN_D1_SERVICE_BOOTSTRAP=PASS service='+a.service);return 0
if __name__=='__main__':raise SystemExit(main())
