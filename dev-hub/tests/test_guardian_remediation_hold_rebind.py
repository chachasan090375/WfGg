#!/usr/bin/env python3
from __future__ import annotations
import re, sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
worker=(ROOT/'dev-hub/guardian/worker.js').read_text(encoding='utf-8')
m=re.search(r'`(INSERT INTO remediation_holds.*?WHERE remediation_holds\.active=0)`',worker,re.S)
assert m,'REMEDIATION_HOLD_UPSERT_SQL_MISSING'
sql=m.group(1)
test_sql=re.sub(r'\?[1-7]', '?', sql)
con=sqlite3.connect(':memory:')
con.execute('''CREATE TABLE remediation_holds(
 hold_key TEXT PRIMARY KEY,directive_id TEXT NOT NULL,target_actor TEXT NOT NULL,target_role TEXT NOT NULL,
 project_id TEXT,run_id TEXT,severity TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,cleared_at TEXT)''')
args=('comparative-pilot|platform-global|run-1','remed-1','comparative-pilot','comparative-pilot','platform-global','run-1','BLOCK')
con.execute(test_sql,args); con.commit()
con.execute("UPDATE remediation_holds SET active=0,cleared_at='done' WHERE hold_key=?",(args[0],));con.commit()
args2=(args[0],'remed-2',*args[2:])
con.execute(test_sql,args2);con.commit()
row=con.execute('SELECT directive_id,active,cleared_at FROM remediation_holds WHERE hold_key=?',(args[0],)).fetchone()
assert row==('remed-2',1,None),row
args3=(args[0],'remed-3',*args[2:])
con.execute(test_sql,args3);con.commit()
row=con.execute('SELECT directive_id,active,cleared_at FROM remediation_holds WHERE hold_key=?',(args[0],)).fetchone()
assert row==('remed-2',1,None),row
print('CHACHA_DEV_GUARDIAN_REMEDIATION_HOLD_REBIND=PASS')
print('CHACHA_DEV_GUARDIAN_ACTIVE_HOLD_NOT_OVERWRITTEN=PASS')
