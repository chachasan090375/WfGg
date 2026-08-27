#!/usr/bin/env python3
import hmac
import http.client
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PUBLIC_PORT = int(os.environ.get("PORT", "8080"))
SLOT_COUNT = max(1, min(12, int(os.environ.get("WFGG_BROKER_SLOTS", "4"))))
SLOT_BASE_PORT = int(os.environ.get("WFGG_BROKER_SLOT_BASE_PORT", "18080"))
SHARED_SECRET = os.environ.get("WFGG_BROKER_SHARED_SECRET", "").strip()
CHILD_BIN = os.environ.get("WFGG_BROKER_CHILD_BIN", "/app/wfgg-lastwar-child")
REQUEST_LIMIT = 64 * 1024
DEFAULT_TX_TTL = 10 * 60

if len(SHARED_SECRET) < 32:
    raise SystemExit("WFGG_BROKER_SHARED_SECRET must contain at least 32 characters")


class Slot:
    def __init__(self, index: int):
        self.index = index
        self.port = SLOT_BASE_PORT + index
        self.home = f"/tmp/wfgg-lastwar-slot-{index}"
        self.proc = None
        self.lease = None
        self.lease_until = 0.0
        self.lock = threading.RLock()
        self.start()

    def start(self):
        with self.lock:
            self._stop_locked()
            shutil.rmtree(self.home, ignore_errors=True)
            os.makedirs(self.home, mode=0o700, exist_ok=True)
            env = dict(os.environ)
            env["HOME"] = self.home
            env["PORT"] = str(self.port)
            env.pop("WFGG_BROKER_SHARED_SECRET", None)
            self.proc = subprocess.Popen(
                [CHILD_BIN],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=None,
                stderr=None,
                close_fds=True,
            )
            self.lease = None
            self.lease_until = 0.0
        self.wait_ready()

    def _stop_locked(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None

    def stop(self):
        with self.lock:
            self._stop_locked()
            shutil.rmtree(self.home, ignore_errors=True)
            self.lease = None
            self.lease_until = 0.0

    def recycle(self):
        self.start()

    def alive(self):
        with self.lock:
            return bool(self.proc and self.proc.poll() is None)

    def wait_ready(self):
        deadline = time.time() + 8
        while time.time() < deadline:
            if not self.alive():
                break
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1)
                conn.request("GET", "/ping")
                res = conn.getresponse()
                res.read()
                conn.close()
                if res.status == 200:
                    return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError(f"Last War child slot {self.index} failed to start")

    def expired(self):
        with self.lock:
            return bool(self.lease and self.lease_until and time.time() > self.lease_until)

    def is_free(self):
        with self.lock:
            return self.alive() and not self.lease

    def reserve(self, lease, ttl=DEFAULT_TX_TTL):
        with self.lock:
            if self.lease:
                return False
            self.lease = lease
            self.lease_until = time.time() + ttl
            return True

    def set_lease(self, lease, ttl):
        with self.lock:
            self.lease = lease
            self.lease_until = time.time() + max(60, ttl)

    def lease_matches(self, lease):
        with self.lock:
            return self.lease == lease and time.time() <= self.lease_until


slots = []
slots_lock = threading.RLock()
shutdown_event = threading.Event()


def init_slots():
    for i in range(SLOT_COUNT):
        slots.append(Slot(i))


def shutdown_slots(*_):
    shutdown_event.set()
    for slot in slots:
        try:
            slot.stop()
        except Exception:
            pass


def janitor():
    while not shutdown_event.wait(15):
        for slot in slots:
            try:
                if slot.expired() or not slot.alive():
                    slot.recycle()
            except Exception as exc:
                print(f"slot recycle failed index={slot.index}: {type(exc).__name__}", flush=True)


def allocate_slot(kind="request", ttl=120):
    with slots_lock:
        for slot in slots:
            if slot.expired():
                try:
                    slot.recycle()
                except Exception:
                    continue
            lease = f"{kind}:{time.time_ns()}"
            if slot.reserve(lease, ttl):
                return slot, lease
    return None, None


def any_alive_slot():
    for slot in slots:
        if slot.alive():
            return slot
    return None


def child_request(slot, method, path, body, inbound_headers, timeout=95):
    headers = {
        "Content-Type": "application/json",
        "X-WfGg-Container-Auth": "1",
    }
    state_key = inbound_headers.get("X-WfGg-State-Key")
    sealed_state = inbound_headers.get("X-WfGg-Sealed-State")
    if state_key:
        headers["X-WfGg-State-Key"] = state_key
    if sealed_state:
        headers["X-WfGg-Sealed-State"] = sealed_state

    conn = http.client.HTTPConnection("127.0.0.1", slot.port, timeout=timeout)
    try:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        conn.request(method, path, body=payload, headers=headers)
        res = conn.getresponse()
        raw = res.read(REQUEST_LIMIT + 1)
        if len(raw) > REQUEST_LIMIT:
            return 502, {"error": "BROKER_CHILD_RESPONSE_TOO_LARGE"}
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            data = {"error": "BROKER_CHILD_INVALID_JSON"}
            if res.status < 400:
                return 502, data
        return res.status, data
    finally:
        conn.close()


