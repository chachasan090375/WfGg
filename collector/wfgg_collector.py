#!/usr/bin/env python3
"""WfGg Collector V1.

A small, dependency-free daemon that repeatedly asks the dedicated READONLY
native collector binary for a live wildcard map harvest (query "*"), stores
normalized player-base observations in SQLite, and exposes a localhost-only API
for Radar and diagnostics.

Security invariants:
- the Last War session file is never logged or returned by the API;
- the HTTP server binds to 127.0.0.1 only;
- stderr/stdout from failed native runs are not dumped verbatim;
- only normalized map/player metadata is persisted.
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(os.environ.get("WFGG_COLLECTOR_ROOT", "/opt/wfgg-collector"))
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("WFGG_COLLECTOR_DB", str(DATA_DIR / "collector.db")))
NATIVE = Path(os.environ.get("WFGG_COLLECTOR_NATIVE", str(ROOT / "bin" / "radar-native-collector")))
SESSION = Path(os.environ.get("WFGG_COLLECTOR_SESSION", str(ROOT / "private" / "session.json")))
CAPTURE = Path(os.environ.get("WFGG_COLLECTOR_CAPTURE", "/opt/wfgg-radar/private/lastwar-native-capture.pcap"))
HOST = "127.0.0.1"
PORT = int(os.environ.get("WFGG_COLLECTOR_PORT", "8791"))
SCAN_INTERVAL = max(60, int(os.environ.get("WFGG_COLLECTOR_SCAN_INTERVAL", "900")))
SCAN_TIMEOUT = max(15, int(os.environ.get("WFGG_COLLECTOR_SCAN_TIMEOUT", "90")))
MAX_API_LIMIT = 500

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    player_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT
);
CREATE TABLE IF NOT EXISTS players (
    game_uid TEXT PRIMARY KEY,
    pseudo TEXT NOT NULL,
    pseudo_norm TEXT NOT NULL,
    server_id TEXT,
    alliance_id TEXT,
    alliance_tag TEXT,
    x INTEGER,
    y INTEGER,
    hq_level INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_scan_id INTEGER NOT NULL,
    power INTEGER,
    army_power INTEGER,
    army_kill INTEGER,
    svip_level INTEGER,
    profile_updated_at TEXT,
    FOREIGN KEY(last_scan_id) REFERENCES scans(id)
);
CREATE INDEX IF NOT EXISTS idx_players_pseudo_norm ON players(pseudo_norm);
CREATE INDEX IF NOT EXISTS idx_players_server ON players(server_id);
CREATE INDEX IF NOT EXISTS idx_players_last_seen ON players(last_seen_at DESC);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    game_uid TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    pseudo TEXT NOT NULL,
    server_id TEXT,
    alliance_id TEXT,
    alliance_tag TEXT,
    x INTEGER,
    y INTEGER,
    hq_level INTEGER,
    FOREIGN KEY(scan_id) REFERENCES scans(id)
);
CREATE INDEX IF NOT EXISTS idx_obs_uid_time ON observations(game_uid, observed_at DESC);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_player(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    uid = str(raw.get("gameUid", "")).strip()
    pseudo = str(raw.get("pseudo", "")).strip()
    if not uid or not pseudo:
        return None
    return {
        "game_uid": uid,
        "pseudo": pseudo,
        "pseudo_norm": pseudo.casefold(),
        "server_id": str(raw.get("serverId", "")).strip() or None,
        "alliance_id": str(raw.get("allianceId", "")).strip() or None,
        "alliance_tag": str(raw.get("allianceTag", "")).strip() or None,
        "x": safe_int(raw.get("x")),
        "y": safe_int(raw.get("y")),
        "hq_level": safe_int(raw.get("hqLevel")),
    }


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def begin_scan(self) -> int:
        with self.connect() as db:
            cur = db.execute(
                "INSERT INTO scans(started_at,status) VALUES(?,?)",
                (utc_now(), "RUNNING"),
            )
            return int(cur.lastrowid)

    def fail_scan(self, scan_id: int, code: str):
        with self.connect() as db:
            db.execute(
                "UPDATE scans SET finished_at=?,status='ERROR',error_code=? WHERE id=?",
                (utc_now(), code[:160], scan_id),
            )
            db.execute(
                "INSERT INTO meta(key,value) VALUES('last_error',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (code[:160],),
            )

    def commit_players(self, scan_id: int, players: list[dict]) -> int:
        observed_at = utc_now()
        dedup: dict[str, dict] = {}
        for raw in players:
            p = normalize_player(raw)
            if p:
                dedup[p["game_uid"]] = p

        with self.connect() as db:
            for p in dedup.values():
                db.execute(
                    """
                    INSERT INTO players(
                        game_uid,pseudo,pseudo_norm,server_id,alliance_id,alliance_tag,
                        x,y,hq_level,first_seen_at,last_seen_at,last_scan_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(game_uid) DO UPDATE SET
                        pseudo=excluded.pseudo,
                        pseudo_norm=excluded.pseudo_norm,
                        server_id=COALESCE(excluded.server_id,players.server_id),
                        alliance_id=COALESCE(excluded.alliance_id,players.alliance_id),
                        alliance_tag=COALESCE(excluded.alliance_tag,players.alliance_tag),
                        x=COALESCE(excluded.x,players.x),
                        y=COALESCE(excluded.y,players.y),
                        hq_level=COALESCE(excluded.hq_level,players.hq_level),
                        last_seen_at=excluded.last_seen_at,
                        last_scan_id=excluded.last_scan_id
                    """,
                    (
                        p["game_uid"], p["pseudo"], p["pseudo_norm"], p["server_id"],
                        p["alliance_id"], p["alliance_tag"], p["x"], p["y"],
                        p["hq_level"], observed_at, observed_at, scan_id,
                    ),
                )
                db.execute(
                    """
                    INSERT INTO observations(
                        scan_id,game_uid,observed_at,pseudo,server_id,alliance_id,
                        alliance_tag,x,y,hq_level
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        scan_id, p["game_uid"], observed_at, p["pseudo"], p["server_id"],
                        p["alliance_id"], p["alliance_tag"], p["x"], p["y"], p["hq_level"],
                    ),
                )
            db.execute(
                "UPDATE scans SET finished_at=?,status='OK',player_count=? WHERE id=?",
                (observed_at, len(dedup), scan_id),
            )
            db.execute(
                "INSERT INTO meta(key,value) VALUES('last_success_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (observed_at,),
            )
            db.execute(
                "INSERT INTO meta(key,value) VALUES('last_error','') ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )
        return len(dedup)

    def meta(self, key: str) -> str:
        with self.connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return str(row[0]) if row else ""

    def stats(self) -> dict:
        with self.connect() as db:
            players = db.execute("SELECT COUNT(*) FROM players").fetchone()[0]
            observations = db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            last = db.execute(
                "SELECT id,started_at,finished_at,status,player_count,error_code FROM scans ORDER BY id DESC LIMIT 1"
            ).fetchone()
            servers = db.execute("SELECT COUNT(DISTINCT server_id) FROM players WHERE server_id IS NOT NULL").fetchone()[0]
        return {
            "players": players,
            "observations": observations,
            "servers": servers,
            "lastScan": dict(last) if last else None,
            "lastSuccessAt": self.meta("last_success_at") or None,
            "lastError": self.meta("last_error") or None,
        }

    def find_player(self, query: str) -> list[dict]:
        q = query.strip()
        if not q:
            return []
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT game_uid AS gameUid,pseudo,server_id AS serverId,
                       alliance_id AS allianceId,alliance_tag AS allianceTag,
                       x,y,hq_level AS hqLevel,power,army_power AS armyPower,
                       army_kill AS armyKill,svip_level AS svipLevel,
                       first_seen_at AS firstSeenAt,last_seen_at AS lastSeenAt,
                       profile_updated_at AS profileUpdatedAt
                FROM players
                WHERE game_uid=? OR pseudo_norm=?
                ORDER BY last_seen_at DESC LIMIT 20
                """,
                (q, q.casefold()),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_players(self, prefix: str, limit: int) -> list[dict]:
        lim = min(MAX_API_LIMIT, max(1, limit))
        p = prefix.strip().casefold()
        with self.connect() as db:
            if p:
                rows = db.execute(
                    """
                    SELECT game_uid AS gameUid,pseudo,server_id AS serverId,
                           alliance_tag AS allianceTag,x,y,hq_level AS hqLevel,last_seen_at AS lastSeenAt
                    FROM players WHERE pseudo_norm LIKE ? ORDER BY last_seen_at DESC LIMIT ?
                    """,
                    (p + "%", lim),
                ).fetchall()
            else:
                rows = db.execute(
                    """
                    SELECT game_uid AS gameUid,pseudo,server_id AS serverId,
                           alliance_tag AS allianceTag,x,y,hq_level AS hqLevel,last_seen_at AS lastSeenAt
                    FROM players ORDER BY last_seen_at DESC LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
        return [dict(r) for r in rows]


class Collector:
    def __init__(self, store: Store):
        self.store = store
        self.stop_event = threading.Event()
        self.scan_event = threading.Event()
        self.lock = threading.Lock()
        self.scanning = False
        self.last_count = 0
        self.last_error = ""

    def trigger(self):
        self.scan_event.set()

    def run_once(self):
        with self.lock:
            if self.scanning:
                return
            self.scanning = True
        scan_id = self.store.begin_scan()
        try:
            for path, code in (
                (NATIVE, "NATIVE_MISSING"),
                (SESSION, "SESSION_MISSING"),
                (CAPTURE, "CAPTURE_MISSING"),
            ):
                if not path.is_file():
                    raise RuntimeError(code)
            if not os.access(NATIVE, os.X_OK):
                raise RuntimeError("NATIVE_NOT_EXECUTABLE")

            cp = subprocess.run(
                [str(NATIVE), str(CAPTURE), str(SESSION), "--scan-player", "*"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=SCAN_TIMEOUT,
                check=False,
                env={**os.environ, "WFGG_COLLECTOR_BULK": "1"},
            )
            try:
                doc = json.loads(cp.stdout)
            except Exception as exc:
                raise RuntimeError("NATIVE_JSON_INVALID") from exc
            if not isinstance(doc, dict):
                raise RuntimeError("NATIVE_JSON_INVALID")
            if cp.returncode != 0:
                code = str(doc.get("loginResponse", "")).strip() or f"NATIVE_RC_{cp.returncode}"
                raise RuntimeError(code)
            players = doc.get("players")
            if players is None:
                players = []
            if not isinstance(players, list):
                raise RuntimeError("PLAYERS_NOT_LIST")
            count = self.store.commit_players(scan_id, players)
            self.last_count = count
            self.last_error = ""
            print(json.dumps({"event":"collector_scan_ok","scanId":scan_id,"players":count}, separators=(",",":")), flush=True)
        except subprocess.TimeoutExpired:
            self.last_error = "NATIVE_TIMEOUT"
            self.store.fail_scan(scan_id, self.last_error)
            print(json.dumps({"event":"collector_scan_error","scanId":scan_id,"error":self.last_error}, separators=(",",":")), flush=True)
        except Exception as exc:
            code = str(exc).strip() or type(exc).__name__
            # Persist/log only the compact error code. Never emit subprocess output.
            code = code[:160]
            self.last_error = code
            self.store.fail_scan(scan_id, code)
            print(json.dumps({"event":"collector_scan_error","scanId":scan_id,"error":code}, separators=(",",":")), flush=True)
        finally:
            with self.lock:
                self.scanning = False

    def worker(self):
        # Give the local API a moment to come up, then harvest immediately.
        if self.stop_event.wait(2):
            return
        while not self.stop_event.is_set():
            self.run_once()
            self.scan_event.clear()
            deadline = time.monotonic() + SCAN_INTERVAL
            while not self.stop_event.is_set():
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    break
                if self.scan_event.wait(min(remaining, 1.0)):
                    self.scan_event.clear()
                    break


class APIHandler(BaseHTTPRequestHandler):
    server_version = "WfGgCollector/1.0"

    @property
    def app(self) -> Collector:
        return self.server.collector  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):
        # Avoid request values (which can include player names) in service logs.
        return

    def send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path == "/health":
            stats = self.app.store.stats()
            self.send_json(200, {
                "ok": True,
                "service": "wfgg-collector-v1",
                "scanning": self.app.scanning,
                "lastCount": self.app.last_count,
                "lastSuccessAt": stats.get("lastSuccessAt"),
                "lastError": stats.get("lastError"),
            })
            return
        if u.path == "/stats":
            self.send_json(200, {"ok": True, **self.app.store.stats(), "scanning": self.app.scanning})
            return
        if u.path == "/player":
            q = (qs.get("q") or [""])[0]
            rows = self.app.store.find_player(q)
            self.send_json(200, {"ok": True, "query": q, "count": len(rows), "players": rows})
            return
        if u.path == "/players":
            prefix = (qs.get("prefix") or [""])[0]
            try:
                limit = int((qs.get("limit") or ["50"])[0])
            except ValueError:
                limit = 50
            rows = self.app.store.list_players(prefix, limit)
            self.send_json(200, {"ok": True, "count": len(rows), "players": rows})
            return
        self.send_json(404, {"ok": False, "error": "NOT_FOUND"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/scan":
            self.app.trigger()
            self.send_json(202, {"ok": True, "queued": True})
            return
        self.send_json(404, {"ok": False, "error": "NOT_FOUND"})


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    store = Store(DB_PATH)
    collector = Collector(store)
    server = ThreadingHTTPServer((HOST, PORT), APIHandler)
    server.collector = collector  # type: ignore[attr-defined]

    def shutdown(_signum=None, _frame=None):
        collector.stop_event.set()
        collector.scan_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    worker = threading.Thread(target=collector.worker, name="wfgg-collector-worker", daemon=True)
    worker.start()
    print(json.dumps({"event":"collector_started","host":HOST,"port":PORT,"interval":SCAN_INTERVAL}, separators=(",",":")), flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        collector.stop_event.set()
        collector.scan_event.set()
        server.server_close()
        worker.join(timeout=5)
        print(json.dumps({"event":"collector_stopped"}, separators=(",",":")), flush=True)


if __name__ == "__main__":
    main()
