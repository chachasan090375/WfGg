#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import importlib.util
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v33-sourcefixed.py'
JS = ROOT / 'frontend/lab/global-graphics-v33/search-correlation-v33.js'
ACCEL = ROOT / 'frontend/lab/global-graphics-v33/preview-accelerator-v34.js'
PTR3D = ROOT / 'scripts/lastwar-global-graphics-ptrmodel-fast-v34.py'
# New cache generation: never reuse 3401 manifests/OBJ files produced while model-file paths were
# still being repaired. This removes stale 404s without asking the user to delete anything.
PTR3D_CACHE = Path.home() / '.cache/wfgg-lastwar-v31/models-v33-ptr-3402'

spec = importlib.util.spec_from_file_location('wfgg_v33_sourcefixed_debug', BASE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# V34 3D repair/performance layer. First use a small exact dependency closure, then retry with
# the deeper exact PPtr graph only when required. The previous strict model path remains the
# final fallback. The shared model cache is also the directory served by /api/v33/model-file.
ptrspec = importlib.util.spec_from_file_location('wfgg_v34_ptrmodel_fast', PTR3D)
ptr3d = importlib.util.module_from_spec(ptrspec)
ptrspec.loader.exec_module(ptr3d)
ptr3d.install(m.c.core, m.c, PTR3D_CACHE, m.c.mobile.ORIGINAL_DEPENDENCY_ROWS)
print('V34_PTR3D_INSTALLED staged-fast-exact=ON transforms-baked=ON cache=models-v33-ptr-3402', flush=True)


class DebugHandler(m.c.CorrelatedHandler):
    def do_GET(self):
        u = urlparse(self.path)
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
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()


if __name__ == '__main__':
    print('=== WFGG V33 — SOURCE FIX + ERRORS VISIBLE + FAST PTR3D V34 ===', flush=True)
    print('V33_AUTO_SKIP runtime-failures=OFF (diagnostic mode)', flush=True)
    print('V34_PTR3D staged-fast-exact=ON transforms-baked=ON cache=models-v33-ptr-3402', flush=True)
    print('V34_PREVIEW_ACCEL neutral-fallback=ON neighbor-prewarm=ON', flush=True)
    print('V33_SOURCE_AUDIT', repr(m.AUDIT), flush=True)
    print(f'http://127.0.0.1:{m.core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', m.core.PORT), DebugHandler).serve_forever()
