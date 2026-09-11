#!/usr/bin/env python3
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.environ.get("WFGG_COLLECTOR_ROOT", "/opt/wfgg-collector")
DB_PATH = os.environ.get("WFGG_COLLECTOR_DB", f"{ROOT}/data/collector.db")
HOST = os.environ.get("WFGG_COLLECTOR_HOST", "127.0.0.1")
PORT = int(os.environ.get("WFGG_COLLECTOR_PORT", "8790"))
DB_LOCK = threading.RLock()


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with DB_LOCK, db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
              game_uid TEXT PRIMARY KEY,
              pseudo TEXT NOT NULL,
              server_id TEXT,
              alliance_id TEXT,
              alliance_tag TEXT,
              x INTEGER,
              y INTEGER,
              hq_level INTEGER,
              power INTEGER,
              first_seen TEXT NOT NULL,
              last_seen TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_players_pseudo_nocase
              ON players(pseudo COLLATE NOCASE);
            CREATE TABLE IF NOT EXISTS observations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              game_uid TEXT NOT NULL,
              observed_at TEXT NOT NULL,
              pseudo TEXT NOT NULL,
              server_id TEXT,
              alliance_id TEXT,
              alliance_tag TEXT,
              x INTEGER,
              y INTEGER,
              hq_level INTEGER,
              power INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_obs_uid_time
              ON observations(game_uid, observed_at DESC);
            """
        )


def normalized_player(p):
    uid = str(p.get("gameUid") or p.get("game_uid") or "").strip()
    pseudo = str(p.get("pseudo") or "").strip()
    if not uid or not pseudo:
        raise ValueError("PLAYER_IDENTITY_REQUIRED")
    return {
        "game_uid": uid,
        "pseudo": pseudo,
        "server_id": str(p.get("serverId") or p.get("server_id") or "").strip(),
        "alliance_id": str(p.get("allianceId") or p.get("alliance_id") or "").strip(),
        "alliance_tag": str(p.get("allianceTag") or p.get("alliance_tag") or "").strip(),
        "x": p.get("x"),
        "y": p.get("y"),
        "hq_level": p.get("hqLevel") if "hqLevel" in p else p.get("hq_level"),
        "power": p.get("power"),
        "observed_at": str(p.get("observedAt") or p.get("observed_at") or now_iso()),
    }


def upsert_player(raw):
    p = normalized_player(raw)
    values = (
        p["pseudo"], p["server_id"], p["alliance_id"], p["alliance_tag"],
        p["x"], p["y"], p["hq_level"], p["power"],
    )
    with DB_LOCK, db() as c:
        old = c.execute(
            "SELECT pseudo,server_id,alliance_id,alliance_tag,x,y,hq_level,power FROM players WHERE game_uid=?",
            (p["game_uid"],),
        ).fetchone()
        changed = old is None or tuple(old) != values
        c.execute(
            """
            INSERT INTO players(game_uid,pseudo,server_id,alliance_id,alliance_tag,x,y,hq_level,power,first_seen,last_seen)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(game_uid) DO UPDATE SET
              pseudo=excluded.pseudo,
              server_id=excluded.server_id,
              alliance_id=excluded.alliance_id,
              alliance_tag=excluded.alliance_tag,
              x=excluded.x,
              y=excluded.y,
              hq_level=excluded.hq_level,
              power=COALESCE(excluded.power,players.power),
              last_seen=excluded.last_seen
            """,
            (p["game_uid"], *values, p["observed_at"], p["observed_at"]),
        )
        if changed:
            c.execute(
                """
                INSERT INTO observations(game_uid,observed_at,pseudo,server_id,alliance_id,alliance_tag,x,y,hq_level,power)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (p["game_uid"], p["observed_at"], *values),
            )
    return p["game_uid"], changed


def find_player(q):
    with DB_LOCK, db() as c:
        row = c.execute(
            "SELECT * FROM players WHERE game_uid=? OR pseudo=? COLLATE NOCASE ORDER BY last_seen DESC LIMIT 1",
            (q, q),
        ).fetchone()
    return dict(row) if row else None


def search_players(q, limit):
    limit = max(1, min(100, int(limit)))
    with DB_LOCK, db() as c:
        rows = c.execute(
            "SELECT * FROM players WHERE pseudo LIKE ? COLLATE NOCASE OR game_uid LIKE ? ORDER BY last_seen DESC LIMIT ?",
            (f"%{q}%", f"%{q}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def stats():
    with DB_LOCK, db() as c:
        players = c.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        observations = c.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        last = c.execute("SELECT MAX(last_seen) FROM players").fetchone()[0]
    return {"players": players, "observations": observations, "lastSeen": last}


class Handler(BaseHTTPRequestHandler):
    server_version = "WfGgCollector/1"

    def log_message(self, fmt, *args):
        return

    def send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        args = parse_qs(u.query)
        if u.path == "/health":
            self.send_json(200, {"ok": True, "service": "wfgg-collector-v1"})
            return
        if u.path == "/stats":
            self.send_json(200, stats())
            return
        if u.path == "/player":
            q = args.get("q", [""])[0].strip()
            if not q:
                self.send_json(400, {"ok": False, "error": "QUERY_REQUIRED"})
                return
            p = find_player(q)
            self.send_json(200 if p else 404, {"ok": bool(p), "player": p})
            return
        if u.path == "/search":
            q = args.get("q", [""])[0].strip()
            limit = args.get("limit", ["20"])[0]
            if not q:
                self.send_json(400, {"ok": False, "error": "QUERY_REQUIRED"})
                return
            self.send_json(200, {"ok": True, "players": search_players(q, limit)})
            return
        self.send_json(404, {"ok": False, "error": "NOT_FOUND"})

    def do_POST(self):
        if urlparse(self.path).path != "/ingest":
            self.send_json(404, {"ok": False, "error": "NOT_FOUND"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > 2_000_000:
                raise ValueError("INVALID_BODY_SIZE")
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
            rows = payload if isinstance(payload, list) else payload.get("players", [payload])
            if not isinstance(rows, list):
                raise ValueError("PLAYERS_LIST_REQUIRED")
            accepted = 0
            changed = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                _, did_change = upsert_player(row)
                accepted += 1
                changed += int(did_change)
            self.send_json(200, {"ok": True, "accepted": accepted, "changed": changed})
        except (ValueError, json.JSONDecodeError) as e:
            self.send_json(400, {"ok": False, "error": str(e)})


def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
