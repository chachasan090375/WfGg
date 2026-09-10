from pathlib import Path
import hashlib

app_path=Path('frontend/train-native/app.v15.js')
worker_path=Path('frontend/_worker.js')
sha_path=Path('frontend/train-native/app.v15.js.sha256')

app=app_path.read_text()
worker=worker_path.read_text()

if 'WFGG_TRAIN_BOOT_DIAGNOSTIC_V8' not in app:
    needle="""              document.body.appendChild(panel);\n              document.getElementById('wfggTrainBootRetryV6')?.addEventListener('click',()=>location.reload());\n            }\n"""
    replacement="""              document.body.appendChild(panel);\n              document.getElementById('wfggTrainBootRetryV6')?.addEventListener('click',()=>location.reload());\n            }\n            /* WFGG_TRAIN_BOOT_DIAGNOSTIC_V8\n               Diagnostic en lecture seule du snapshot réellement appelé par le\n               navigateur. N'affiche ni jeton ni donnée sensible : seulement le\n               code HTTP, l'étape backend et le message d'erreur déjà prévu par\n               le diagnostic Sentinel V10. */\n            if(panel && !panel.dataset.wfggDiagV8){\n              panel.dataset.wfggDiagV8='1';\n              const diag=document.createElement('div');\n              diag.id='wfggTrainBootDiagV8';\n              diag.style.cssText='margin:18px auto 0;padding:12px 14px;max-width:480px;border-radius:12px;background:rgba(255,255,255,.08);font-size:13px;line-height:1.45;text-align:left;word-break:break-word';\n              diag.textContent='Diagnostic Train en cours…';\n              panel.appendChild(diag);\n              (async()=>{\n                try{\n                  const r=await fetch('/api/snapshot?wfgg_boot_diag=v8',{\n                    method:'GET',\n                    cache:'no-store',\n                    credentials:'same-origin',\n                    headers:{'X-WfGg-Sentinel-Diagnostic':'v10'}\n                  });\n                  let data={};\n                  try{data=await r.json();}catch(_){ }\n                  const sd=data&&data.sentinelDiagnostic;\n                  const stage=sd&&sd.stage?String(sd.stage):'inconnue';\n                  const source=sd&&sd.source?String(sd.source):'';\n                  const message=String((data&&data.error)||('HTTP '+r.status));\n                  diag.textContent='Diagnostic : HTTP '+r.status+' · '+stage+(source?' · '+source:'')+' · '+message;\n                }catch(e){\n                  diag.textContent='Diagnostic : réseau · '+String(e&&e.message||e||'erreur inconnue');\n                }\n              })();\n            }\n"""
    if needle not in app:
        raise SystemExit('V8 app insertion point not found')
    app=app.replace(needle,replacement,1)

# Force a fresh Worker-generated app.js URL on phones already holding V7.
if 'wfgg_diag=v8' not in worker:
    if 'wfgg_auth=v7' not in worker:
        raise SystemExit('V7 cache-bust marker not found in worker')
    worker=worker.replace('wfgg_auth=v7','wfgg_auth=v7&wfgg_diag=v8')

app_path.write_text(app)
worker_path.write_text(worker)
sha=hashlib.sha256(app.encode()).hexdigest()
sha_path.write_text(f'{sha}  app.v15.js\n')
print('WFGG_TRAIN_BOOT_DIAGNOSTIC_V8=PATCHED')
print('APP_SHA256='+sha)
