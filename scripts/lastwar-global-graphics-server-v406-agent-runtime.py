#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40.6 — V40.5 trace + staged exact serialized dependency closure."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import importlib.util,re,sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
BASE=ROOT/'scripts/lastwar-global-graphics-server-v405-agent-runtime.py'
CLOSURE_AGENT=ROOT/'scripts/lastwar-runtime-dependency-closure-v406.py'
CLOSURE_JS=ROOT/'frontend/lab/global-graphics-v33/animation-runtime-closure-v406.js'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

v405=load('wfgg_v405_for_v406',BASE)
closure=load('wfgg_closure_v406',CLOSURE_AGENT)
core=v405.core
agent402=v405.agent402
v3915=v405.v3915
trace=v405.trace


def resolver_text():
    return v405.resolver_text()+'\n\n'+CLOSURE_JS.read_text('utf-8')+'\n'


class V406Handler(v405.V405Handler):
    def do_GET(self):
        u=urlparse(self.path);qs=parse_qs(u.query)
        if u.path=='/lab/global-graphics-v33/animation-resolver-v392.js':
            try:return v405.send_js(self,resolver_text())
            except Exception as exc:return self.send_json({'error':'v40.6-inline-ui-failed','message':str(exc)},500)
        if u.path=='/lab/global-graphics-v33/animation-runtime-closure-v406.js':
            try:return v405.send_js(self,CLOSURE_JS.read_text('utf-8'))
            except Exception as exc:return self.send_json({'error':'v40.6-closure-ui-failed','message':str(exc)},500)
        if u.path=='/api/v40/runtime-closure':
            sid=str((qs.get('id') or [''])[0]).strip().upper()
            scope=str((qs.get('scope') or ['primary'])[0]).strip().lower()
            force=str((qs.get('force') or ['1'])[0]).lower() in {'1','true','yes','on'}
            if not re.fullmatch(r'LWGA-[A-Z0-9]+',sid):return self.send_json({'error':'invalid-id'},400)
            try:
                d=closure.build_closure(sid,core,trace,agent402,v3915,scope=scope,force=force);s=d.get('summary') or {}
                print('V40_6_RUNTIME_CLOSURE',sid,'scope='+str(d.get('scope')),
                      'assets='+str(s.get('assetsScanned',0)),'bundles='+str(s.get('bundleFilesMaterialized',0)),
                      'bindings='+str(s.get('exactTextureBindings',0)),'textures='+str(s.get('textureFilesExported',0)),
                      'unresolved='+str(s.get('unresolvedAssets',0)),flush=True)
                for x in d.get('results') or []:
                    st=x.get('stage') or {}
                    print('V40_6_ASSET',x.get('stableId'),'role='+str(x.get('role')),'status='+str(x.get('status')),
                          'bindings='+str(x.get('bindingCount',0)),'files='+str(x.get('textureFileCount',0)),
                          'stage='+str(st.get('bundles','-'))+'/'+str(st.get('depth','-')),
                          'materialized='+str((x.get('sources') or {}).get('materialized',0)),flush=True)
                return self.send_json(d)
            except KeyError as exc:return self.send_json({'error':'asset-not-found','message':str(exc)},404)
            except ValueError as exc:return self.send_json({'error':'invalid-id','message':str(exc)},400)
            except Exception as exc:
                print('V40_6_RUNTIME_CLOSURE_ERROR',sid,type(exc).__name__,str(exc)[:1800],flush=True)
                return self.send_json({'error':'v40.6-runtime-closure-failed','message':str(exc)},500)
        if u.path=='/api/v40/status':
            st=agent402.cache_status();st.update({
                'version':'40.6','exactRuntimeDependencyTrace':True,'deepSerializedClosure':True,
                'stagedDependencyClosure':True,'closureStages':['48/3','96/5','160/7'],
                'materialTextureReenrichment':True,'targetScopeDefault':'root+WORK+IDLE',
                'inheritsGameRender':'40.4.1','syntheticGeometry':False,'syntheticTexture':False,'syntheticAnimation':False,
                'auditIndexCaches':'untouched','referencePrefab':'LWGA-0D0CA2A747F7DF'})
            return self.send_json(st)
        return super().do_GET()


if __name__=='__main__':
    print('=== WFGG LAST WAR V40.6 — DEEP EXACT SERIALIZED CLOSURE ===',flush=True)
    print('V40_6_TARGET root+WORK+IDLE exact-local default; all=optional',flush=True)
    print('V40_6_CLOSURE bundle_dependencies_v33 staged 48/3 -> 96/5 -> 160/7 STOP_ON_EXACT_TEXTURE=ON',flush=True)
    print('V40_6_TEXTURE Material->Texture2D Unity-PPtr reenrichment=ON exported-PNG=ON',flush=True)
    print('V40_6_RENDER existing V40.4.1 consumes refreshed objectTextures=ON',flush=True)
    print('V40_6_TRACE V40.5 bundle/fragment/APK + CLR loader evidence=ON',flush=True)
    print('V40_6_SYNTHETIC geometry=OFF texture=OFF animation=OFF',flush=True)
    print('V40_6_CACHE audit/index-visual=UNTOUCHED ptr-texture-enrichment-only=REFRESHABLE',flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html',flush=True)
    ThreadingHTTPServer(('127.0.0.1',core.PORT),V406Handler).serve_forever()
