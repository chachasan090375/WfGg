#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40 server — V39.15 viewer + deterministic Animation Graph Agent."""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v3915-runtime-preview.py'
AGENT_CORE = ROOT / 'scripts/lastwar-animation-graph-agent-v40.py'
AGENT_JS = ROOT / 'frontend/lab/global-graphics-v33/animation-agent-v40.js'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

v3915 = load('wfgg_v3915_for_v40', BASE)
v40core = load('wfgg_animation_graph_agent_v40', AGENT_CORE)
v3912 = v3915.v3914.v3912
core = v3915.core
agent = v40core.AnimationGraphAgent(v3912)


def _send_js(handler, text):
    raw = text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache')
    handler.send_header('Expires','0')
    handler.end_headers(); handler.wfile.write(raw)


class V40Handler(v3915.V3915Handler):
    def do_GET(self):
        u = urlparse(self.path); qs = parse_qs(u.query)
        if u.path == '/api/v40/status':
            try:
                st = v40core.agent_status()
                st.update({
                    'serverVersion':'40.0',
                    'inherits':'39.15',
                    'referenceAsset':'LWGA-C37A0F67197299',
                    'referencePrefab':'LWGA-0D0CA2A747F7DF',
                    'assemblyStaticAnalysis':True,
                    'ilCallTokenInspection':True,
                    'batchIndexPlanned':True,
                })
                return self.send_json(st)
            except Exception as exc:
                return self.send_json({'error':'v40-status-failed','message':str(exc)},500)
        if u.path == '/api/v40/trace':
            sid = str((qs.get('id') or [''])[0]).strip().upper()
            refresh = str((qs.get('refresh') or ['0'])[0]).lower() in {'1','true','yes'}
            deep = str((qs.get('deep') or ['1'])[0]).lower() not in {'0','false','no'}
            try:
                payload = agent.trace(sid, refresh=refresh, deep=deep)
                print('V40_AGENT_TRACE', sid,
                      'controller='+str(payload.get('controllerStableId')),
                      'nodes='+str((payload.get('summary') or {}).get('nodeCount')),
                      'edges='+str((payload.get('summary') or {}).get('edgeCount')),
                      'recipe='+str((payload.get('recipe') or {}).get('kind')),
                      'cache='+str(payload.get('cacheHit')), flush=True)
                return self.send_json(payload)
            except ValueError as exc:
                return self.send_json({'error':'v40-invalid-id','message':str(exc)},400)
            except KeyError as exc:
                return self.send_json({'error':'v40-asset-not-found','message':str(exc)},404)
            except Exception as exc:
                print('V40_AGENT_ERROR', sid, type(exc).__name__, str(exc), flush=True)
                return self.send_json({'error':'v40-agent-failed','message':str(exc),'id':sid},500)
        if u.path == '/lab/global-graphics-v33/animation-agent-v40.js':
            try:
                return _send_js(self, AGENT_JS.read_text('utf-8'))
            except Exception as exc:
                return self.send_json({'error':'v40-agent-js-failed','message':str(exc)},500)
        if u.path == '/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                # Keep one deterministic execution chain: V39 resolver + fixed badge row + exact
                # runtime-child preview + V40 graph-agent UI.
                text = (
                    v3915.RESOLVER_JS.read_text('utf-8') + '\n\n' +
                    v3915.LAYOUT_JS.read_text('utf-8') + '\n\n' +
                    v3915.PREVIEW_JS.read_text('utf-8') + '\n\n' +
                    AGENT_JS.read_text('utf-8') + '\n'
                )
                return _send_js(self, text)
            except Exception as exc:
                return self.send_json({'error':'v40-inline-ui-failed','message':str(exc)},500)
        return super().do_GET()


if __name__ == '__main__':
    st = v40core.agent_status()
    print('=== WFGG LAST WAR V40 — ANIMATION GRAPH AGENT ===', flush=True)
    print('V40_AGENT graph=ON cache=SQLite assembly-clr=ON il-call-token=ON code-execution=OFF', flush=True)
    print('V40_AGENT_EVIDENCE catalogue=EXACT pptr=EXACT softprefab=EXACT code=CLR+IL synthetic-motion=OFF', flush=True)
    print('V40_AGENT_REFERENCE LWGA-C37A0F67197299 -> LWGA-0D0CA2A747F7DF', flush=True)
    print('V40_AGENT_CACHE traces='+str(st.get('traces',0))+' assembly-ready='+str((st.get('assembly') or {}).get('ready',False)), flush=True)
    print('V39_15_RUNTIME_CHILD inherited=ON V39_14_BADGE inherited=ON', flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), V40Handler).serve_forever()
