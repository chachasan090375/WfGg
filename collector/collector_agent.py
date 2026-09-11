#!/usr/bin/env python3
import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import incremental_engine as inc

ROOT=os.environ.get('WFGG_COLLECTOR_ROOT','/opt/wfgg-collector')
DB_PATH=os.environ.get('WFGG_COLLECTOR_DB',f'{ROOT}/data/collector.db')
MASTER_DIR=os.environ.get('WFGG_COLLECTOR_MASTER_DIR',f'{ROOT}/data/masters')
HOST=os.environ.get('WFGG_COLLECTOR_HOST','127.0.0.1')
PORT=int(os.environ.get('WFGG_COLLECTOR_PORT','8790'))
DB_LOCK=threading.RLock()


def now_iso():
    return inc.now_iso()


def db():
    c=sqlite3.connect(DB_PATH,timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA busy_timeout=30000')
    return c


def init_db():
    os.makedirs(os.path.dirname(DB_PATH),exist_ok=True)
    os.makedirs(MASTER_DIR,exist_ok=True)
    with DB_LOCK,db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS players(
          game_uid TEXT PRIMARY KEY,pseudo TEXT NOT NULL,server_id TEXT,alliance_id TEXT,
          alliance_tag TEXT,x INTEGER,y INTEGER,hq_level INTEGER,power INTEGER,
          first_seen TEXT NOT NULL,last_seen TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_players_pseudo_nocase ON players(pseudo COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS observations(
          id INTEGER PRIMARY KEY AUTOINCREMENT,game_uid TEXT NOT NULL,observed_at TEXT NOT NULL,
          pseudo TEXT NOT NULL,server_id TEXT,alliance_id TEXT,alliance_tag TEXT,
          x INTEGER,y INTEGER,hq_level INTEGER,power INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_obs_uid_time ON observations(game_uid,observed_at DESC);
        ''')
        inc.ensure_schema(c)


def normalized_player(p):
    uid=str(p.get('gameUid') or p.get('game_uid') or '').strip()
    pseudo=str(p.get('pseudo') or '').strip()
    if not uid or not pseudo:
        raise ValueError('PLAYER_IDENTITY_REQUIRED')
    return {
      'game_uid':uid,'pseudo':pseudo,
      'server_id':str(p.get('serverId') or p.get('server_id') or '').strip(),
      'alliance_id':str(p.get('allianceId') or p.get('alliance_id') or '').strip(),
      'alliance_tag':str(p.get('allianceTag') or p.get('alliance_tag') or '').strip(),
      'x':p.get('x'),'y':p.get('y'),
      'hq_level':p.get('hqLevel') if 'hqLevel' in p else p.get('hq_level'),
      'power':p.get('power'),
      'observed_at':str(p.get('observedAt') or p.get('observed_at') or now_iso())
    }


def ingest_players(rows,cycle_id=None):
    accepted=changed=new=0
    with DB_LOCK,db() as c:
        if cycle_id is not None:
            r=c.execute('SELECT status FROM cycles WHERE id=?',(cycle_id,)).fetchone()
            if not r or r['status']!='RUNNING':
                raise ValueError('CYCLE_NOT_RUNNING')
        for raw in rows:
            if not isinstance(raw,dict):
                continue
            p=normalized_player(raw)
            did_change,is_new,effective=inc.upsert(c,p,cycle_id)
            if did_change:
                c.execute('''INSERT INTO observations(game_uid,observed_at,pseudo,server_id,alliance_id,
                  alliance_tag,x,y,hq_level,power) VALUES(?,?,?,?,?,?,?,?,?,?)''',(
                  p['game_uid'],p['observed_at'],effective['pseudo'],effective['server_id'],effective['alliance_id'],
                  effective['alliance_tag'],effective['x'],effective['y'],effective['hq_level'],effective['power']))
            accepted+=1; changed+=int(did_change); new+=int(is_new)
    return {'accepted':accepted,'changed':changed,'new':new}


def find_player(q):
    with DB_LOCK,db() as c:
        r=c.execute('SELECT * FROM players WHERE game_uid=? OR pseudo=? COLLATE NOCASE ORDER BY last_seen DESC LIMIT 1',(q,q)).fetchone()
    return dict(r) if r else None


def search_players(q,limit):
    limit=max(1,min(100,int(limit)))
    with DB_LOCK,db() as c:
        rows=c.execute('''SELECT * FROM players WHERE pseudo LIKE ? COLLATE NOCASE OR game_uid LIKE ?
          ORDER BY last_seen DESC LIMIT ?''',(f'%{q}%',f'%{q}%',limit)).fetchall()
    return [dict(r) for r in rows]


def master_latest():
    with DB_LOCK,db() as c:
        return inc.latest_master(c)


def master_create(note):
    with DB_LOCK:
        return inc.create_master(DB_PATH,MASTER_DIR,note)


def cycle_start(trigger,query):
    with DB_LOCK,db() as c:
        return inc.start_cycle(c,trigger,query)


def cycle_finish(cid,status,error):
    with DB_LOCK,db() as c:
        return inc.finish_cycle(c,cid,status,error)


def cycle_get(cid):
    with DB_LOCK,db() as c:
        r=c.execute('SELECT * FROM cycles WHERE id=?',(cid,)).fetchone()
    return dict(r) if r else None


def cycle_latest():
    with DB_LOCK,db() as c:
        r=c.execute('SELECT * FROM cycles ORDER BY id DESC LIMIT 1').fetchone()
    return dict(r) if r else None


def cycle_changes(cid,limit):
    limit=max(1,min(2000,int(limit)))
    with DB_LOCK,db() as c:
        rows=c.execute('''SELECT id,cycle_id,game_uid,change_type,before_json,after_json,changed_at
          FROM cycle_changes WHERE cycle_id=? ORDER BY id LIMIT ?''',(cid,limit)).fetchall()
    out=[]
    for r in rows:
        d=dict(r)
        before=d.pop('before_json'); after=d.pop('after_json')
        d['before']=json.loads(before) if before else None
        d['after']=json.loads(after) if after else None
        out.append(d)
    return out


def stats():
    with DB_LOCK,db() as c:
        players=c.execute('SELECT COUNT(*) FROM players').fetchone()[0]
        active=c.execute("SELECT COUNT(*) FROM players WHERE status='ACTIVE'").fetchone()[0]
        observations=c.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        last=c.execute('SELECT MAX(last_seen) FROM players').fetchone()[0]
        m=inc.latest_master(c)
        cy=c.execute('SELECT * FROM cycles ORDER BY id DESC LIMIT 1').fetchone()
    return {'players':players,'activePlayers':active,'observations':observations,'lastSeen':last,
      'master':m,'lastCycle':dict(cy) if cy else None}


class Handler(BaseHTTPRequestHandler):
    server_version='WfGgCollector/2'
    def log_message(self,fmt,*args): return
    def send_json(self,status,obj):
        body=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store')
        self.end_headers(); self.wfile.write(body)
    def read_json(self,max_bytes=2_000_000):
        n=int(self.headers.get('Content-Length','0'))
        if n<=0 or n>max_bytes: raise ValueError('INVALID_BODY_SIZE')
        return json.loads(self.rfile.read(n).decode())
    def do_GET(self):
        u=urlparse(self.path); a=parse_qs(u.query)
        if u.path=='/health': return self.send_json(200,{'ok':True,'service':'wfgg-collector-v2'})
        if u.path=='/stats': return self.send_json(200,stats())
        if u.path=='/master/latest':
            m=master_latest(); return self.send_json(200 if m else 404,{'ok':bool(m),'master':m})
        if u.path=='/cycle/status':
            raw=a.get('id',[''])[0].strip()
            if not raw.isdigit(): return self.send_json(400,{'ok':False,'error':'CYCLE_ID_REQUIRED'})
            cy=cycle_get(int(raw)); return self.send_json(200 if cy else 404,{'ok':bool(cy),'cycle':cy})
        if u.path=='/cycle/latest':
            cy=cycle_latest(); return self.send_json(200 if cy else 404,{'ok':bool(cy),'cycle':cy})
        if u.path=='/cycle/changes':
            raw=a.get('id',[''])[0].strip()
            if not raw.isdigit(): return self.send_json(400,{'ok':False,'error':'CYCLE_ID_REQUIRED'})
            return self.send_json(200,{'ok':True,'changes':cycle_changes(int(raw),a.get('limit',['200'])[0])})
        if u.path=='/player':
            q=a.get('q',[''])[0].strip()
            if not q: return self.send_json(400,{'ok':False,'error':'QUERY_REQUIRED'})
            p=find_player(q); return self.send_json(200 if p else 404,{'ok':bool(p),'player':p})
        if u.path=='/search':
            q=a.get('q',[''])[0].strip()
            if not q: return self.send_json(400,{'ok':False,'error':'QUERY_REQUIRED'})
            return self.send_json(200,{'ok':True,'players':search_players(q,a.get('limit',['20'])[0])})
        self.send_json(404,{'ok':False,'error':'NOT_FOUND'})
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            p=self.read_json()
            if path=='/ingest':
                rows=p if isinstance(p,list) else p.get('players',[p])
                if not isinstance(rows,list): raise ValueError('PLAYERS_LIST_REQUIRED')
                raw=None if isinstance(p,list) else p.get('cycleId')
                cid=int(raw) if raw not in (None,'') else None
                return self.send_json(200,{'ok':True,**ingest_players(rows,cid)})
            if path=='/master/create':
                note=str(p.get('note') or 'initial-master') if isinstance(p,dict) else 'initial-master'
                return self.send_json(200,{'ok':True,'master':master_create(note)})
            if path=='/cycle/start':
                if not isinstance(p,dict): raise ValueError('OBJECT_REQUIRED')
                cy,joined=cycle_start(str(p.get('trigger') or 'MANUAL'),str(p.get('query') or ''))
                return self.send_json(200,{'ok':True,'joined':joined,'cycle':cy})
            if path=='/cycle/finish':
                if not isinstance(p,dict): raise ValueError('OBJECT_REQUIRED')
                cy=cycle_finish(int(p.get('cycleId')),str(p.get('status') or 'SUCCESS'),str(p.get('error') or ''))
                return self.send_json(200,{'ok':True,'cycle':cy})
            self.send_json(404,{'ok':False,'error':'NOT_FOUND'})
        except (ValueError,TypeError,json.JSONDecodeError) as e:
            self.send_json(400,{'ok':False,'error':str(e)})


def main():
    init_db(); ThreadingHTTPServer((HOST,PORT),Handler).serve_forever(poll_interval=.5)

if __name__=='__main__': main()
