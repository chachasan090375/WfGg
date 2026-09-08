#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40 — animation graph agent server.

Inherits the complete V39.15 viewer/runtime stack and adds a deterministic on-demand animation graph
agent. The V40 cache is isolated from the V33/V35 audit/index caches.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util
import sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v3915-runtime-preview.py'
AGENT=ROOT/'scripts/lastwar-animation-graph-agent-v40.py'
RESOLVER_JS=ROOT/'frontend/lab/global-graphics-v33/animation-resolver-v392.js'
LAYOUT_JS=ROOT/'frontend/lab/global-graphics-v33/animation-badge-layout-v3913.js'
PREVIEW_JS=ROOT/'frontend/lab/global-graphics-v33/animation-runtime-prefab-preview-v3915.js'
V40_JS=ROOT/'frontend/lab/global-graphics-v33/animation-graph-agent-v40.js'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

v3915=load('wfgg_v3915_for_v40',BASE)
agent=load('wfgg_animation_agent_v40',AGENT)
core=v3915.core


def _send_js(handler,text):
    raw=text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache');handler.send_header('Expires','0')
    handler.end_headers();handler.wfile.write(raw)


class V40Handler(v3915.V3915Handler):
    def do_GET(self):
        u=urlparse(self.path);qs=parse_qs(u.query)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                # One uncached execution path: existing V39 resolver/layout/runtime preview + V40 agent UI.
                text=(RESOLVER_JS.read_text('utf-8')+'\n\n'+LAYOUT_JS.read_text('utf-8')+'\n\n'+PREVIEW_JS.read_text('utf-8')+'\n\n'+V40_JS.read_text('utf-8')+'\n')
                return _send_js(self,text)
            except Exception as exc:
                return self.send_json({'error':'v40-inline-agent-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-graph-agent-v40.js':
            try:return _send_js(self,V40_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40-agent-ui-failed','message':str(exc)},500)
        if u.path=='/api/v40/animation-graph':
            sid=str((qs.get('id') or [''])[0]).strip().upper()
            force=str((qs.get('force') or ['0'])[0]).lower() in {'1','true','yes','on'}
            try:
                payload=agent.build_graph(sid,v3915,force=force)
                print('V40_GRAPH',sid,'root='+str(payload.get('rootPrefab')),'motion='+str(len(payload.get('motionRecipe') or [])),'children='+str(payload.get('summary',{}).get('localRuntimeChildren',0)),'cache='+('HIT' if payload.get('cacheHit') else 'MISS'),'seconds='+str(payload.get('scanSeconds')),flush=True)
                return self.send_json(payload)
            except ValueError as exc:return self.send_json({'error':'invalid-id','message':str(exc)},400)
            except KeyError as exc:return self.send_json({'error':'asset-not-found','message':str(exc)},404)
            except Exception as exc:
                print('V40_GRAPH_ERROR',sid,type(exc).__name__,str(exc)[:1200],flush=True)
                return self.send_json({'error':'v40-graph-failed','message':str(exc)},500)
        if u.path=='/api/v40/status':
            st=agent.cache_status()
            st.update({
                'version':'40.0','deterministicGraph':True,'assemblyCSharpStaticAnalysis':True,
                'clrMethodBodyTokenScan':True,'softReferenceGraph':True,'iconToPrefabGraph':True,
                'motionRecipeConfidence':True,'visualSimilarityAsRuntimeProof':False,
                'syntheticGeometry':False,'syntheticAnimation':False,
                'autoPrefetchOnAnimatedSelection':True,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF',
            })
            return self.send_json(st)
        if u.path=='/api/v39/status':
            # Keep V39 compatibility while exposing the V40 layer to the UI/debugger.
            return self.send_json({
                'version':'40.0','inherits':'39.15','animationDiagnostics':True,'physicalSourceRecovery':True,
                'shiftedOffsetRecovery':True,'softReferencePrefabResolver':True,'runtimeChildPrefabPreview':True,
                'animationGraphAgent':True,'assemblyCSharpStaticAnalysis':True,'syntheticGeometry':False,'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF'
            })
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR V40 — ANIMATION GRAPH AGENT ===',flush=True)
    print('V40_GRAPH exact-unity-relations=ON softprefabs=ON icon-to-prefab=ON persistent-cache=ON',flush=True)
    print('V40_CODE Assembly-CSharp.mdl=READ_ONLY CLR-TypeDef/MethodDef=ON method-body-token-scan=ON',flush=True)
    print('V40_MOTION evidence=API-CALLS+SERIALIZED-FIELDS confidence-labelled=ON synthetic-motion=OFF',flush=True)
    print('V40_PREFETCH selected-animated-asset=ON cache-isolated-from-audit-and-visual-index=ON',flush=True)
    print('V39_15 inherited runtime-child-preview=ON exact-only=ON',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V40Handler).serve_forever()
