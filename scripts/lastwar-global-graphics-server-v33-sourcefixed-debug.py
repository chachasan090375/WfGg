#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util
import mimetypes
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v33-sourcefixed.py'
JS = ROOT / 'frontend/lab/global-graphics-v33/search-correlation-v33.js'
ACCEL = ROOT / 'frontend/lab/global-graphics-v33/preview-accelerator-v34.js'
MODEL_JS = ROOT / 'frontend/lab/global-graphics-v33/model-viewer-v33.js'
PTR3D = ROOT / 'scripts/lastwar-global-graphics-ptrmodel-fast-v34.py'
# New cache generation: never reuse 3401 manifests/OBJ files produced while model-file paths were
# still being repaired. This removes stale 404s without asking the user to delete anything.
PTR3D_CACHE = Path.home() / '.cache/wfgg-lastwar-v31/models-v33-ptr-3402'
CACHE_ROOT = Path.home() / '.cache/wfgg-lastwar-v31'

spec = importlib.util.spec_from_file_location('wfgg_v33_sourcefixed_debug', BASE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# V34 3D repair/performance layer. First use a small exact dependency closure, then retry with
# the deeper exact PPtr graph only when required. The previous strict model path remains the
# final fallback. The shared model cache is also the primary directory served by /api/v33/model-file.
ptrspec = importlib.util.spec_from_file_location('wfgg_v34_ptrmodel_fast', PTR3D)
ptr3d = importlib.util.module_from_spec(ptrspec)
spec.loader.exec_module(m) if False else None
ptrspec.loader.exec_module(ptr3d)
ptr3d.install(m.c.core, m.c, PTR3D_CACHE, m.c.mobile.ORIGINAL_DEPENDENCY_ROWS)
print('V34_PTR3D_INSTALLED staged-fast-exact=ON transforms-baked=ON cache=models-v33-ptr-3402', flush=True)


def _model_cache_roots():
    """Every cache generation that a legitimate exact/fallback assembler may have used.

    The manifest URL contract contains only stable_id + relative OBJ path. During the V33/V34
    transition some fallback functions kept their own module-level MODEL_CACHE. Searching these
    known local caches is exact (same stable_id and exact relative path), so it never substitutes
    geometry from another asset while eliminating false model-file 404s.
    """
    roots = [PTR3D_CACHE]
    for obj in (
        getattr(m.c, 'core', None),
        getattr(m.c, 'exact', None),
        getattr(getattr(m.c, 'mobile', None), 'exact', None),
        getattr(getattr(m.c, 'mobile', None), 'core', None),
    ):
        try:
            value = getattr(obj, 'MODEL_CACHE', None)
            if value:
                roots.append(Path(value))
        except Exception:
            pass
    roots.extend([
        CACHE_ROOT / 'models-v33-exact',
        CACHE_ROOT / 'models-v33-mobile-3306',
        CACHE_ROOT / 'models-v33',
        CACHE_ROOT / 'models-v33-ptr-3401',
        CACHE_ROOT / 'models-v33-ptr-3402',
    ])
    out = []
    seen = set()
    for root in roots:
        try:
            root = Path(root).resolve()
        except Exception:
            continue
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _find_model_file(sid, rel):
    if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid or ''):
        return None, None
    rel = str(rel or '').replace('\\', '/').lstrip('/')
    if not rel or '..' in Path(rel).parts:
        return None, None
    for root in _model_cache_roots():
        base = (root / sid).resolve()
        p = (base / rel).resolve()
        try:
            p.relative_to(base)
        except Exception:
            continue
        if p.is_file():
            return p, root
    return None, None


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


class DebugHandler(m.c.CorrelatedHandler):
    def do_GET(self):
        u = urlparse(self.path)

        # model-viewer is parsed before the legacy inline init() call. It now contains the earliest
        # transient-error shield, so it must never be allowed to remain stale in Chrome's cache.
        if u.path == '/lab/global-graphics-v33/model-viewer-v33.js':
            _send_js(self, MODEL_JS)
            return

        if u.path == '/lab/global-graphics-v33/search-correlation-v33.js':
            raw = JS.read_text('utf-8').replace(
                'const AUTO_SKIP_RUNTIME_FAILURES=true;',
                'const AUTO_SKIP_RUNTIME_FAILURES=false;'
            )
            if ACCEL.is_file():
                raw += '\n\n' + ACCEL.read_text('utf-8')
            data = raw.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(data)
            return

        if u.path == '/api/v33/model-file':
            qs = parse_qs(u.query)
            sid = (qs.get('id') or [''])[0]
            rel = (qs.get('file') or [''])[0]
            p, root = _find_model_file(sid, rel)
            if not p:
                print('V34_MODEL_FILE_MISS', sid, rel, 'roots=' + str(len(_model_cache_roots())), flush=True)
                return self.send_json({'error': 'model-file-not-found', 'id': sid, 'file': rel}, 404)
            raw = p.read_bytes()
            ctype = mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.end_headers()
            self.wfile.write(raw)
            if root != PTR3D_CACHE.resolve():
                print('V34_MODEL_FILE_RECOVERED', sid, rel, 'cache=' + root.name, flush=True)
            return

        return super().do_GET()


if __name__ == '__main__':
    print('=== WFGG V33 — SOURCE FIX + ERRORS VISIBLE + FAST PTR3D V34 ===', flush=True)
    print('V33_AUTO_SKIP runtime-failures=OFF (diagnostic mode)', flush=True)
    print('V34_PTR3D staged-fast-exact=ON transforms-baked=ON cache=models-v33-ptr-3402', flush=True)
    print('V34_MODEL_FILE multi-cache-exact-recovery=ON', flush=True)
    print('V34_MODEL_VIEWER no-store=ON early-error-shield=ON', flush=True)
    print('V34_PREVIEW_ACCEL neutral-fallback=ON neighbor-prewarm=ON', flush=True)
    print('V33_SOURCE_AUDIT', repr(m.AUDIT), flush=True)
    print(f'http://127.0.0.1:{m.core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', m.core.PORT), DebugHandler).serve_forever()
