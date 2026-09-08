#!/usr/bin/env python3
from __future__ import annotations

"""V39.8 browser diagnostic hotfix.

V39 animation-viewer exposes WFGGAnimationV39.last as a getter backed by the module-local
lastData. The successful fetch path also attempted to assign to that getter-only property,
throwing TypeError and incorrectly replacing a valid Unity diagnostic with an error card.

This wrapper serves the same V39 viewer script with that redundant assignment removed. No
catalogue, audit, visual-index, bundle, animation or rendering data is changed.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import importlib.util, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v397-recovery.py'

spec = importlib.util.spec_from_file_location('wfgg_v397_for_v398', BASE)
v397 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v397)

core = v397.core
ORIGINAL_JS = v397.v39.V39_JS
BAD = 'window.WFGGAnimationV39.last=d;'
GOOD = '/* V39.8: lastData is already updated; WFGGAnimationV39.last is getter-only. */'


def _send_patched_js(handler):
    text = ORIGINAL_JS.read_text('utf-8')
    count = text.count(BAD)
    if count != 1:
        raise RuntimeError('V39_8_EXPECTED_ASSIGNMENT_COUNT_' + str(count))
    raw = text.replace(BAD, GOOD).encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/javascript; charset=utf-8')
    handler.send_header('Content-Length', str(len(raw)))
    handler.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma', 'no-cache')
    handler.send_header('Expires', '0')
    handler.end_headers()
    handler.wfile.write(raw)


class HotfixHandler(v397.RecoveryHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/lab/global-graphics-v33/animation-viewer-v39.js':
            try:
                return _send_patched_js(self)
            except Exception as exc:
                print('V39_8_JS_HOTFIX_ERROR', type(exc).__name__, str(exc), flush=True)
                return self.send_json({'error':'v39.8-js-hotfix-failed','message':str(exc)},500)
        if u.path == '/api/v39/status':
            return self.send_json({
                'version':'39.8',
                'animationDiagnostics':True,
                'getterOnlyLastHotfix':True,
                'physicalSourceRecovery':True,
                'shiftedOffsetRecovery':True,
                'exactAssetValidationRequired':True,
                'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299',
                'referencePrefab':'LWGA-0D0CA2A747F7DF'
            })
        return super().do_GET()


if __name__ == '__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V39.8 — DIAGNOSTIC STATE HOTFIX ===', flush=True)
    print('V39_8_BROWSER getter-only-last-assignment=REMOVED valid-api-diagnostic-preserved=ON', flush=True)
    print('V39_7_SOURCE_RECOVERY inherited=ON shifted-offset=ON exact-asset-validation=REQUIRED', flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), HotfixHandler).serve_forever()
