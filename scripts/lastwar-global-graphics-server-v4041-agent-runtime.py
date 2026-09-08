#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.4.1 — V40.4 exact game render + recovery from proven V40.3 assembly session."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import importlib.util, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v404-agent-runtime.py'
PATCH_JS=ROOT/'frontend/lab/global-graphics-v33/animation-game-render-v4041.js'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

v404=load('wfgg_v404_for_v4041',BASE)
core=v404.core


def send_js(handler,text):
    raw=text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache');handler.send_header('Expires','0')
    handler.end_headers();handler.wfile.write(raw)


class V4041Handler(v404.V404Handler):
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                v403=v404.v403
                text=(v403.v402.v401.RESOLVER_JS.read_text('utf-8')+'\n\n'+
                      v403.v402.v401.LAYOUT_JS.read_text('utf-8')+'\n\n'+
                      v403.v402.v401.V40_JS.read_text('utf-8')+'\n\n'+
                      v403.v402.PATCH_JS.read_text('utf-8')+'\n\n'+
                      v403.v402.v401.V401_RUNTIME_JS.read_text('utf-8')+'\n\n'+
                      v403.ASSEMBLY_JS.read_text('utf-8')+'\n\n'+
                      v403.EXACT_ID_JS.read_text('utf-8')+'\n\n'+
                      v404.GAME_JS.read_text('utf-8')+'\n\n'+
                      PATCH_JS.read_text('utf-8')+'\n')
                return send_js(self,text)
            except Exception as exc:
                return self.send_json({'error':'v40.4.1-inline-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-game-render-v4041.js':
            try:return send_js(self,PATCH_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40.4.1-recovery-ui-failed','message':str(exc)},500)
        if u.path=='/api/v40/status':
            st=v404.v403.v402.agent402.cache_status();st.update({
                'version':'40.4.1',
                'recursivePrefabAssembly':True,'assemblyDepth':3,
                'exactMaterialTextureBindings':True,'uvMaterialRenderer':'WFGGModelViewer-v35.2-WebGL',
                'gameRenderRecovery':'reuse-proven-v40.3-session',
                'canonicalModelFileRetry':True,
                'recalculateGraphOnRecovery':False,
                'motionPlaybackPolicy':'blocked until exact target + axis/speed evidence',
                'syntheticGeometry':False,'syntheticTexture':False,'syntheticAnimation':False,
                'referencePrefab':'LWGA-0D0CA2A747F7DF'})
            return self.send_json(st)
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR V40.4.1 — EXACT GAME RENDER RECOVERY ===',flush=True)
    print('V40_4_BASE exact recursive material/UV render=ON',flush=True)
    print('V40_4_1_RECOVERY reuse-proven-V40.3-session=ON',flush=True)
    print('V40_4_1_FETCH original-object-url + canonical-model-file-retry=ON',flush=True)
    print('V40_4_1_RECALCULATE graph-on-recovery=OFF',flush=True)
    print('V40_4_1_TEXTURE exact Material->Texture2D bindings preserved=ON',flush=True)
    print('V40_4_1_SYNTHETIC geometry=OFF texture=OFF animation=OFF',flush=True)
    print('V40_4_1_CACHE audit/index-visual=UNTOUCHED',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V4041Handler).serve_forever()
