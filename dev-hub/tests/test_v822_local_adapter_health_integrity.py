#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,tempfile,threading
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PROBE=ROOT/"dev-hub/bin/collector-knowledge-provider-probe.py"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!="/knowledge/health":
            self.send_response(404);self.end_headers();return
        body=b'{"status":"ok","read_only":true}'
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

def run_probe(systemctl:Path,url:str,out:Path):
    return subprocess.run([
      "python3",str(PROBE),"--executable","/bin/true","--output",str(out),
      "--api-url",url,"--systemctl-bin",str(systemctl),"--timeout","2"
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)

with tempfile.TemporaryDirectory(prefix="v822-collector-probe-") as raw:
    td=Path(raw)
    fake=td/"systemctl"
    fake.write_text("#!/bin/sh\n[ \"$1\" = is-active ] && { echo active; exit 0; }\necho unsupported >&2; exit 2\n")
    fake.chmod(0o755)
    server=HTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    healthy=td/"healthy.json"
    p=run_probe(fake,f"http://127.0.0.1:{server.server_port}/knowledge/health",healthy)
    server.shutdown();thread.join(timeout=2)
    assert p.returncode==0,(p.stdout,p.stderr)
    x=json.loads(healthy.read_text())
    assert x["schema"]=="chacha.dev/provider-probe-result/v1"
    assert x["provider"]=="collector-knowledge-runtime"
    assert x["state"]=="HEALTHY"
    assert x["details"]["independent_from_adapter_execution"] is True
    assert x["details"]["loopback_only"] is True
    assert x["details"]["lastwar_connection"]=="NONE"
    assert x["details"]["mutations"] is False

    fake.write_text("#!/bin/sh\n[ \"$1\" = is-active ] && { echo inactive; exit 3; }\nexit 2\n")
    fake.chmod(0o755)
    unavailable=td/"unavailable.json"
    p=run_probe(fake,"http://127.0.0.1:9/knowledge/health",unavailable)
    assert p.returncode==2,(p.stdout,p.stderr)
    y=json.loads(unavailable.read_text())
    assert y["state"]=="UNAVAILABLE"
    assert any("NOT_ACTIVE" in z for z in y["details"]["blockers"])
    assert any("TRANSPORT" in z for z in y["details"]["blockers"])

catalog=json.loads((ROOT/"dev-hub/config/provider-health-probes.v1.json").read_text())
assert catalog["providers"]["collector-knowledge-runtime"]["probe"]=="collector-knowledge-local"

registry=json.loads((ROOT/"dev-hub/config/provider-adapters.v1.json").read_text())
http=registry["adapters"]["http-smoke-adapter"]
assert http["status"]=="ENABLED"
assert http["executable"]=="/opt/chacha-dev/adapters/http-smoke/current/http-smoke-adapter"
assert set(http["supports"])=={"read"}

source=PROBE.read_text(encoding="utf-8")
assert "collector-knowledge-adapter.py" not in source
assert "subprocess.run([str(a.executable)" not in source
assert "ProxyHandler({})" in source
assert "lastwar_connection" in source
assert "mutations" in source

print("CHACHA_DEV_V822_HTTP_SMOKE_ENABLED=PASS")
print("CHACHA_DEV_V822_COLLECTOR_HEALTHY_PROBE=PASS")
print("CHACHA_DEV_V822_COLLECTOR_UNAVAILABLE_FAIL_CLOSED=PASS")
print("CHACHA_DEV_V822_PROBE_INDEPENDENT_FROM_ADAPTER=PASS")
print("CHACHA_DEV_V822_LASTWAR_CONNECTION_NONE=PASS")
print("CHACHA_DEV_V822_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
