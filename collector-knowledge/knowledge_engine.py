#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import mimetypes
import re
import sqlite3
import struct
import threading
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

ENGINE_VERSION = "1.0.0"
SCHEMA_VERSION = 1

TEXT_EXTS = {
    ".txt", ".md", ".json", ".xml", ".yaml", ".yml", ".csv", ".tsv",
    ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".htm", ".svg",
    ".lua", ".go", ".py", ".sh", ".ini", ".cfg", ".conf", ".properties",
    ".atlas", ".prefab", ".meta", ".shader", ".mat",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tga", ".dds", ".ktx", ".ktx2"}
AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".m4a", ".aac"}
ANIMATION_EXTS = {".anim", ".controller", ".skel", ".skeleton", ".timeline", ".spine", ".motion"}
ARCHIVE_EXTS = {".apk", ".xapk", ".zip", ".pak", ".bundle", ".assetbundle"}

COMMAND_RE = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){1,5}\b")
REFERENCE_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.(?:png|jpe?g|webp|atlas|json|prefab|anim|controller|skel|wav|ogg|mp3|lua|bytes|assetbundle))", re.I)

@dataclass(frozen=True)
class ArtifactInfo:
    logical_path: str
    sha256: str
    size: int
    mtime_ns: int
    layer: str
    media_type: str

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()

def classify_layer(path: str) -> str:
    p = path.replace("\\", "/").lower()
    ext = Path(p).suffix.lower()
    tokens = set(re.split(r"[/_.-]+", p))
    if ext in IMAGE_EXTS or {"texture", "sprite", "atlas", "icon", "portrait", "graphic"} & tokens:
        return "GRAPHICS"
    if ext in ANIMATION_EXTS or {"animation", "anim", "timeline", "spine", "skeleton", "particle", "effect", "fx"} & tokens:
        return "ANIMATION"
    if ext in AUDIO_EXTS or {"audio", "sound", "music", "voice", "sfx"} & tokens:
        return "AUDIO"
    if {"protocol", "net", "msgs", "message", "socket", "sfs", "command"} & tokens:
        return "PROTOCOL"
    if {"ui", "view", "controller", "screen", "widget", "panel"} & tokens:
        return "UI"
    if {"map", "world", "region", "zone", "tile"} & tokens:
        return "MAP"
    if {"rule", "formula", "buff", "debuff", "season", "rank", "score"} & tokens:
        return "RULES"
    if {"server", "backend", "api", "worker", "service"} & tokens:
        return "BACKEND"
    if {"config", "setting", "localization", "lang", "locale"} & tokens:
        return "CONFIG"
    if ext in ARCHIVE_EXTS:
        return "CONTAINER"
    return "DATA"

def media_type_for(path: Path) -> str:
    if path.suffix.lower() == ".luac":
        return "application/x-lua-bytecode"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"

