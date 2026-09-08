#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.1 — Animation Graph Agent + agent-driven runtime preview.

V40.1 keeps the deterministic V40 graph, but removes the legacy V39.15 browser loop that could
walk unrelated runtime children after WORK/IDLE failures. The browser now auto-tests only exact,
local WORK then IDLE candidates, each with a hard timeout. Other variants are manual fallbacks.
"""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import importlib.util, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v40-agent.py'
RESOLVER_JS=ROOT/'frontend/lab/global-graphics-v33/animation-resolver-v392.js'
LAYOUT_JS=ROOT/'frontend/lab/global-graphics-v33/animation-badge-layout-v3913.js'
V40_JS=ROOT/'frontend/lab/global-graphics-v33/animation-graph-agent-v40.js'
V401_RUNTIME_JS=ROOT/'frontend/lab/global-graphics-v33/animation-runtime-agent-v401.js'

spec=importlib.util.spec_from_file_location('wfgg_v40_for_v401',BASE)
v40=importlib.util.module_from_spec(spec);spec.loader.exec_module(v40)
core=v40.core


def _send_js(handler,text):
    raw=text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache');handler.send_header('Expires','0')
    handler.end_headers();handler.wfile.write(raw)


class V401Handler(v40.V40Handler):
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                # Deliberately omit V39.15 PREVIEW_JS. V40.1 owns runtime preview from the graph.
                text=(RESOLVER_JS.read_text('utf-8')+'\n\n'+LAYOUT_JS.read_text('utf-8')+'\n\n'+V40_JS.read_text('utf-8')+'\n\n'+V401_RUNTIME_JS.read_text('utf-8')+'\n')
                return _send_js(self,text)
            except Exception as exc:
                return self.send_json({'error':'v40.1-inline-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-runtime-agent-v401.js':
            try:return _send_js(self,V401_RUNTIME_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40.1-runtime-ui-failed','message':str(exc)},500)
        if u.path=='/api/v40/status':
            st=v40.agent.cache_status()
            st.update({
                'version':'40.1','deterministicGraph':True,'assemblyCSharpStaticAnalysis':True,
                'clrMethodBodyTokenScan':True,'softReferenceGraph':True,'iconToPrefabGraph':True,
                'motionRecipeConfidence':True,'runtimePreview':'agent-driven',
                'runtimeAutoVariants':['work','idle'],'runtimeModelTimeoutSeconds':10,
                'legacyBlindRuntimeLoop':False,'visualSimilarityAsRuntimeProof':False,
                'syntheticGeometry':False,'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF',
            })
            return self.send_json(st)
        if u.path=='/api/v39/status':
            return self.send_json({
                'version':'40.1','inherits':'40.0+39.14','animationDiagnostics':True,
                'physicalSourceRecovery':True,'shiftedOffsetRecovery':True,
                'softReferencePrefabResolver':True,'runtimeChildPrefabPreview':True,
                'runtimeChildPolicy':'V40-agent-work-idle-only-auto','runtimeTimeoutSeconds':10,
                'animationGraphAgent':True,'assemblyCSharpStaticAnalysis':True,
                'syntheticGeometry':False,'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF'
            })
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR V40.1 — AGENT-DRIVEN RUNTIME ===',flush=True)
    print('V40_1_GRAPH inherited deterministic Unity/CLR evidence=ON persistent-cache=ON',flush=True)
    print('V40_1_RUNTIME auto=WORK,IDLE exact-local-only timeout=10s unrelated-runtime-auto=OFF',flush=True)
    print('V40_1_LEGACY V39.15 blind-child-loop=REMOVED',flush=True)
    print('V40_1_MOTION synthetic=OFF visual-similarity-runtime-proof=OFF',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V401Handler).serve_forever()