def safe_recycle(slot):
    try:
        slot.recycle()
    except Exception as exc:
        print(f"slot recycle failed index={slot.index}: {type(exc).__name__}", flush=True)


def external_tx(slot, child_tx):
    return f"s{slot.index}.{child_tx}"


def parse_external_tx(value):
    value = str(value or "").strip()
    if not value.startswith("s") or "." not in value:
        return None, None
    prefix, child = value.split(".", 1)
    try:
        index = int(prefix[1:])
    except ValueError:
        return None, None
    if index < 0 or index >= len(slots) or not child:
        return None, None
    return slots[index], child


class Handler(BaseHTTPRequestHandler):
    server_version = "WfGgLastWarBroker/1.0"

    def log_message(self, fmt, *args):
        # Never log request bodies, email addresses, verification codes, or auth headers.
        print(f"broker {self.command} {self.path} {fmt % args}", flush=True)

    def send_json(self, status, data):
        payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        supplied = self.headers.get("X-WfGg-Broker-Auth", "")
        return hmac.compare_digest(supplied.encode(), SHARED_SECRET.encode())

    def read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if size <= 0 or size > REQUEST_LIMIT:
            raise ValueError("invalid request size")
        raw = self.rfile.read(size)
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("JSON object required")
        return obj

    def do_GET(self):
        path = urlparse(self.path).path
        if path != "/ping":
            self.send_json(404, {"error": "NOT_FOUND"})
            return
        healthy = sum(1 for s in slots if s.alive())
        status = 200 if healthy else 503
        self.send_json(status, {
            "ok": healthy > 0,
            "service": "wfgg-lastwar-broker-manager",
            "child_service": "wfgg-lastwar-go-broker",
            "mode": "read-only",
            "slots": SLOT_COUNT,
            "healthy_slots": healthy,
            "leased_slots": sum(1 for s in slots if s.lease),
        })

    def do_POST(self):
        if not self.authorized():
            self.send_json(403, {"error": "FORBIDDEN"})
            return
        path = urlparse(self.path).path
        if path not in {
            "/v1/identity/resolve",
            "/v1/identity/send-code",
            "/v1/identity/verify-code",
            "/v1/profile/sync",
        }:
            self.send_json(404, {"error": "NOT_FOUND"})
            return
        try:
            body = self.read_json()
        except Exception:
            self.send_json(400, {"error": "INVALID_JSON"})
            return

        if path == "/v1/identity/resolve":
            slot = any_alive_slot()
            if not slot:
                self.send_json(503, {"error": "LASTWAR_BROKER_UNAVAILABLE"})
                return
            try:
                status, data = child_request(slot, "POST", path, body, self.headers)
                self.send_json(status, data)
            except Exception:
                self.send_json(503, {"error": "LASTWAR_BROKER_UNAVAILABLE"})
            return

        if path == "/v1/identity/send-code":
            slot, provisional = allocate_slot("link", DEFAULT_TX_TTL + 90)
            if not slot:
                self.send_json(429, {"error": "LASTWAR_RATE_LIMITED"})
                return
            try:
                status, data = child_request(slot, "POST", path, body, self.headers)
                child_tx = str(data.get("auth_transaction", "")) if isinstance(data, dict) else ""
                if status == 200 and child_tx:
                    ttl = int(data.get("expires_in", DEFAULT_TX_TTL))
                    ext = external_tx(slot, child_tx)
                    data["auth_transaction"] = ext
                    slot.set_lease(ext, ttl + 30)
                    self.send_json(status, data)
                    return
                self.send_json(status, data)
            except Exception:
                self.send_json(503, {"error": "LASTWAR_BROKER_UNAVAILABLE"})
            safe_recycle(slot)
            return

        if path == "/v1/identity/verify-code":
            ext = str(body.get("auth_transaction", ""))
            slot, child_tx = parse_external_tx(ext)
            if not slot or not slot.lease_matches(ext):
                self.send_json(401, {"error": "LASTWAR_VERIFY_CODE_EXPIRED"})
                return
            body = dict(body)
            body["auth_transaction"] = child_tx
            try:
                status, data = child_request(slot, "POST", path, body, self.headers)
                self.send_json(status, data)
            except Exception:
                self.send_json(503, {"error": "LASTWAR_BROKER_UNAVAILABLE"})
            finally:
                safe_recycle(slot)
            return

        if path == "/v1/profile/sync":
            slot, lease = allocate_slot("sync", 180)
            if not slot:
                self.send_json(429, {"error": "LASTWAR_RATE_LIMITED"})
                return
            try:
                status, data = child_request(slot, "POST", path, body, self.headers)
                self.send_json(status, data)
            except Exception:
                self.send_json(503, {"error": "LASTWAR_BROKER_UNAVAILABLE"})
            finally:
                safe_recycle(slot)
            return


def main():
    init_slots()
    threading.Thread(target=janitor, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown_slots)
    signal.signal(signal.SIGINT, shutdown_slots)
    server = ThreadingHTTPServer(("0.0.0.0", PUBLIC_PORT), Handler)
    print(f"wfgg-lastwar-broker-manager listening on :{PUBLIC_PORT} slots={SLOT_COUNT}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        shutdown_slots()


if __name__ == "__main__":
    main()
