#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V39.13 — definitive badge-row layout wrapper.

Inherits V39.12 SoftReferencePrefab resolution and injects the badge-layout add-on directly into the
always-loaded animation resolver response. This guarantees the layout fix is active before the user
opens the animation diagnostic. The top row is reserved from the preview content, so badges cannot
cover the artwork.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import importlib.util, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v3912-softprefab.py'
RESOLVER_JS = ROOT / 'frontend/lab/global-graphics-v33/animation-resolver-v392.js'
LAYOUT_JS = ROOT / 'frontend/lab/global-graphics-v33/animation-badge-layout-v3913.js'

spec = importlib.util.spec_from_file_location('wfgg_v3912_for_v3913', BASE)
v3912 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3912)
core = v3912.core


def _send_js(handler, text):
    raw = text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache')
    handler.send_header('Expires','0')
    handler.end_headers(); handler.wfile.write(raw)


class V3913Handler(v3912.V3912Handler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                text = RESOLVER_JS.read_text('utf-8')
                text += "\n;(()=>{if(!document.querySelector('script[data-wfgg-v3913-badge-layout]')){const s=document.createElement('script');s.src='/lab/global-graphics-v33/animation-badge-layout-v3913.js?v=39130';s.dataset.wfggV3913BadgeLayout='1';document.head.appendChild(s);}})();\n"
                return _send_js(self, text)
            except Exception as exc:
                return self.send_json({'error':'v39.13-resolver-loader-failed','message':str(exc)},500)
        if u.path == '/lab/global-graphics-v33/animation-badge-layout-v3913.js':
            try:
                return _send_js(self, LAYOUT_JS.read_text('utf-8'))
            except Exception as exc:
                return self.send_json({'error':'v39.13-layout-addon-failed','message':str(exc)},500)
        if u.path == '/api/v39/status':
            base = {
                'version':'39.13',
                'animationDiagnostics':True,
                'physicalSourceRecovery':True,
                'shiftedOffsetRecovery':True,
                'softReferencePrefabResolver':True,
                'softReferencePhysicalRecovery':True,
                'softReferenceAssemblyPlan':True,
                'mergedAssemblyEnabled':False,
                'badgeSameRow':True,
                'badgeReservedGutter':54,
                'artworkBadgeOverlap':False,
                'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299',
                'referencePrefab':'LWGA-0D0CA2A747F7DF'
            }
            return self.send_json(base)
        return super().do_GET()


if __name__ == '__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V39.13 — BADGE ROW + SOFT PREFAB TRACE ===', flush=True)
    print('V39_13_BADGE same-row=ON reserved-gutter=54 artwork-overlap=OFF loader=UNCONDITIONAL', flush=True)
    print('V39_12_SOFTPREFAB inherited=ON serialized-evidence=ON exact-name-path=REQUIRED physical-recovery=ON', flush=True)
    print('V39_12_ASSEMBLY plan=ON merged-render=GUARDED_UNTIL_ALL_EXACT_LOCAL', flush=True)
    print('V39_7_SOURCE_RECOVERY inherited=ON shifted-offset=ON exact-asset-validation=REQUIRED', flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), V3913Handler).serve_forever()
