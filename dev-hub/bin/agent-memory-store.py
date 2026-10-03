from __future__ import annotations
import argparse,json,re,sqlite3
from pathlib import Path
from typing import Any
SHA256=re.compile(r'^sha256:[a-f0-9]{64}$')

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(x,dict):raise ValueError('JSON_OBJECT_REQUIRED')
    return x

def connect(path:Path)->sqlite3.Connection:
    path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(path)
    db.execute('''CREATE TABLE IF NOT EXISTS agent_memory(
      memory_id TEXT PRIMARY KEY,memory_key TEXT NOT NULL,memory_type TEXT NOT NULL,trust_state TEXT NOT NULL,
      evidence_count INTEGER NOT NULL,confidence REAL NOT NULL,content_digest TEXT NOT NULL,evidence_refs_json TEXT NOT NULL,
      observed_at TEXT,anti_pattern INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_agent_memory_key ON agent_memory(memory_key)');return db

def validate(record:dict[str,Any])->None:
    if record.get('schema')!='chacha.dev/agent-memory-record/v1':raise ValueError('RECORD_SCHEMA')
    if 'content' in record or 'raw_user_content' in record or 'secret' in record:raise ValueError('RAW_CONTENT_FORBIDDEN')
    for k in ('memory_id','memory_key','memory_type','trust_state','content_digest'):
        if not str(record.get(k) or ''):raise ValueError('FIELD_REQUIRED:'+k)
    if record['memory_type'] not in {'episodic','semantic','procedural'}:raise ValueError('MEMORY_TYPE')
    if not SHA256.fullmatch(str(record['content_digest'])):raise ValueError('CONTENT_DIGEST')
    if not isinstance(record.get('evidence_refs',[]),list):raise ValueError('EVIDENCE_REFS')

def put(db_path:Path,record:dict[str,Any])->dict[str,Any]:
    validate(record);db=connect(db_path)
    with db:
        db.execute('''INSERT INTO agent_memory(memory_id,memory_key,memory_type,trust_state,evidence_count,confidence,content_digest,evidence_refs_json,observed_at,anti_pattern,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(memory_id) DO UPDATE SET memory_key=excluded.memory_key,memory_type=excluded.memory_type,trust_state=excluded.trust_state,evidence_count=excluded.evidence_count,confidence=excluded.confidence,content_digest=excluded.content_digest,evidence_refs_json=excluded.evidence_refs_json,observed_at=excluded.observed_at,anti_pattern=excluded.anti_pattern,updated_at=CURRENT_TIMESTAMP''',
        (record['memory_id'],record['memory_key'],record['memory_type'],record['trust_state'],int(record.get('evidence_count') or 0),float(record.get('confidence') or 0),record['content_digest'],json.dumps(record.get('evidence_refs') or [],separators=(',',':')),record.get('observed_at'),1 if record.get('anti_pattern') else 0))
    db.close();return {'schema':'chacha.dev/agent-memory-store-result/v1','status':'PASS','memory_id':record['memory_id'],'production_mutation':False,'automatic_external_spend_eur':0}

def get(db_path:Path,memory_id:str)->dict[str,Any]|None:
    db=connect(db_path);db.row_factory=sqlite3.Row;row=db.execute('SELECT * FROM agent_memory WHERE memory_id=?',(memory_id,)).fetchone();db.close()
    if not row:return None
    x=dict(row);x['evidence_refs']=json.loads(x.pop('evidence_refs_json'));x['anti_pattern']=bool(x['anti_pattern']);return x

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--db',type=Path,required=True);sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('put');p.add_argument('--record',type=Path,required=True);g=sub.add_parser('get');g.add_argument('--memory-id',required=True);a=ap.parse_args()
    if a.cmd=='put':out=put(a.db,load(a.record))
    else:out={'schema':'chacha.dev/agent-memory-store-read/v1','status':'PASS','record':get(a.db,a.memory_id),'production_mutation':False,'automatic_external_spend_eur':0}
    print(json.dumps(out,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
