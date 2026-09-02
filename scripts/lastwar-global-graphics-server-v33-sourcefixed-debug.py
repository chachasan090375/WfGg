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

spec = importlib.util.spec_from_file_location('wfgg_v33_sourcefixed_debug', BASE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DebugHandler(m.c.CorrelatedHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/lab/global-graphics-v33/search-correlation-v33.js':
            raw = JS.read_text('utf-8').replace(
                'const AUTO_SKIP_RUNTIME_FAILURES=true;',
                'const AUTO_SKIP_RUNTIME_FAILURES=false;'
            )
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
    print('=== WFGG V33 — SOURCE FIX + ERRORS VISIBLE ===', flush=True)
    print('V33_AUTO_SKIP runtime-failures=OFF (diagnostic mode)', flush=True)
    print('V33_SOURCE_AUDIT', repr(m.AUDIT), flush=True)
    print(f'http://127.0.0.1:{m.core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', m.core.PORT), DebugHandler).serve_forever()
