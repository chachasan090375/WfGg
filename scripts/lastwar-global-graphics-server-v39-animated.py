#!/usr/bin/env python3
from __future__ import annotations

"""WfGg Last War graphics LAB V39: exact animated-prefab diagnostics.

This is a non-destructive wrapper around the current V33/V34/V35/V38 explorer. It adds an exact
Unity animation scanner and the V39 diagnostics UI without weakening any existing render guardrail.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util, re, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v33-explorer.py'
SCANNER = ROOT / 'scripts/lastwar-global-graphics-animation-v39.py'
BINDINGS = ROOT / 'scripts/lastwar-global-graphics-animation-bindings-v39.py'
V39_JS = ROOT / 'frontend/lab/global-graphics-v33/animation-viewer-v39.js'
V391_RUNTIME_JS = ROOT / 'frontend/lab/global-graphics-v33/animation-runtime-v39.js'
VIEWER = ROOT / 'frontend/lab/lastwar-global-graphics-viewer-v33.html'
CACHE_ROOT = Path.home() / '.cache/wfgg-lastwar-v31'

spec = importlib.util.spec_from_file_location('wfgg_v33_explorer_for_v39', BASE)
v33 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v33)

aspec = importlib.util.spec_from_file_location('wfgg_animation_v39', SCANNER)
anim = importlib.util.module_from_spec(aspec)
aspec.loader.exec_module(anim)

bspec = importlib.util.spec_from_file_location('wfgg_animation_bindings_v39', BINDINGS)
bindings = importlib.util.module_from_spec(bspec)
bspec.loader.exec_module(bindings)

base = v33.base
core = v33.core
ptr_fast = base.ptr3d
ptr = ptr_fast.p
dependency_rows = v33.mobile.ORIGINAL_DEPENDENCY_ROWS


def _send_js(handler, path):
    raw = path.read_bytes()
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/javascript; charset=utf-8')
    handler.send_header('Content-Length', str(len(raw)))
    handler.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma', 'no-cache')
    handler.send_header('Expires', '0')
    handler.end_headers()
    handler.wfile.write(raw)


def _asset(sid):
    if hasattr(core, 'get_asset'):
        try:
            a = core.get_asset(sid)
            if a:
                return a
        except Exception:
            pass
    con = core.dbcon()
    try:
        row = con.execute('SELECT * FROM assets WHERE stable_id=?', (sid,)).fetchone()
        return core.rowdict(row) if row else None
    finally:
        con.close()


class AnimatedHandler(v33.ExplorerHandler):
    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        try:
            if u.path == '/lab/global-graphics-v33/animation-viewer-v39.js':
                return _send_js(self, V39_JS)
            if u.path == '/lab/global-graphics-v33/animation-runtime-v39.js':
                return _send_js(self, V391_RUNTIME_JS)

            if u.path == '/api/v39/animation':
                sid = str((qs.get('id') or [''])[0])
                if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
                    return self.send_json({'error': 'invalid-id'}, 400)
                a = _asset(sid)
                if not a:
                    return self.send_json({'error': 'asset-not-found', 'id': sid}, 404)
                with ptr_fast.ASSEMBLY_LOCK:
                    payload = anim.scan_animation(a, core, ptr, dependency_rows, CACHE_ROOT)
                print(
                    'V39_ANIMATION_SCAN', sid,
                    payload.get('classification', {}).get('status', ''),
                    'clips=' + str(payload.get('clips', {}).get('directLinkedCount', 0)),
                    'nodes=' + str(payload.get('hierarchy', {}).get('nodeCount', 0)),
                    'cache=' + ('HIT' if payload.get('cacheHit') else 'MISS'),
                    flush=True,
                )
                return self.send_json(payload)

            if u.path == '/api/v39/animation-bindings':
                sid = str((qs.get('id') or [''])[0])
                if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
                    return self.send_json({'error': 'invalid-id'}, 400)
                a = _asset(sid)
                if not a:
                    return self.send_json({'error': 'asset-not-found', 'id': sid}, 404)
                with ptr_fast.ASSEMBLY_LOCK:
                    payload = bindings.build_bindings(a, core, ptr, dependency_rows, CACHE_ROOT)
                print('V39_ANIMATION_BINDINGS', sid, 'nodes='+str(payload.get('nodeCount', 0)), 'meshes='+str(payload.get('meshBindingCount', 0)), 'cache='+('HIT' if payload.get('cacheHit') else 'MISS'), flush=True)
                return self.send_json(payload)

            if u.path == '/api/v39/status':
                return self.send_json({
                    'version': '39.1',
                    'animationDiagnostics': True,
                    'exactBundlePtrEvidence': True,
                    'syntheticAnimation': False,
                    'playbackRuntime': 'reconstructed-simple-transform-curves',
                    'exactMeshTransformBindings': True,
                    'referenceAsset': 'LWGA-C37A0F67197299',
                })

            if u.path == '/lab/lastwar-global-graphics-viewer-v33.html':
                raw = VIEWER.read_text('utf-8')
                corr = '<script src="./global-graphics-v33/search-correlation-v33.js"></script>'
                exp = '<script src="./global-graphics-v33/explorer-v33.js"></script>'
                v39 = '<script src="./global-graphics-v33/animation-viewer-v39.js?v=3901"></script>'
                v391 = '<script src="./global-graphics-v33/animation-runtime-v39.js?v=3911"></script>'
                if 'search-correlation-v33.js' not in raw:
                    raw = raw.replace('</body>', corr + '</body>')
                if 'explorer-v33.js' not in raw:
                    raw = raw.replace('</body>', exp + '</body>')
                if 'animation-viewer-v39.js' not in raw:
                    raw = raw.replace('</body>', v39 + '</body>')
                if 'animation-runtime-v39.js' not in raw:
                    raw = raw.replace('</body>', v391 + '</body>')
                data = raw.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                self.wfile.write(data)
                return
        except Exception as exc:
            print('V39_ANIMATION_ERROR', type(exc).__name__, str(exc)[:900], flush=True)
            return self.send_json({'error': 'v39-animation-failed', 'message': str(exc)}, 500)
        return super().do_GET()


if __name__ == '__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V39 — ANIMATED PREFAB DIAGNOSTICS ===', flush=True)
    print('V39_ANIMATION exact-bundle-ptr=ON transform-curves=INSPECT synthetic-motion=OFF', flush=True)
    print('V39_PLAYBACK simple-transform-curves=RECONSTRUCTABLE exact-mesh-bindings=ON', flush=True)
    print('V39_PARTICLES detection=ON playback=NOT_YET', flush=True)
    print('V39_SCRIPTS animation-hints=CONSERVATIVE execution=OFF', flush=True)
    print('V39_REFERENCE_ASSET LWGA-C37A0F67197299', flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), AnimatedHandler).serve_forever()
