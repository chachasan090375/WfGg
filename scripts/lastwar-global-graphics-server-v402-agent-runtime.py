#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.2 — recursive lifecycle-aware Animation Graph Agent + V40.1 runtime preview."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util, re, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v401-agent-runtime.py'
AGENT402=ROOT/'scripts/lastwar-animation-graph-agent-v402.py'
PATCH_JS=ROOT/'frontend/lab/global-graphics-v33/animation-graph-agent-v402-patch.js'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

v401=load('wfgg_v401_for_v402',BASE)
agent402=load('wfgg_agent_v402',AGENT402)
core=v401.core


def _send_js(handler,text):
    raw=text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache');handler.send_header('Expires','0')
    handler.end_headers();handler.wfile.write(raw)


class V402Handler(v401.V401Handler):
    def do_GET(self):
        u=urlparse(self.path);qs=parse_qs(u.query)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                text=(v401.RESOLVER_JS.read_text('utf-8')+'\n\n'+v401.LAYOUT_JS.read_text('utf-8')+'\n\n'+
                      v401.V40_JS.read_text('utf-8')+'\n\n'+PATCH_JS.read_text('utf-8')+'\n\n'+
                      v401.V401_RUNTIME_JS.read_text('utf-8')+'\n')
                return _send_js(self,text)
            except Exception as exc:
                return self.send_json({'error':'v40.2-inline-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-graph-agent-v402-patch.js':
            try:return _send_js(self,PATCH_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40.2-ui-patch-failed','message':str(exc)},500)
        if u.path=='/api/v40/animation-graph':
            sid=str((qs.get('id') or [''])[0]).strip().upper()
            force=str((qs.get('force') or ['0'])[0]).lower() in {'1','true','yes','on'}
            if not re.fullmatch(r'LWGA-[A-Z0-9]+',sid):return self.send_json({'error':'invalid-id'},400)
            try:
                payload=agent402.build_graph(sid,v401.v40.v3915,force=force)
                ma=payload.get('motionAnalysis') or {}
                print('V40_2_GRAPH',sid,'status='+str(ma.get('status')),'continuous='+str(ma.get('continuousCount',0)),
                      'init='+str(ma.get('initializationCount',0)),'methods='+str(ma.get('methodsVisited',0)),
                      'cache='+('HIT' if payload.get('cacheHit') else 'MISS'),'seconds='+str(payload.get('scanSecondsV402')),flush=True)
                return self.send_json(payload)
            except KeyError as exc:return self.send_json({'error':'asset-not-found','message':str(exc)},404)
            except ValueError as exc:return self.send_json({'error':'invalid-id','message':str(exc)},400)
            except Exception as exc:
                print('V40_2_GRAPH_ERROR',sid,type(exc).__name__,str(exc)[:1400],flush=True)
                return self.send_json({'error':'v40.2-graph-failed','message':str(exc)},500)
        if u.path=='/api/v40/status':
            st=agent402.cache_status();st.update({
                'version':'40.2','recursiveMethodDefCallGraph':True,'lifecycleClassification':True,
                'continuousVsInitialization':True,'childScriptCodeAnalysis':True,
                'runtimePreview':'agent-driven-v40.1','runtimeAutoVariants':['work','idle'],
                'legacyBlindRuntimeLoop':False,'syntheticGeometry':False,'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF'})
            return self.send_json(st)
        if u.path=='/api/v39/status':
            return self.send_json({
                'version':'40.2','inherits':'40.1+39.14','animationDiagnostics':True,
                'physicalSourceRecovery':True,'shiftedOffsetRecovery':True,'softReferencePrefabResolver':True,
                'runtimeChildPolicy':'V40-agent-work-idle-only-auto','animationGraphAgent':True,
                'recursiveMethodDefCallGraph':True,'continuousVsInitialization':True,
                'syntheticGeometry':False,'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF'})
            return self.send_json({})
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR V40.2 — RECURSIVE ANIMATION GRAPH AGENT ===',flush=True)
    print('V40_2_CODE MethodDef-callgraph=RECURSIVE depth=7 lifecycle=FRAME|INIT|STATE|TEARDOWN',flush=True)
    print('V40_2_MOTION continuous-vs-initialization=ON confidence-reweighted=ON synthetic=OFF',flush=True)
    print('V40_2_CHILDREN exact-local child-script-analysis=ON WORK-IDLE-runtime evidence=ON',flush=True)
    print('V40_2_CACHE isolated-v402=ON audit/index-visual=UNTOUCHED',flush=True)
    print('V40_1_RUNTIME inherited WORK,IDLE-auto-only timeout=10s unrelated-runtime-auto=OFF',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V402Handler).serve_forever()
