#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V39.15 — exact runtime child-prefab preview.

Inherits V39.14 badge layout and V39.12 exact SoftReferencePrefab resolution. When a controller
prefab has no autonomous Mesh, the browser may render a proven/local child prefab (WORK preferred,
then IDLE) through the existing exact V33 model endpoint. This is a state preview, not a guessed
parent+child merge: no visual-similarity substitution and no synthetic geometry/motion.
"""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import importlib.util, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v3913-layout.py'
RESOLVER_JS=ROOT/'frontend/lab/global-graphics-v33/animation-resolver-v392.js'
LAYOUT_JS=ROOT/'frontend/lab/global-graphics-v33/animation-badge-layout-v3913.js'
PREVIEW_JS=ROOT/'frontend/lab/global-graphics-v33/animation-runtime-prefab-preview-v3915.js'

spec=importlib.util.spec_from_file_location('wfgg_v3914_for_v3915',BASE)
v3914=importlib.util.module_from_spec(spec);spec.loader.exec_module(v3914)
core=v3914.core


def _send_js(handler,text):
    raw=text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache');handler.send_header('Expires','0')
    handler.end_headers();handler.wfile.write(raw)


class V3915Handler(v3914.V3914Handler):
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                # Resolver + proven badge row + runtime child preview execute in one no-cache response.
                text=(RESOLVER_JS.read_text('utf-8')+'\n\n'+LAYOUT_JS.read_text('utf-8')+'\n\n'+PREVIEW_JS.read_text('utf-8')+'\n')
                return _send_js(self,text)
            except Exception as exc:
                return self.send_json({'error':'v39.15-inline-runtime-preview-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-runtime-prefab-preview-v3915.js':
            try:return _send_js(self,PREVIEW_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v39.15-runtime-preview-addon-failed','message':str(exc)},500)
        if u.path=='/api/v39/status':
            return self.send_json({
                'version':'39.15','animationDiagnostics':True,'physicalSourceRecovery':True,
                'shiftedOffsetRecovery':True,'softReferencePrefabResolver':True,
                'softReferencePhysicalRecovery':True,'softReferenceAssemblyPlan':True,
                'runtimeChildPrefabPreview':True,'runtimeChildPolicy':'exact-local-only',
                'runtimeChildDefaultOrder':['work','idle','runtime','upgrade','level-tip'],
                'mergedAssemblyEnabled':False,'syntheticGeometry':False,'syntheticAnimation':False,
                'badgeRealFlexRow':True,'artworkBadgeOverlap':False,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF'
            })
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V39.15 — EXACT RUNTIME CHILD PREFAB PREVIEW ===',flush=True)
    print('V39_15_RUNTIME_CHILD exact-softrefs-only=ON WORK-first=ON IDLE-fallback=ON child-model=ON',flush=True)
    print('V39_15_ASSEMBLY parent-child-merge=OFF state-preview=ON synthetic-geometry=OFF synthetic-motion=OFF',flush=True)
    print('V39_14_BADGE inherited real-flex-row=ON artwork-overlap=OFF',flush=True)
    print('V39_12_SOFTPREFAB inherited serialized-evidence=ON exact-name-path=REQUIRED physical-recovery=ON',flush=True)
    print('V39_7_SOURCE_RECOVERY inherited shifted-offset=ON exact-asset-validation=REQUIRED',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V3915Handler).serve_forever()
