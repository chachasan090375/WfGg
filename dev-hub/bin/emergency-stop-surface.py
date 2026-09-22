#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,secrets,subprocess
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

DEFAULT_BIND="127.0.0.1"
DEFAULT_PORT=8788
DEFAULT_TOKEN=Path("/opt/chacha-dev/runtime/control/emergency-stop-ui.token")
DEFAULT_CONTROLLER=Path("/opt/chacha-dev/platform/current/dev-hub/bin/emergency-stop-controller.py")

def token(path:Path)->str:
    if path.is_file(): return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True,exist_ok=True)
    value=secrets.token_urlsafe(32)
    path.write_text(value+"\n",encoding="utf-8"); os.chmod(path,0o600)
    return value

def call(controller:Path,args:list[str])->dict:
    p=subprocess.run(["/usr/bin/python3",str(controller),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=35)
    if p.returncode!=0: raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return json.loads(p.stdout)

def page(tok:str)->str:
    return """<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChaCha DEV — Arrêt d'urgence</title><style>
body{font-family:system-ui;margin:0;background:#24232a;color:#f7f7f8;display:grid;place-items:center;min-height:100vh}
main{width:min(92vw,560px);background:#34323d;padding:28px;border-radius:24px;box-shadow:0 12px 35px #0006}
h1{margin-top:0}.stop{width:100%;min-height:120px;border:0;border-radius:22px;background:#d71920;color:white;font-size:28px;font-weight:900;box-shadow:inset 0 -6px #8e0d12;cursor:pointer}
.reset{margin-top:20px;width:100%;padding:14px;border-radius:14px;border:1px solid #817b91;background:#514d5e;color:white}
#status{margin:18px 0;padding:12px;border-radius:12px;background:#25232b;white-space:pre-wrap}.hint{opacity:.75;font-size:14px}
</style><main><h1>ChaCha DEV · Sécurité</h1><div id="status">Lecture de l’état…</div>
<button class="stop" id="stop">STOP D’URGENCE</button><button class="reset" id="reset">Réinitialiser le verrou</button>
<p class="hint">Le STOP bloque les nouveaux dispatchs et matérialisations et coupe les capsules éphémères. La mémoire persistante et les preuves sont conservées.</p>
<script>
const TOKEN="""+json.dumps(tok)+""";
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-ChaCha-Stop-Token':TOKEN},body:body?JSON.stringify(body):undefined});const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
async function refresh(){try{const j=await api('/api/emergency-stop/status');document.querySelector('#status').textContent=j.active?'⛔ ARRÊT D’URGENCE ACTIF':'✅ Système autorisé — verrou inactif'}catch(e){document.querySelector('#status').textContent='Erreur: '+e}}
document.querySelector('#stop').onclick=async()=>{if(confirm("Déclencher l'arrêt d'urgence ChaCha DEV ?")){await api('/api/emergency-stop/activate',{reason:'human-ui-button'});await refresh()}}
document.querySelector('#reset').onclick=async()=>{if(confirm("Réinitialiser le verrou ? La reprise restera manuelle.")){await api('/api/emergency-stop/reset',{reason:'human-ui-reset',confirm:'RESET'});await refresh()}}
refresh();
</script></main></html>"""

class Handler(BaseHTTPRequestHandler):
    server_version="ChaChaEmergencySurface/1"
    def _json(self,code:int,obj:dict):
        raw=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(code);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path=="/":
            raw=page(self.server.stop_token).encode()
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw);return
        if self.path=="/api/emergency-stop/status":
            try:self._json(200,call(self.server.controller,["status"]))
            except Exception as e:self._json(500,{"error":str(e)})
            return
        self._json(404,{"error":"not_found"})
    def do_POST(self):
        if self.headers.get("X-ChaCha-Stop-Token","")!=self.server.stop_token:
            self._json(403,{"error":"forbidden"});return
        try:
            n=min(int(self.headers.get("Content-Length","0") or 0),4096); body=json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._json(400,{"error":"invalid_json"});return
        try:
            if self.path=="/api/emergency-stop/activate":
                reason=str(body.get("reason") or "human-ui-button")[:160]
                self._json(200,call(self.server.controller,["activate","--reason",reason,"--actor","human-emergency-stop-ui"]));return
            if self.path=="/api/emergency-stop/reset":
                if body.get("confirm")!="RESET": self._json(409,{"error":"explicit_reset_confirmation_required"});return
                reason=str(body.get("reason") or "human-ui-reset")[:160]
                self._json(200,call(self.server.controller,["reset","--reason",reason,"--actor","human-emergency-reset-ui"]));return
            self._json(404,{"error":"not_found"})
        except Exception as e:self._json(500,{"error":str(e)})
    def log_message(self,fmt,*args): return

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--bind",default=DEFAULT_BIND);ap.add_argument("--port",type=int,default=DEFAULT_PORT)
    ap.add_argument("--token-file",type=Path,default=DEFAULT_TOKEN);ap.add_argument("--controller",type=Path,default=DEFAULT_CONTROLLER)
    a=ap.parse_args()
    if a.bind not in {"127.0.0.1","::1","localhost"}: raise SystemExit("EMERGENCY_SURFACE_BIND_MUST_BE_LOOPBACK")
    srv=ThreadingHTTPServer((a.bind,a.port),Handler);srv.stop_token=token(a.token_file);srv.controller=a.controller
    print(f"CHACHA_EMERGENCY_SURFACE=READY bind={a.bind} port={a.port}",flush=True);srv.serve_forever()
if __name__=="__main__":
    main()