class KnowledgeDB:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.RLock()
        self.init_schema()

    def init_schema(self) -> None:
        with self._lock, self.db:
            self.db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources(
                    id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,kind TEXT NOT NULL,root TEXT NOT NULL,
                    version TEXT,digest TEXT,enabled INTEGER NOT NULL DEFAULT 1,
                    first_seen TEXT NOT NULL,last_seen TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts(
                    id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    logical_path TEXT NOT NULL,sha256 TEXT NOT NULL,size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,
                    layer TEXT NOT NULL,media_type TEXT NOT NULL,analyzer TEXT NOT NULL,analyzer_version TEXT NOT NULL,
                    status TEXT NOT NULL,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,
                    UNIQUE(source_id,logical_path)
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_sha ON artifacts(sha256);
                CREATE INDEX IF NOT EXISTS idx_artifacts_layer ON artifacts(layer);
                CREATE TABLE IF NOT EXISTS entities(
                    id INTEGER PRIMARY KEY,kind TEXT NOT NULL,canonical_name TEXT NOT NULL,normalized_name TEXT NOT NULL,
                    layer TEXT NOT NULL,version TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,confidence REAL NOT NULL,
                    first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,
                    UNIQUE(kind,normalized_name,version)
                );
                CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(normalized_name);
                CREATE INDEX IF NOT EXISTS idx_entities_layer ON entities(layer);
                CREATE TABLE IF NOT EXISTS evidence(
                    id INTEGER PRIMARY KEY,artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
                    entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,evidence_type TEXT NOT NULL,
                    locator TEXT NOT NULL,excerpt TEXT NOT NULL,digest TEXT NOT NULL,observed_at TEXT NOT NULL,
                    UNIQUE(artifact_id,evidence_type,locator,digest)
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence(entity_id);
                CREATE TABLE IF NOT EXISTS assertions(
                    id INTEGER PRIMARY KEY,subject_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    predicate TEXT NOT NULL,object_value TEXT NOT NULL DEFAULT '',
                    object_entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,confidence REAL NOT NULL,evidence_count INTEGER NOT NULL DEFAULT 0,
                    first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,
                    UNIQUE(subject_entity_id,predicate,object_value,object_entity_id)
                );
                CREATE TABLE IF NOT EXISTS assertion_evidence(
                    assertion_id INTEGER NOT NULL REFERENCES assertions(id) ON DELETE CASCADE,
                    evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
                    PRIMARY KEY(assertion_id,evidence_id)
                );
                CREATE TABLE IF NOT EXISTS edges(
                    id INTEGER PRIMARY KEY,from_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    relation TEXT NOT NULL,to_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,confidence REAL NOT NULL,evidence_count INTEGER NOT NULL DEFAULT 0,
                    first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,
                    UNIQUE(from_entity_id,relation,to_entity_id)
                );
                CREATE TABLE IF NOT EXISTS tasks(
                    id INTEGER PRIMARY KEY,task_type TEXT NOT NULL,artifact_id INTEGER REFERENCES artifacts(id) ON DELETE CASCADE,
                    target TEXT NOT NULL,state TEXT NOT NULL,priority INTEGER NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    UNIQUE(task_type,artifact_id,target)
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state,priority DESC,id);
                CREATE TABLE IF NOT EXISTS scan_runs(
                    id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,
                    artifacts_seen INTEGER NOT NULL DEFAULT 0,artifacts_changed INTEGER NOT NULL DEFAULT 0,
                    errors INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            self.db.execute("INSERT OR REPLACE INTO schema_meta(key,value) VALUES('schema_version',?)",(str(SCHEMA_VERSION),))
            self.db.execute("INSERT OR REPLACE INTO schema_meta(key,value) VALUES('engine_version',?)",(ENGINE_VERSION,))

    def upsert_source(self,name,kind,root,version="",digest="") -> int:
        now=now_iso()
        with self._lock,self.db:
            self.db.execute(
                """INSERT INTO sources(name,kind,root,version,digest,first_seen,last_seen)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET kind=excluded.kind,root=excluded.root,
                   version=excluded.version,digest=excluded.digest,last_seen=excluded.last_seen""",
                (name,kind,root,version,digest,now,now))
            return int(self.db.execute("SELECT id FROM sources WHERE name=?",(name,)).fetchone()[0])

    def artifact_state(self,source_id,logical_path):
        return self.db.execute("SELECT id,sha256,mtime_ns,size FROM artifacts WHERE source_id=? AND logical_path=?",
                               (source_id,logical_path)).fetchone()

    def upsert_artifact(self,source_id,info,analyzer,status) -> int:
        now=now_iso()
        with self._lock,self.db:
            self.db.execute(
                """INSERT INTO artifacts(source_id,logical_path,sha256,size,mtime_ns,layer,media_type,
                   analyzer,analyzer_version,status,first_seen,last_seen)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(source_id,logical_path) DO UPDATE SET sha256=excluded.sha256,size=excluded.size,
                   mtime_ns=excluded.mtime_ns,layer=excluded.layer,media_type=excluded.media_type,
                   analyzer=excluded.analyzer,analyzer_version=excluded.analyzer_version,
                   status=excluded.status,last_seen=excluded.last_seen""",
                (source_id,info.logical_path,info.sha256,info.size,info.mtime_ns,info.layer,info.media_type,
                 analyzer,ENGINE_VERSION,status,now,now))
            return int(self.db.execute("SELECT id FROM artifacts WHERE source_id=? AND logical_path=?",
                                       (source_id,info.logical_path)).fetchone()[0])

    def entity(self,kind,name,layer,version="",status="OBSERVED",confidence=1.0) -> int:
        now=now_iso(); norm=normalize_name(name)
        with self._lock,self.db:
            self.db.execute(
                """INSERT INTO entities(kind,canonical_name,normalized_name,layer,version,status,confidence,first_seen,last_seen)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(kind,normalized_name,version) DO UPDATE SET
                   canonical_name=excluded.canonical_name,layer=excluded.layer,
                   confidence=MAX(entities.confidence,excluded.confidence),last_seen=excluded.last_seen""",
                (kind,name,norm,layer,version,status,confidence,now,now))
            return int(self.db.execute("SELECT id FROM entities WHERE kind=? AND normalized_name=? AND version=?",
                                       (kind,norm,version)).fetchone()[0])

    def add_evidence(self,artifact_id,entity_id,evidence_type,locator,excerpt) -> int:
        excerpt=excerpt[:2000]
        digest=sha256_bytes((evidence_type+"\n"+locator+"\n"+excerpt).encode("utf-8","replace"))
        now=now_iso()
        with self._lock,self.db:
            self.db.execute(
                """INSERT OR IGNORE INTO evidence(artifact_id,entity_id,evidence_type,locator,excerpt,digest,observed_at)
                   VALUES(?,?,?,?,?,?,?)""",(artifact_id,entity_id,evidence_type,locator,excerpt,digest,now))
            return int(self.db.execute(
                "SELECT id FROM evidence WHERE artifact_id=? AND evidence_type=? AND locator=? AND digest=?",
                (artifact_id,evidence_type,locator,digest)).fetchone()[0])

    def add_edge(self,from_id,relation,to_id,evidence_id,confidence=0.8) -> None:
        now=now_iso()
        with self._lock,self.db:
            self.db.execute(
                """INSERT INTO edges(from_entity_id,relation,to_entity_id,status,confidence,evidence_count,first_seen,last_seen)
                   VALUES(?,?,?,'OBSERVED',?,1,?,?)
                   ON CONFLICT(from_entity_id,relation,to_entity_id) DO UPDATE SET
                   confidence=MAX(edges.confidence,excluded.confidence),
                   evidence_count=edges.evidence_count+1,last_seen=excluded.last_seen""",
                (from_id,relation,to_id,confidence,now,now))

    def add_assertion(self,subject_id,predicate,value,evidence_id,confidence=0.75) -> None:
        now=now_iso()
        with self._lock,self.db:
            self.db.execute(
                """INSERT INTO assertions(subject_entity_id,predicate,object_value,status,confidence,evidence_count,first_seen,last_seen)
                   VALUES(?,?,?,'OBSERVED',?,1,?,?)
                   ON CONFLICT(subject_entity_id,predicate,object_value,object_entity_id) DO UPDATE SET
                   confidence=MAX(assertions.confidence,excluded.confidence),
                   evidence_count=assertions.evidence_count+1,last_seen=excluded.last_seen""",
                (subject_id,predicate,value,confidence,now,now))
            row=self.db.execute(
                "SELECT id FROM assertions WHERE subject_entity_id=? AND predicate=? AND object_value=? AND object_entity_id IS NULL",
                (subject_id,predicate,value)).fetchone()
            if row:
                self.db.execute("INSERT OR IGNORE INTO assertion_evidence(assertion_id,evidence_id) VALUES(?,?)",
                                (int(row[0]),evidence_id))

    def enqueue(self,task_type,artifact_id,target,priority=10) -> None:
        now=now_iso()
        with self._lock,self.db:
            self.db.execute(
                """INSERT INTO tasks(task_type,artifact_id,target,state,priority,created_at,updated_at)
                   VALUES(?,?,?,'PENDING',?,?,?)
                   ON CONFLICT(task_type,artifact_id,target) DO UPDATE SET
                   priority=MAX(tasks.priority,excluded.priority),
                   state=CASE WHEN tasks.state='DONE' THEN tasks.state ELSE 'PENDING' END,
                   updated_at=excluded.updated_at""",
                (task_type,artifact_id,target,priority,now,now))

    def stats(self):
        tables=("sources","artifacts","entities","evidence","assertions","edges","tasks","scan_runs")
        out={t:int(self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in tables}
        out["pendingTasks"]=int(self.db.execute("SELECT COUNT(*) FROM tasks WHERE state='PENDING'").fetchone()[0])
        out["unknownArtifacts"]=int(self.db.execute("SELECT COUNT(*) FROM artifacts WHERE status='NEEDS_DECODER'").fetchone()[0])
        out["layers"]={r["layer"]:r["n"] for r in self.db.execute(
            "SELECT layer,COUNT(*) n FROM entities GROUP BY layer ORDER BY n DESC")}
        return out

    def search(self,q,limit=25):
        q=q.strip()
        if not q:return []
        like=f"%{q.lower()}%"
        rows=self.db.execute(
            """SELECT e.id,e.kind,e.canonical_name,e.layer,e.version,e.status,e.confidence,
               COUNT(DISTINCT ev.id) evidence_count
               FROM entities e LEFT JOIN evidence ev ON ev.entity_id=e.id
               WHERE e.normalized_name LIKE ?
                  OR EXISTS(SELECT 1 FROM assertions a WHERE a.subject_entity_id=e.id
                            AND (LOWER(a.predicate) LIKE ? OR LOWER(a.object_value) LIKE ?))
                  OR EXISTS(SELECT 1 FROM evidence x WHERE x.entity_id=e.id AND LOWER(x.excerpt) LIKE ?)
               GROUP BY e.id ORDER BY evidence_count DESC,e.confidence DESC,e.canonical_name LIMIT ?""",
            (like,like,like,like,max(1,min(int(limit),100)))).fetchall()
        return [dict(r) for r in rows]

    def entity_detail(self,entity_id):
        e=self.db.execute("SELECT * FROM entities WHERE id=?",(entity_id,)).fetchone()
        if not e:return None
        evidence=[dict(r) for r in self.db.execute(
            """SELECT ev.id,ev.evidence_type,ev.locator,ev.excerpt,ev.digest,ev.observed_at,
               a.logical_path,a.layer FROM evidence ev JOIN artifacts a ON a.id=ev.artifact_id
               WHERE ev.entity_id=? ORDER BY ev.id DESC LIMIT 100""",(entity_id,))]
        assertions=[dict(r) for r in self.db.execute(
            "SELECT predicate,object_value,status,confidence,evidence_count,last_seen FROM assertions WHERE subject_entity_id=? ORDER BY predicate",
            (entity_id,))]
        edges=[dict(r) for r in self.db.execute(
            """SELECT ed.relation,ed.status,ed.confidence,ed.evidence_count,
               x.id target_id,x.kind target_kind,x.canonical_name target_name,x.layer target_layer
               FROM edges ed JOIN entities x ON x.id=ed.to_entity_id
               WHERE ed.from_entity_id=? ORDER BY ed.relation,x.canonical_name""",(entity_id,))]
        return {"entity":dict(e),"assertions":assertions,"edges":edges,"evidence":evidence}

class Analyzer:
    def __init__(self,db,source_id,source_version):
        self.db=db; self.source_id=source_id; self.source_version=source_version

    def scan_file(self,root,path):
        rel=path.relative_to(root).as_posix()
        st=path.stat()
        old=self.db.artifact_state(self.source_id,rel)
        if old and int(old["mtime_ns"])==st.st_mtime_ns and int(old["size"])==st.st_size:
            return False,"UNCHANGED"
        data=path.read_bytes(); digest=sha256_bytes(data)
        if old and old["sha256"]==digest:
            return False,"UNCHANGED"
        layer=classify_layer(rel)
        info=ArtifactInfo(rel,digest,len(data),st.st_mtime_ns,layer,media_type_for(path))
        if data[:4]==b"LWLF": analyzer="lwlf"
        elif path.suffix.lower() in TEXT_EXTS: analyzer="text"
        elif path.suffix.lower() in IMAGE_EXTS: analyzer="image-metadata"
        elif path.suffix.lower() in ANIMATION_EXTS: analyzer="animation-reference"
        else: analyzer="binary-strings"
        aid=self.db.upsert_artifact(self.source_id,info,analyzer,"OBSERVED")
        file_entity=self.db.entity("ARTIFACT",rel,layer,self.source_version)
        self.db.add_evidence(aid,file_entity,"ARTIFACT_DIGEST",rel,digest)
        if analyzer=="lwlf":
            self._analyze_lwlf(aid,file_entity,data)
        elif analyzer=="text":
            self._analyze_text(aid,file_entity,rel,data)
        elif analyzer in {"image-metadata","animation-reference"}:
            self._analyze_asset(aid,file_entity,rel,data)
        else:
            useful=self._analyze_binary_strings(aid,file_entity,rel,data)
            if not useful:
                with self.db.db:
                    self.db.db.execute("UPDATE artifacts SET status='NEEDS_DECODER' WHERE id=?",(aid,))
                self.db.enqueue("DECODE_UNKNOWN_FORMAT",aid,rel,20)
        return True,analyzer

    def _analyze_text(self,aid,file_entity,rel,data):
        text=data.decode("utf-8","replace"); layer=classify_layer(rel)
        for cmd in sorted(set(COMMAND_RE.findall(text)))[:3000]:
            if len(cmd)>120:continue
            eid=self.db.entity("COMMAND_OR_KEY",cmd,"PROTOCOL" if "." in cmd else layer,self.source_version)
            ev=self.db.add_evidence(aid,eid,"STRING_LITERAL",rel,cmd)
            self.db.add_edge(file_entity,"REFERENCES",eid,ev,0.9)
        for ref in sorted(set(REFERENCE_RE.findall(text)))[:3000]:
            target=self.db.entity("ASSET_REFERENCE",ref.replace("\\","/"),classify_layer(ref),self.source_version)
            ev=self.db.add_evidence(aid,target,"ASSET_REFERENCE",rel,ref)
            self.db.add_edge(file_entity,"REFERENCES_ASSET",target,ev,0.85)
        if Path(rel).suffix.lower()==".json":
            try: obj=json.loads(text)
            except Exception: obj=None
            if obj is not None:self._walk_json(aid,file_entity,rel,obj,"$",layer)

    def _walk_json(self,aid,file_entity,rel,obj,locator,layer):
        if isinstance(obj,dict):
            for k,v in list(obj.items())[:10000]:
                key=str(k)
                eid=self.db.entity("FIELD",key,layer,self.source_version)
                ev=self.db.add_evidence(aid,eid,"JSON_FIELD",f"{rel}:{locator}.{key}",repr(v)[:500])
                self.db.add_edge(file_entity,"DECLARES_FIELD",eid,ev,0.95)
                self._walk_json(aid,file_entity,rel,v,locator+"."+key,layer)
        elif isinstance(obj,list):
            for i,v in enumerate(obj[:1000]):
                self._walk_json(aid,file_entity,rel,v,f"{locator}[{i}]",layer)

    def _analyze_asset(self,aid,file_entity,rel,data):
        ext=Path(rel).suffix.lower()
        if ext==".png" and len(data)>=24 and data[:8]==b"\x89PNG\r\n\x1a\n":
            w,h=struct.unpack(">II",data[16:24])
            ev=self.db.add_evidence(aid,file_entity,"IMAGE_DIMENSIONS",rel,f"{w}x{h}")
            self.db.add_assertion(file_entity,"dimensions",f"{w}x{h}",ev,1.0)
        if ext in ANIMATION_EXTS or "anim" in rel.lower() or "timeline" in rel.lower():
            self.db.enqueue("DECODE_ANIMATION",aid,rel,30)
        if ext in IMAGE_EXTS:
            self.db.enqueue("VISUAL_SEMANTIC_INDEX",aid,rel,15)
        self._analyze_binary_strings(aid,file_entity,rel,data)

    def _analyze_binary_strings(self,aid,file_entity,rel,data):
        strings=[m.group(0).decode("ascii","replace") for m in re.finditer(rb"[ -~]{4,}",data)]
        useful=False
        for st in strings[:20000]:
            if COMMAND_RE.fullmatch(st):
                useful=True
                eid=self.db.entity("COMMAND_OR_KEY",st,"PROTOCOL",self.source_version)
                ev=self.db.add_evidence(aid,eid,"BINARY_STRING",rel,st)
                self.db.add_edge(file_entity,"REFERENCES",eid,ev,0.7)
            for ref in REFERENCE_RE.findall(st):
                useful=True
                eid=self.db.entity("ASSET_REFERENCE",ref.replace("\\","/"),classify_layer(ref),self.source_version)
                ev=self.db.add_evidence(aid,eid,"BINARY_ASSET_REFERENCE",rel,ref)
                self.db.add_edge(file_entity,"REFERENCES_ASSET",eid,ev,0.65)
        return useful

    def _analyze_lwlf(self,aid,file_entity,data):
        if len(data)<16:
            self.db.enqueue("DECODE_CORRUPT_LWLF",aid,"LWLF",50); return
        _,file_version,version,count=struct.unpack_from("<4sIII",data,0)
        ev=self.db.add_evidence(aid,file_entity,"LWLF_HEADER","offset:0",f"fileVersion={file_version};version={version};entries={count}")
        self.db.add_assertion(file_entity,"module_count",str(count),ev,1.0)
        pos=16; parsed=0
        for idx in range(count):
            try:
                n,pos=self._read7(data,pos)
                name=data[pos:pos+n].decode("utf-8","replace"); pos+=n
                size=struct.unpack_from("<I",data,pos)[0]; pos+=4
                chunk=data[pos:pos+size]; pos+=size
            except Exception:
                self.db.enqueue("DECODE_LWLF_ENTRY_ERROR",aid,f"entry:{idx}",60); break
            parsed+=1; layer=classify_layer(name)
            mod=self.db.entity("LUA_MODULE",name,layer,self.source_version)
            mev=self.db.add_evidence(aid,mod,"LWLF_MODULE",f"entry:{idx}",f"name={name};size={size};sha256={sha256_bytes(chunk)}")
            self.db.add_edge(file_entity,"CONTAINS_MODULE",mod,mev,1.0)
            strings=[m.group(0).decode("ascii","replace") for m in re.finditer(rb"[ -~]{4,}",chunk)]
            for st in strings[:5000]:
                if COMMAND_RE.fullmatch(st):
                    cmd=self.db.entity("COMMAND",st,"PROTOCOL",self.source_version)
                    cev=self.db.add_evidence(aid,cmd,"LUA_CONSTANT",f"{name}:entry:{idx}",st)
                    self.db.add_edge(mod,"REFERENCES_COMMAND",cmd,cev,0.95)
                elif st.lower() in {"totalnum","totalcount","playercount","playernum","rolecount","rolenum","usercount","serverid","totalscore","totalrank","rankcount","maxrank"}:
                    fld=self.db.entity("FIELD",st,layer,self.source_version)
                    fev=self.db.add_evidence(aid,fld,"LUA_CONSTANT",f"{name}:entry:{idx}",st)
                    self.db.add_edge(mod,"REFERENCES_FIELD",fld,fev,0.9)
            if any(x in name.lower() for x in ("anim","timeline","spine","skeleton","effect","particle")):
                self.db.enqueue("DECODE_LUA_ANIMATION_BEHAVIOR",aid,name,25)
            if layer=="PROTOCOL":
                self.db.enqueue("DECOMPILE_PROTOCOL_MODULE",aid,name,40)
        if parsed!=count:
            self.db.add_assertion(file_entity,"parsed_module_count",str(parsed),ev,0.5)

    @staticmethod
    def _read7(data,off):
        value=0;shift=0
        for _ in range(5):
            b=data[off];off+=1;value|=(b&0x7f)<<shift
            if not b&0x80:return value,off
            shift+=7
        raise ValueError("invalid 7-bit integer")

def scan_source(db,name,kind,root,version=""):
    source_id=db.upsert_source(name,kind,str(root),version)
    analyzer=Analyzer(db,source_id,version)
    with db.db:
        cur=db.db.execute("INSERT INTO scan_runs(source_id,started_at,status) VALUES(?,?,'RUNNING')",(source_id,now_iso()))
        run_id=int(cur.lastrowid)
    seen=changed=errors=0
    if not root.exists(): errors=1
    else:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():continue
            seen+=1
            try:
                did,_=analyzer.scan_file(root,path);changed+=int(did)
            except Exception as exc:
                errors+=1
                rel=path.relative_to(root).as_posix()
                db.enqueue("ANALYSIS_ERROR",None,f"{rel}:{type(exc).__name__}:{exc}",100)
    status="SUCCESS" if errors==0 else "PARTIAL"
    with db.db:
        db.db.execute("UPDATE scan_runs SET finished_at=?,status=?,artifacts_seen=?,artifacts_changed=?,errors=? WHERE id=?",
                      (now_iso(),status,seen,changed,errors,run_id))
    return {"status":status,"seen":seen,"changed":changed,"errors":errors,"runId":run_id}

class APIHandler(http.server.BaseHTTPRequestHandler):
    db=None
    def _json(self,code,payload):
        raw=json.dumps(payload,ensure_ascii=False).encode("utf-8")
        self.send_response(code);self.send_header("content-type","application/json; charset=utf-8")
        self.send_header("content-length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        u=urllib.parse.urlparse(self.path);q=urllib.parse.parse_qs(u.query)
        if u.path=="/knowledge/health":self._json(200,{"ok":True,"engineVersion":ENGINE_VERSION,"readonly":True});return
        if u.path=="/knowledge/stats":self._json(200,{"ok":True,"stats":self.db.stats()});return
        if u.path in {"/knowledge/search","/knowledge/ask"}:
            query=(q.get("q") or [""])[0];limit=int((q.get("limit") or ["25"])[0])
            self._json(200,{"ok":True,"query":query,"results":self.db.search(query,limit)});return
        if u.path=="/knowledge/entity":
            try: entity_id=int((q.get("id") or ["0"])[0])
            except ValueError: entity_id=0
            detail=self.db.entity_detail(entity_id)
            self._json(200 if detail else 404,{"ok":bool(detail),"result":detail});return
        self._json(404,{"ok":False,"error":"NOT_FOUND"})
    def log_message(self,fmt,*args):return

def load_config(path):return json.loads(path.read_text())

def run_worker(config_path):
    cfg=load_config(config_path);db=KnowledgeDB(Path(cfg["database"]))
    interval=max(30,int(cfg.get("intervalSeconds",300)))
    while True:
        for src in cfg.get("sources",[]):
            if not src.get("enabled",True):continue
            result=scan_source(db,str(src["name"]),str(src.get("kind","FILESYSTEM")),Path(src["root"]),str(src.get("version","")))
            print(json.dumps({"collectorKnowledgeScan":src["name"],**result},ensure_ascii=False),flush=True)
        time.sleep(interval)

def serve(config_path):
    cfg=load_config(config_path);db=KnowledgeDB(Path(cfg["database"]))
    APIHandler.db=db;host=str(cfg.get("listenHost","127.0.0.1"));port=int(cfg.get("listenPort",8791))
    server=http.server.ThreadingHTTPServer((host,port),APIHandler)
    print(json.dumps({"collectorKnowledgeAPI":"READY","host":host,"port":port,"readonly":True}),flush=True)
    server.serve_forever()

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--db")
    sub=ap.add_subparsers(dest="cmd",required=True)
    s=sub.add_parser("scan");s.add_argument("--name",required=True);s.add_argument("--kind",default="FILESYSTEM");s.add_argument("--root",required=True);s.add_argument("--version",default="")
    q=sub.add_parser("query");q.add_argument("q");q.add_argument("--limit",type=int,default=25)
    e=sub.add_parser("entity");e.add_argument("id",type=int)
    sub.add_parser("stats")
    w=sub.add_parser("worker");w.add_argument("--config",required=True)
    h=sub.add_parser("serve");h.add_argument("--config",required=True)
    args=ap.parse_args()
    if args.cmd=="worker":run_worker(Path(args.config));return
    if args.cmd=="serve":serve(Path(args.config));return
    if not args.db:raise SystemExit("--db is required")
    db=KnowledgeDB(Path(args.db))
    if args.cmd=="scan":print(json.dumps(scan_source(db,args.name,args.kind,Path(args.root),args.version),ensure_ascii=False))
    elif args.cmd=="query":print(json.dumps({"ok":True,"results":db.search(args.q,args.limit)},ensure_ascii=False,indent=2))
    elif args.cmd=="entity":print(json.dumps({"ok":True,"result":db.entity_detail(args.id)},ensure_ascii=False,indent=2))
    elif args.cmd=="stats":print(json.dumps({"ok":True,"stats":db.stats()},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
