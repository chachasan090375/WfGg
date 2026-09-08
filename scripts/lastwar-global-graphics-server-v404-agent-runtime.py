#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.4 — V40.3.1 exact recursive assembly + exact UV/material game render."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import importlib.util, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v403-agent-runtime.py'
GAME_JS=ROOT/'frontend/lab/global-graphics-v33/animation-game-render-v404.js'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

v403=load('wfgg_v403_for_v404',BASE)
core=v403.core


def send_js(handler,text):
    raw=text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache');handler.send_header('Expires','0')
    handler.end_headers();handler.wfile.write(raw)


class V404Handler(v403.V403Handler):
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:
                text=(v403.v402.v401.RESOLVER_JS.read_text('utf-8')+'\n\n'+
                      v403.v402.v401.LAYOUT_JS.read_text('utf-8')+'\n\n'+
                      v403.v402.v401.V40_JS.read_text('utf-8')+'\n\n'+
                      v403.v402.PATCH_JS.read_text('utf-8')+'\n\n'+
                      v403.v402.v401.V401_RUNTIME_JS.read_text('utf-8')+'\n\n'+
                      v403.ASSEMBLY_JS.read_text('utf-8')+'\n\n'+
                      v403.EXACT_ID_JS.read_text('utf-8')+'\n\n'+
                      GAME_JS.read_text('utf-8')+'\n')
                return send_js(self,text)
            except Exception as exc:
                return self.send_json({'error':'v40.4-inline-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-game-render-v404.js':
            try:return send_js(self,GAME_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40.4-game-ui-failed','message':str(exc)},500)
        if u.path=='/api/v40/status':
            st=v403.v402.agent402.cache_status();st.update({
                'version':'40.4',
                'recursiveMethodDefCallGraph':True,
                'continuousVsInitialization':True,
                'recursivePrefabAssembly':True,
                'assemblyDepth':3,
                'assemblyTransformProof':'exact or unique-suffix V39 nodePath restWorldMatrix',
                'exactMaterialTextureBindings':True,
                'uvMaterialRenderer':'WFGGModelViewer-v35.2-WebGL',
                'texturePolicy':'exact Material->Texture2D PPtr only for automatic game render',
                'continuousMotionEvidenceShown':True,
                'motionPlaybackPolicy':'blocked until exact target + axis/speed evidence',
                'noAnimationRootChildPolicy':'nonfatal-exact-leaf',
                'exactStableIdClientPreviewBypass':True,
                'syntheticGeometry':False,'syntheticTexture':False,'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299','referencePrefab':'LWGA-0D0CA2A747F7DF'})
            return self.send_json(st)
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR V40.4 — EXACT GAME RENDER ===',flush=True)
    print('V40_2_CODE recursive CLR lifecycle tracing=ON',flush=True)
    print('V40_4_ASSEMBLY recursive-depth=3 exact-or-unique-suffix-nodePath=ON',flush=True)
    print('V40_4_TEXTURE exact Material->Texture2D PPtr bindings=ON UV=ON WebGL=ON',flush=True)
    print('V40_4_GAME_RENDER auto-upgrade-after-V40.3-assembly=ON',flush=True)
    print('V40_4_MOTION continuous-evidence=ON playback=ONLY_WHEN_TARGET_AXIS_SPEED_PROVED',flush=True)
    print('V40_4_SYNTHETIC geometry=OFF texture=OFF animation=OFF',flush=True)
    print('V40_4_CACHE audit/index-visual=UNTOUCHED',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V404Handler).serve_forever()
