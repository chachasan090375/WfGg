from pathlib import Path

path = Path('frontend/_worker.js')
src = path.read_text(encoding='utf-8')

old_fail = """    const fail=()=>{\n      const w=words();\n      const el=gate();\n      const currentLang=norm(localStorage.getItem(PORTAL_LANG))||'fr';\n      el.innerHTML='<div><p>'+w.failed+'</p><p><a href=\"/?lang='+currentLang+'\" style=\"color:inherit\">'+w.back+'</a></p></div>';\n    };\n"""

new_fail = """    const fail=(code='')=>{\n      const w=words();\n      const el=gate();\n      const currentLang=norm(localStorage.getItem(PORTAL_LANG))||'fr';\n      const safeCode=String(code||'').replace(/[^A-Z0-9_:\\-]/gi,'').slice(0,90);\n      el.innerHTML='<div><p>'+w.failed+'</p>'+(safeCode?'<p style=\"margin:.65rem 0 1rem;opacity:.62;font:500 12px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace\">Diagnostic : '+safeCode+'</p>':'')+'<p><a href=\"/?lang='+currentLang+'\" style=\"color:inherit\">'+w.back+'</a></p></div>';\n    };\n"""

old_start = """    gate();\n    hideLegacyEntry();\n\n    let attempts=0;\n"""

new_start = """    gate();\n    hideLegacyEntry();\n\n    /* WFGG_PORTAL_TRAIN_SESSION_PROBE_V1\n       Vérifie la vraie session Portail avant d'attendre le boot du frontend Train.\n       Le résultat non sensible est conservé en sessionStorage pour diagnostic.\n    */\n    const probePortalTrain=async()=>{\n      const token=localStorage.getItem(PORTAL_TOKEN);\n      if(!token)return {ok:false,code:'NO_PORTAL_SESSION'};\n\n      try{\n        const response=await fetch(\n          'https://portal-auth-phase1-wfgg-train.chachasan090375.workers.dev/api/snapshot',\n          {\n            method:'GET',\n            headers:{\n              'X-WfGg-Portal-Token':token,\n              'Accept':'application/json'\n            },\n            mode:'cors',\n            credentials:'omit',\n            cache:'no-store'\n          }\n        );\n\n        let data=null;\n        try{data=await response.clone().json();}catch(_){}\n        const code=String((data&&data.error)||('HTTP_'+response.status));\n        const bridge=response.headers.get('X-WfGg-Portal-Bridge')||'';\n        sessionStorage.setItem(\n          'wfgg_train_bridge_probe_v1',\n          JSON.stringify({\n            ok:response.ok,\n            status:response.status,\n            code,\n            bridge,\n            at:Date.now()\n          })\n        );\n        return {ok:response.ok,code,bridge};\n      }catch(error){\n        const code='NETWORK_'+String(error&&error.name||'ERROR').toUpperCase();\n        sessionStorage.setItem(\n          'wfgg_train_bridge_probe_v1',\n          JSON.stringify({ok:false,status:0,code,at:Date.now()})\n        );\n        return {ok:false,code};\n      }\n    };\n\n    let attempts=0;\n"""

old_end = """    open();\n  }\n"""

new_end = """    probePortalTrain().then((probe)=>{\n      if(!probe.ok){\n        fail(probe.code);\n        return;\n      }\n      open();\n    });\n  }\n"""

for old, new, label in [
    (old_fail, new_fail, 'fail block'),
    (old_start, new_start, 'probe insertion'),
    (old_end, new_end, 'probe start')
]:
    if old not in src:
        raise SystemExit(f'Expected {label} not found; refusing blind patch')
    src = src.replace(old, new, 1)

path.write_text(src, encoding='utf-8')
