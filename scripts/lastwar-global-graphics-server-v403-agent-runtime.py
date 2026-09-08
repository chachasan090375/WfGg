#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.3.1 — V40.2 recursive code agent + exact recursive prefab assembly preview."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util, re, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v402-agent-runtime.py'
ASSEMBLY_JS=ROOT/'frontend/lab/global-graphics-v33/animation-assembly-v403.js'
EXACT_ID_JS=ROOT/'frontend/lab/global-graphics-v33/exact-id-bypass-v4031.js'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

v402=load('wfgg_v402_for_v403',BASE)
core=v402.core


def _send_js(handler,text):
    raw=text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache');handler.send_header('Expires','0')
    handler.end_headers();handler.wfile.write(raw)


def _soft_graph_no_animation_root(sid,message):
    """A local exact prefab may be renderable but have no V39 animation anchor.

    This is not an assembly failure: V40.3 can still use its exact model as a leaf part.  Returning
    a 200 leaf graph prevents a harmless animation diagnostic miss from aborting recursive assembly.
    """
    return {
        'version':'40.3.1','stableId':sid,'rootPrefab':sid,'cacheHit':False,
        'runtimePrefabs':{'items':[],'count':0},'childDiagnostics':{},
        'scriptCodeEvidence':[],'recursiveCodeEvidence':[],'motionRecipe':[],
        'motionAnalysis':{
            'status':'no-exact-animation-root','continuousCount':0,'initializationCount':0,
            'stateEventCount':0,'scriptsScanned':0,'methodsVisited':0,'bestContinuous':None},
        'summary':{'status':'no-exact-animation-root','continuousMotionFound':False,'assemblyLeaf':True},
        'diagnostic':{'nonFatal':True,'reason':'v39-animation-root-not-found','message':message},
        'policy':'Exact/local prefab remains usable as an assembly leaf when V39 finds no animation root. No synthetic relation, geometry or motion is added.'
    }


class V403Handler(v402.V402Handler):
    def do_GET(self):
        u=urlparse(self.path);qs=parse_qs(u.query)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                text=(v402.v401.RESOLVER_JS.read_text('utf-8')+'\n\n'+v402.v401.LAYOUT_JS.read_text('utf-8')+'\n\n'+
                      v402.v401.V40_JS.read_text('utf-8')+'\n\n'+v402.PATCH_JS.read_text('utf-8')+'\n\n'+
                      v402.v401.V401_RUNTIME_JS.read_text('utf-8')+'\n\n'+ASSEMBLY_JS.read_text('utf-8')+'\n\n'+
                      EXACT_ID_JS.read_text('utf-8')+'\n')
                return _send_js(self,text)
            except Exception as exc:
                return self.send_json({'error':'v40.3.1-inline-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-assembly-v403.js':
            try:return _send_js(self,ASSEMBLY_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40.3-assembly-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/exact-id-bypass-v4031.js':
            try:return _send_js(self,EXACT_ID_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40.3.1-exact-id-ui-failed','message':str(exc)},500)

        # V40.3.1: an exact/local child with no V39 animation anchor is a valid assembly leaf,
        # not a fatal graph error. Normal graph behavior remains unchanged for every other case.
        if u.path=='/api/v40/animation-graph':
            sid=str((qs.get('id') or [''])[0]).strip().upper()
            force=str((qs.get('force') or ['0'])[0]).lower() in {'1','true','yes','on'}
            if not re.fullmatch(r'LWGA-[A-Z0-9]+',sid):return self.send_json({'error':'invalid-id'},400)
            try:
                payload=v402.agent402.build_graph(sid,v402.v401.v40.v3915,force=force)
                ma=payload.get('motionAnalysis') or {}
                print('V40_3_1_GRAPH',sid,'status='+str(ma.get('status')),'continuous='+str(ma.get('continuousCount',0)),
                      'cache='+('HIT' if payload.get('cacheHit') else 'MISS'),flush=True)
                return self.send_json(payload)
            except RuntimeError as exc:
                msg=str(exc)
                if 'V39_ANIMATION_ROOT_NOT_FOUND' in msg or 'no-exact-root' in msg:
                    payload=_soft_graph_no_animation_root(sid,msg)
                    print('V40_3_1_GRAPH_LEAF',sid,'animation-root=ABSENT nonfatal=ON',flush=True)
                    return self.send_json(payload)
                print('V40_3_1_GRAPH_ERROR',sid,type(exc).__name__,msg[:1400],flush=True)
                return self.send_json({'error':'v40.3.1-graph-failed','message':msg},500)
            except KeyError as exc:return self.send_json({'error':'asset-not-found','message':str(exc)},404)
            except ValueError as exc:return self.send_json({'error':'invalid-id','message':str(exc)},400)
            except Exception as exc:
                print('V40_3_1_GRAPH_ERROR',sid,type(exc).__name__,str(exc)[:1400],flush=True)
                return self.send_json({'error':'v40.3.1-graph-failed','message':str(exc)},500)

        if u.path=='/api/v40/status':
            st=v402.agent402.cache_status();st.update({
                'version':'40.3.1','recursiveMethodDefCallGraph':True,'lifecycleClassification':True,
                'continuousVsInitialization':True,'childScriptCodeAnalysis':True,
                'runtimePreview':'agent-driven-v40.1','runtimeAutoVariants':['work','idle'],
                'recursivePrefabAssembly':True,'assemblyDepth':2,'assemblyStateVariants':['idle','work'],
                'assemblyTransformProof':'exact unique V39 nodePath restWorldMatrix',
                'assemblyRelations':'exact local SoftReferencePrefab only',
                'noAnimationRootChildPolicy':'nonfatal-exact-leaf',
                'exactStableIdClientPreviewBypass':True,
                'syntheticGeometry':False,'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF'})
            return self.send_json(st)
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR V40.3.1 — EXACT RECURSIVE PREFAB ASSEMBLY ===',flush=True)
    print('V40_2_CODE inherited recursive CLR lifecycle tracing=ON',flush=True)
    print('V40_3_ASSEMBLY root+children depth=2 state=IDLE|WORK',flush=True)
    print('V40_3_RELATIONS exact-local SoftReferencePrefab only',flush=True)
    print('V40_3_TRANSFORMS unique exact nodePath restWorldMatrix composition=ON',flush=True)
    print('V40_3_1_EXACT_ID client-preview-filter=BYPASSED for exact LWGA intent',flush=True)
    print('V40_3_1_GRAPH_LEAF no-animation-root child=NONFATAL',flush=True)
    print('V40_3_RENDER mobile OBJ budget=42 triangles=26000',flush=True)
    print('V40_3_SYNTHETIC geometry=OFF animation=OFF',flush=True)
    print('V40_3_CACHE audit/index-visual=UNTOUCHED',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V403Handler).serve_forever()
