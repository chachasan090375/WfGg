#!/usr/bin/env python3
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def ensure_column(c,table,column,ddl):
    cols={r[1] for r in c.execute(f'PRAGMA table_info({table})').fetchall()}
    if column not in cols:
        c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')


def row_state(r):
    return {'game_uid':str(r['game_uid']),'pseudo':r['pseudo'],'server_id':r['server_id'] or '',
      'alliance_id':r['alliance_id'] or '','alliance_tag':r['alliance_tag'] or '',
      'x':r['x'],'y':r['y'],'hq_level':r['hq_level'],'power':r['power']}


def json_state(p):
    keys=('game_uid','pseudo','server_id','alliance_id','alliance_tag','x','y','hq_level','power')
    return json.dumps({k:p.get(k) for k in keys},ensure_ascii=False,sort_keys=True,separators=(',',':'))


def hash_state(p):
    return hashlib.sha256(json_state(p).encode()).hexdigest()


def ensure_schema(c):
    ensure_column(c,'players','state_hash','TEXT')
    ensure_column(c,'players','missing_count','INTEGER NOT NULL DEFAULT 0')
    ensure_column(c,'players','status',"TEXT NOT NULL DEFAULT 'ACTIVE'")
    ensure_column(c,'players','last_change_cycle','INTEGER')
    ensure_column(c,'players','last_enriched','TEXT')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS masters(
      id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,
      player_count INTEGER NOT NULL,observation_count INTEGER NOT NULL,
      db_path TEXT,sha256 TEXT,note TEXT
    );
    CREATE TABLE IF NOT EXISTS master_players(
      master_id INTEGER NOT NULL,game_uid TEXT NOT NULL,state_json TEXT NOT NULL,state_hash TEXT NOT NULL,
      PRIMARY KEY(master_id,game_uid)
    );
    CREATE TABLE IF NOT EXISTS cycles(
      id INTEGER PRIMARY KEY AUTOINCREMENT,trigger TEXT NOT NULL,query TEXT,
      started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,
      players_seen INTEGER NOT NULL DEFAULT 0,new_players INTEGER NOT NULL DEFAULT 0,
      changed_players INTEGER NOT NULL DEFAULT 0,unchanged_players INTEGER NOT NULL DEFAULT 0,
      missing_players INTEGER NOT NULL DEFAULT 0,enriched_players INTEGER NOT NULL DEFAULT 0,error TEXT
    );
    CREATE TABLE IF NOT EXISTS cycle_seen(
      cycle_id INTEGER NOT NULL,game_uid TEXT NOT NULL,state_hash TEXT NOT NULL,
      enriched INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(cycle_id,game_uid)
    );
    CREATE TABLE IF NOT EXISTS cycle_baseline(
      cycle_id INTEGER NOT NULL,game_uid TEXT NOT NULL,state_hash TEXT NOT NULL,state_json TEXT NOT NULL,
      PRIMARY KEY(cycle_id,game_uid)
    );
    CREATE TABLE IF NOT EXISTS cycle_changes(
      id INTEGER PRIMARY KEY AUTOINCREMENT,cycle_id INTEGER NOT NULL,game_uid TEXT NOT NULL,
      change_type TEXT NOT NULL,before_json TEXT,after_json TEXT,changed_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_cycle_changes_cycle ON cycle_changes(cycle_id,id);
    ''')
    rows=c.execute('SELECT * FROM players WHERE state_hash IS NULL OR state_hash=""').fetchall()
    for r in rows:
        c.execute('UPDATE players SET state_hash=? WHERE game_uid=?',(hash_state(row_state(r)),r['game_uid']))


def upsert(c,p,cycle_id=None):
    old=c.execute('SELECT * FROM players WHERE game_uid=?',(p['game_uid'],)).fetchone()
    old_state=row_state(old) if old else None
    effective=dict(p)
    if effective.get('power') is None and old:
        effective['power']=old['power']
    new_state={k:effective.get(k) for k in ('game_uid','pseudo','server_id','alliance_id','alliance_tag','x','y','hq_level','power')}
    new_hash=hash_state(new_state)
    old_hash=(old['state_hash'] if old else None) or (hash_state(old_state) if old else None)
    is_new=old is None
    changed=is_new or old_hash!=new_hash
    reactivated=bool(old and old['status']!='ACTIVE')
    has_profile=p.get('power') is not None
    last_enriched=p['observed_at'] if has_profile else (old['last_enriched'] if old else None)
    c.execute('''
      INSERT INTO players(game_uid,pseudo,server_id,alliance_id,alliance_tag,x,y,hq_level,power,
        first_seen,last_seen,state_hash,missing_count,status,last_change_cycle,last_enriched)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(game_uid) DO UPDATE SET pseudo=excluded.pseudo,server_id=excluded.server_id,
        alliance_id=excluded.alliance_id,alliance_tag=excluded.alliance_tag,x=excluded.x,y=excluded.y,
        hq_level=excluded.hq_level,power=COALESCE(?,players.power),last_seen=excluded.last_seen,
        state_hash=excluded.state_hash,missing_count=0,status='ACTIVE',
        last_change_cycle=CASE WHEN ? THEN excluded.last_change_cycle ELSE players.last_change_cycle END,
        last_enriched=COALESCE(excluded.last_enriched,players.last_enriched)
    ''',(p['game_uid'],effective['pseudo'],effective['server_id'],effective['alliance_id'],effective['alliance_tag'],
      effective['x'],effective['y'],effective['hq_level'],effective['power'],p['observed_at'],p['observed_at'],
      new_hash,0,'ACTIVE',cycle_id if changed or reactivated else None,last_enriched,p.get('power'),1 if changed or reactivated else 0))
    if cycle_id is not None:
        c.execute('''INSERT INTO cycle_seen(cycle_id,game_uid,state_hash,enriched) VALUES(?,?,?,?)
          ON CONFLICT(cycle_id,game_uid) DO UPDATE SET state_hash=excluded.state_hash,
          enriched=MAX(cycle_seen.enriched,excluded.enriched)''',(cycle_id,p['game_uid'],new_hash,1 if has_profile else 0))
        if changed or reactivated:
            kind='NEW' if is_new else ('UPDATED' if changed else 'REACTIVATED')
            c.execute('''INSERT INTO cycle_changes(cycle_id,game_uid,change_type,before_json,after_json,changed_at)
              VALUES(?,?,?,?,?,?)''',(cycle_id,p['game_uid'],kind,json_state(old_state) if old_state else None,
              json_state(new_state),p['observed_at']))
    return changed,is_new,effective


def start_cycle(c,trigger,query=''):
    running=c.execute("SELECT * FROM cycles WHERE status='RUNNING' ORDER BY id DESC LIMIT 1").fetchone()
    if running:
        return dict(running),True
    cur=c.execute("INSERT INTO cycles(trigger,query,started_at,status) VALUES(?,?,?,'RUNNING')",
      ((trigger or 'MANUAL').strip().upper()[:40],(query or '').strip()[:200],now_iso()))
    cid=cur.lastrowid
    for r in c.execute('SELECT * FROM players').fetchall():
        s=row_state(r)
        c.execute('INSERT INTO cycle_baseline(cycle_id,game_uid,state_hash,state_json) VALUES(?,?,?,?)',
          (cid,r['game_uid'],r['state_hash'] or hash_state(s),json_state(s)))
    return dict(c.execute('SELECT * FROM cycles WHERE id=?',(cid,)).fetchone()),False


def finish_cycle(c,cycle_id,status='SUCCESS',error=''):
    status=(status or 'SUCCESS').upper()
    if status not in ('SUCCESS','FAILED'):
        raise ValueError('CYCLE_STATUS_INVALID')
    cy=c.execute('SELECT * FROM cycles WHERE id=?',(cycle_id,)).fetchone()
    if not cy:
        raise ValueError('CYCLE_NOT_FOUND')
    if cy['status']!='RUNNING':
        return dict(cy)

    seen_rows=c.execute('SELECT * FROM players WHERE last_seen>=?',(cy['started_at'],)).fetchall()
    seen_uids={r['game_uid'] for r in seen_rows}
    baseline={r['game_uid']:r for r in c.execute('SELECT * FROM cycle_baseline WHERE cycle_id=?',(cycle_id,)).fetchall()}
    new_uids=[]; changed_uids=[]
    for r in seen_rows:
        b=baseline.get(r['game_uid'])
        if b is None:
            new_uids.append(r['game_uid'])
        elif (r['state_hash'] or hash_state(row_state(r)))!=b['state_hash'] or r['status']!='ACTIVE':
            changed_uids.append(r['game_uid'])

    already={r[0] for r in c.execute('SELECT game_uid FROM cycle_changes WHERE cycle_id=?',(cycle_id,)).fetchall()}
    for uid in new_uids:
        if uid in already: continue
        r=c.execute('SELECT * FROM players WHERE game_uid=?',(uid,)).fetchone()
        c.execute('''INSERT INTO cycle_changes(cycle_id,game_uid,change_type,before_json,after_json,changed_at)
          VALUES(?,?,?,?,?,?)''',(cycle_id,uid,'NEW',None,json_state(row_state(r)),r['last_seen']))
    for uid in changed_uids:
        if uid in already: continue
        r=c.execute('SELECT * FROM players WHERE game_uid=?',(uid,)).fetchone(); b=baseline[uid]
        c.execute('''INSERT INTO cycle_changes(cycle_id,game_uid,change_type,before_json,after_json,changed_at)
          VALUES(?,?,?,?,?,?)''',(cycle_id,uid,'UPDATED',b['state_json'],json_state(row_state(r)),r['last_seen']))
        c.execute('UPDATE players SET last_change_cycle=? WHERE game_uid=?',(cycle_id,uid))

    missing_uids=[uid for uid in baseline if uid not in seen_uids]
    if status=='SUCCESS':
        for uid in missing_uids:
            r=c.execute('SELECT * FROM players WHERE game_uid=?',(uid,)).fetchone()
            if not r: continue
            n=int(r['missing_count'] or 0)+1; st='INACTIVE' if n>=3 else r['status']
            if st!=r['status']:
                js=json_state(row_state(r))
                c.execute('''INSERT INTO cycle_changes(cycle_id,game_uid,change_type,before_json,after_json,changed_at)
                  VALUES(?,?,?,?,?,?)''',(cycle_id,uid,'INACTIVE',js,js,now_iso()))
            c.execute('UPDATE players SET missing_count=?,status=? WHERE game_uid=?',(n,st,uid))
        if seen_uids:
            c.executemany("UPDATE players SET missing_count=0,status='ACTIVE' WHERE game_uid=?",((u,) for u in seen_uids))

    enriched=c.execute('SELECT COUNT(*) FROM players WHERE last_enriched>=?',(cy['started_at'],)).fetchone()[0]
    seen=len(seen_uids); new=len(new_uids); changed=len(changed_uids); missing=len(missing_uids)
    c.execute('''UPDATE cycles SET finished_at=?,status=?,players_seen=?,new_players=?,changed_players=?,
      unchanged_players=?,missing_players=?,enriched_players=?,error=? WHERE id=?''',(
      now_iso(),status,seen,new,changed,max(0,seen-new-changed),missing,enriched,(error or '')[:500],cycle_id))
    return dict(c.execute('SELECT * FROM cycles WHERE id=?',(cycle_id,)).fetchone())


def latest_master(c):
    r=c.execute('SELECT * FROM masters ORDER BY id DESC LIMIT 1').fetchone()
    return dict(r) if r else None


def create_master(db_path,master_dir,note='initial-master'):
    os.makedirs(master_dir,exist_ok=True)
    src=sqlite3.connect(db_path,timeout=30); src.row_factory=sqlite3.Row
    try:
        players=src.execute('SELECT * FROM players ORDER BY game_uid').fetchall()
        obs=src.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        created=now_iso()
        cur=src.execute('INSERT INTO masters(created_at,player_count,observation_count,note) VALUES(?,?,?,?)',
          (created,len(players),obs,note)); mid=cur.lastrowid
        for r in players:
            s=row_state(r)
            src.execute('INSERT INTO master_players(master_id,game_uid,state_json,state_hash) VALUES(?,?,?,?)',
              (mid,r['game_uid'],json_state(s),hash_state(s)))
        src.commit(); stamp=created.replace('-','').replace(':','').replace('.','')
        path=os.path.join(master_dir,f'collector-master-{mid}-{stamp}.db'); tmp=path+'.tmp'
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        dst=sqlite3.connect(tmp)
        try: src.backup(dst)
        finally: dst.close()
        os.replace(tmp,path); h=hashlib.sha256()
        with open(path,'rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
        src.execute('UPDATE masters SET db_path=?,sha256=? WHERE id=?',(path,h.hexdigest(),mid)); src.commit()
        return dict(src.execute('SELECT * FROM masters WHERE id=?',(mid,)).fetchone())
    finally:
        src.close()
