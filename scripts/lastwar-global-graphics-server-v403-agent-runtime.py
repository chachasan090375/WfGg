#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.3 — V40.2 recursive code agent + exact recursive prefab assembly preview."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import importlib.util, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v402-agent-runtime.py'
ASSEMBLY_JS=ROOT/'frontend/lab/global-graphics-v33/animation-assembly-v403.js'


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


class V403Handler(v402.V402Handler):
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                text=(v402.v401.RESOLVER_JS.read_text('utf-8')+'\n\n'+v402.v401.LAYOUT_JS.read_text('utf-8')+'\n\n'+
                      v402.v401.V40_JS.read_text('utf-8')+'\n\n'+v402.PATCH_JS.read_text('utf-8')+'\n\n'+
                      v402.v401.V401_RUNTIME_JS.read_text('utf-8')+'\n\n'+ASSEMBLY_JS.read_text('utf-8')+'\n')
                return _send_js(self,text)
            except Exception as exc:
                return self.send_json({'error':'v40.3-inline-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-assembly-v403.js':
            try:return _send_js(self,ASSEMBLY_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40.3-assembly-ui-failed','message':str(exc)},500)
        if u.path=='/api/v40/status':
            st=v402.agent402.cache_status();st.update({
                'version':'40.3','recursiveMethodDefCallGraph':True,'lifecycleClassification':True,
                'continuousVsInitialization':True,'childScriptCodeAnalysis':True,
                'runtimePreview':'agent-driven-v40.1','runtimeAutoVariants':['work','idle'],
                'recursivePrefabAssembly':True,'assemblyDepth':2,'assemblyStateVariants':['idle','work'],
                'assemblyTransformProof':'exact unique V39 nodePath restWorldMatrix',
                'assemblyRelations':'exact local SoftReferencePrefab only',
                'syntheticGeometry':False,'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF'})
            return self.send_json(st)
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR V40.3 — EXACT RECURSIVE PREFAB ASSEMBLY ===',flush=True)
    print('V40_2_CODE inherited recursive CLR lifecycle tracing=ON',flush=True)
    print('V40_3_ASSEMBLY root+children depth=2 state=IDLE|WORK',flush=True)
    print('V40_3_RELATIONS exact-local SoftReferencePrefab only',flush=True)
    print('V40_3_TRANSFORMS unique exact nodePath restWorldMatrix composition=ON',flush=True)
    print('V40_3_RENDER mobile OBJ budget=42 triangles=26000',flush=True)
    print('V40_3_SYNTHETIC geometry=OFF animation=OFF',flush=True)
    print('V40_3_CACHE audit/index-visual=UNTOUCHED',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V403Handler).serve_forever()
