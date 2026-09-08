#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.5 — V40.4.1 render + exact runtime dependency/call-path trace."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util, re, sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v4041-agent-runtime.py'
TRACE_AGENT=ROOT/'scripts/lastwar-runtime-trace-agent-v405.py'
TRACE_JS=ROOT/'frontend/lab/global-graphics-v33/animation-runtime-trace-v405.js'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

v4041=load('wfgg_v4041_for_v405',BASE)
trace=load('wfgg_runtime_trace_v405',TRACE_AGENT)
core=v4041.core
agent402=v4041.v404.v403.v402.agent402
v3915=v4041.v404.v403.v402.v401.v40.v3915


def send_js(handler,text):
    raw=text.encode('utf-8');handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache');handler.send_header('Expires','0')
    handler.end_headers();handler.wfile.write(raw)


def resolver_text():
    v404=v4041.v404;v403=v404.v403;v402=v403.v402;v401=v402.v401
    return (v401.RESOLVER_JS.read_text('utf-8')+'\n\n'+v401.LAYOUT_JS.read_text('utf-8')+'\n\n'+
            v401.V40_JS.read_text('utf-8')+'\n\n'+v402.PATCH_JS.read_text('utf-8')+'\n\n'+
            v401.V401_RUNTIME_JS.read_text('utf-8')+'\n\n'+v403.ASSEMBLY_JS.read_text('utf-8')+'\n\n'+
            v403.EXACT_ID_JS.read_text('utf-8')+'\n\n'+v404.GAME_JS.read_text('utf-8')+'\n\n'+
            v4041.PATCH_JS.read_text('utf-8')+'\n\n'+TRACE_JS.read_text('utf-8')+'\n')


class V405Handler(v4041.V4041Handler):
    def do_GET(self):
        u=urlparse(self.path);qs=parse_qs(u.query)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:return send_js(self,resolver_text())
            except Exception as exc:return self.send_json({'error':'v40.5-inline-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-runtime-trace-v405.js':
            try:return send_js(self,TRACE_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40.5-trace-ui-failed','message':str(exc)},500)
        if u.path=='/api/v40/runtime-trace':
            sid=str((qs.get('id') or [''])[0]).strip().upper()
            force=str((qs.get('force') or ['0'])[0]).lower() in {'1','true','yes','on'}
            if not re.fullmatch(r'LWGA-[A-Z0-9]+',sid):return self.send_json({'error':'invalid-id'},400)
            try:
                d=trace.build_trace(sid,core,agent402,v3915,force=force);s=d.get('summary') or {}
                print('V40_5_RUNTIME_TRACE',sid,'relations='+str(s.get('exactRuntimeRelations',0)),
                      'physical='+str(s.get('physicalSourcesProven',0)),'loadCalls='+str(s.get('loaderCallChains',0)),
                      'textures='+str(s.get('exactTextureBindingsInCache',0)),'motion='+str(s.get('continuousMotionChains',0)),flush=True)
                return self.send_json(d)
            except KeyError as exc:return self.send_json({'error':'asset-not-found','message':str(exc)},404)
            except ValueError as exc:return self.send_json({'error':'invalid-id','message':str(exc)},400)
            except Exception as exc:
                print('V40_5_RUNTIME_TRACE_ERROR',sid,type(exc).__name__,str(exc)[:1600],flush=True)
                return self.send_json({'error':'v40.5-runtime-trace-failed','message':str(exc)},500)
        if u.path=='/api/v40/status':
            st=agent402.cache_status();st.update({
                'version':'40.5','exactRuntimeDependencyTrace':True,'cataloguePhysicalProvenance':True,
                'bundleFragmentOffsetTrace':True,'clrLoaderCallTrace':True,'clrPathLiteralTrace':True,
                'textureCacheDiagnostics':True,'continuousMotionTrace':True,
                'runtimeTracePolicy':'serialized/catalogue/CLR-token evidence only; code literals remain candidates until joined',
                'inheritsGameRender':'40.4.1','syntheticGeometry':False,'syntheticTexture':False,'syntheticAnimation':False,
                'referencePrefab':'LWGA-0D0CA2A747F7DF'})
            return self.send_json(st)
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR V40.5 — EXACT RUNTIME DEPENDENCY TRACE ===',flush=True)
    print('V40_5_TRACE Unity-serialized-prefab -> stable-id -> bundle -> BundleFragment/APK -> offset/span=ON',flush=True)
    print('V40_5_CODE CLR LoadAsset/LoadPrefab/ResourceManager/Instantiate call-chain=ON',flush=True)
    print('V40_5_LITERALS code-path-strings=CANDIDATE_ONLY until serialized/catalogue join',flush=True)
    print('V40_5_TEXTURE diagnostic Material->Texture2D cache-status/errors=ON',flush=True)
    print('V40_5_MOTION continuous-call-chain=ON target-axis-speed still proof-gated',flush=True)
    print('V40_5_RENDER inherited V40.4.1 exact geometry/UV recovery=ON',flush=True)
    print('V40_5_SYNTHETIC geometry=OFF texture=OFF animation=OFF',flush=True)
    print('V40_5_CACHE audit/index-visual=UNTOUCHED',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V405Handler).serve_forever()
