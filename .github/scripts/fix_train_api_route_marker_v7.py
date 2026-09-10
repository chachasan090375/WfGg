from pathlib import Path

path = Path('frontend/_worker.js')
text = path.read_text(encoding='utf-8')

old_bridge = """          const portalToken=localStorage.getItem(PORTAL_TOKEN);\n\n          if(portalToken){\n            const headers=new Headers(\n              options.headers ||\n              (input instanceof Request ? input.headers : undefined)\n            );\n\n            headers.set('X-WfGg-Portal-Token',portalToken);\n            if(headers.get('Authorization')==='Bearer '+TRAIN_BRIDGE_SENTINEL){\n              headers.delete('Authorization');\n            }\n\n            const directUrl=\n              WFGG_TRAIN_API_ORIGIN+target.pathname+target.search;\n\n            if(input instanceof Request){\n              const bridged=new Request(input,{...options,headers});\n              const method=String(bridged.method||'GET').toUpperCase();\n              const directOptions={\n                method,\n                headers:new Headers(bridged.headers),\n                mode:'cors',\n                credentials:'same-origin',\n                cache:bridged.cache,\n                redirect:bridged.redirect,\n                referrerPolicy:bridged.referrerPolicy,\n                keepalive:bridged.keepalive,\n                signal:bridged.signal\n              };\n\n              if(method!=='GET'&&method!=='HEAD'){\n                directOptions.body=await bridged.clone().arrayBuffer();\n              }\n\n              return WFGG_NATIVE_FETCH(directUrl,directOptions);\n            }\n\n            return WFGG_NATIVE_FETCH(directUrl,{\n              ...options,\n              headers,\n              mode:'cors',\n              credentials:'same-origin'\n            });\n          }\n"""

new_bridge = """          const portalToken=localStorage.getItem(PORTAL_TOKEN);\n\n          /* WFGG_TRAIN_API_ROUTE_MARKER_V7\n             Le module Train marque explicitement ses appels same-origin. Le\n             Worker n'a plus besoin de déduire le backend à partir du Referer,\n             qui peut être absent selon le navigateur / la politique referrer.\n             Ce marqueur ne vaut pas authentification : le cookie Portail\n             HttpOnly reste revalidé par le backend Train. */\n          const headers=new Headers(\n            options.headers ||\n            (input instanceof Request ? input.headers : undefined)\n          );\n          headers.set('X-WfGg-Module','train');\n          if(portalToken){\n            headers.set('X-WfGg-Portal-Token',portalToken);\n          }\n          if(headers.get('Authorization')==='Bearer '+TRAIN_BRIDGE_SENTINEL){\n            headers.delete('Authorization');\n          }\n\n          const directUrl=\n            WFGG_TRAIN_API_ORIGIN+target.pathname+target.search;\n\n          if(input instanceof Request){\n            const bridged=new Request(input,{...options,headers});\n            const method=String(bridged.method||'GET').toUpperCase();\n            const directOptions={\n              method,\n              headers:new Headers(bridged.headers),\n              mode:'cors',\n              credentials:'same-origin',\n              cache:bridged.cache,\n              redirect:bridged.redirect,\n              referrerPolicy:bridged.referrerPolicy,\n              keepalive:bridged.keepalive,\n              signal:bridged.signal\n            };\n\n            if(method!=='GET'&&method!=='HEAD'){\n              directOptions.body=await bridged.clone().arrayBuffer();\n            }\n\n            return WFGG_NATIVE_FETCH(directUrl,directOptions);\n          }\n\n          return WFGG_NATIVE_FETCH(directUrl,{\n            ...options,\n            headers,\n            mode:'cors',\n            credentials:'same-origin'\n          });\n"""

if old_bridge not in text:
    raise SystemExit('Train fetch bridge block not found')
text = text.replace(old_bridge, new_bridge, 1)

old_route = """        const hasPortalTrainToken =\n          request.headers.has('X-WfGg-Portal-Token');\n        const cookiePortalTrainToken = portalSessionCookie(request);\n\n        let fromTrainPage = false;\n"""
new_route = """        const hasPortalTrainToken =\n          request.headers.has('X-WfGg-Portal-Token');\n        const cookiePortalTrainToken = portalSessionCookie(request);\n        const hasTrainModuleMarker =\n          String(request.headers.get('X-WfGg-Module') || '').trim().toLowerCase() === 'train';\n\n        let fromTrainPage = false;\n"""
if old_route not in text:
    raise SystemExit('API route prelude not found')
text = text.replace(old_route, new_route, 1)

old_choice = """        const apiRoute =\n          (fromTrainPage || hasPortalTrainToken)\n            ? UPSTREAMS.trainApi\n            : UPSTREAMS.portalApi;\n"""
new_choice = """        const apiRoute =\n          (hasTrainModuleMarker || fromTrainPage || hasPortalTrainToken)\n            ? UPSTREAMS.trainApi\n            : UPSTREAMS.portalApi;\n"""
if old_choice not in text:
    raise SystemExit('API route choice not found')
text = text.replace(old_choice, new_choice, 1)

if text.count('WFGG_TRAIN_API_ROUTE_MARKER_V7') != 1:
    raise SystemExit('unexpected V7 marker count')

if text.count('wfgg_auth=v6') < 1:
    raise SystemExit('wfgg_auth=v6 cache bust not found')
text = text.replace('wfgg_auth=v6', 'wfgg_auth=v7')

path.write_text(text, encoding='utf-8')
print('WFGG_TRAIN_API_ROUTE_MARKER_V7=PATCHED')
