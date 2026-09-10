from pathlib import Path

app = Path('frontend/train-native/app.v15.js')
text = app.read_text(encoding='utf-8')
old = """        /* WFGG_PORTAL_ONLY_TRAIN_BOOT_V4\n           Un cache Train local ne constitue jamais une authentification. Sous\n           /train/, le snapshot Portail doit être revalidé à chaque ouverture. */\n        if (location.pathname === '/train' || location.pathname.startsWith('/train/')) {\n          try {\n            const refreshed = await syncSnapshot({ render: false, quiet: true });\n            const ready = !!(refreshed && state.currentUserId && user());\n            if (!ready) throw new Error('snapshot_without_identity');\n            console.info('WFGG_PORTAL_ONLY_TRAIN_BOOT_V4=READY');\n            bootApp();\n          } catch (e) {\n            console.error('WFGG_PORTAL_ONLY_TRAIN_BOOT_V4=REJECTED', String(e && e.message || e));\n            state.currentUserId = null;\n            saveState();\n            const returnTo = encodeURIComponent(location.pathname + location.search);\n            location.replace('/?returnTo=' + returnTo);\n          }\n        } else {\n          showPortal();\n        }\n"""
new = """        /* WFGG_PORTAL_ONLY_TRAIN_BOOT_V6\n           Le contrôle d'accès est déjà effectué côté Worker AVANT de servir\n           /train/. Le frontend ne refait donc pas un second snapshot et ne\n           redirige jamais silencieusement vers le Portail sur une panne de\n           synchronisation. Il réutilise le snapshot autoritatif obtenu plus haut. */\n        if (location.pathname === '/train' || location.pathname.startsWith('/train/')) {\n          const ready = !!(ok && state.currentUserId && user());\n          if (ready) {\n            console.info('WFGG_PORTAL_ONLY_TRAIN_BOOT_V6=READY');\n            bootApp();\n          } else {\n            console.error('WFGG_PORTAL_ONLY_TRAIN_BOOT_V6=DATA_UNAVAILABLE');\n            document.getElementById('portalView')?.classList.add('hidden');\n            document.getElementById('loginView')?.classList.add('hidden');\n            document.getElementById('wfggTrainPortalGate')?.remove();\n            document.getElementById('wfggTrainGateStyle')?.remove();\n            let panel=document.getElementById('wfggTrainBootErrorV6');\n            if(!panel){\n              panel=document.createElement('div');\n              panel.id='wfggTrainBootErrorV6';\n              panel.style.cssText='max-width:560px;margin:56px auto;padding:24px;border-radius:18px;background:#171522;color:#fff;font:500 15px/1.5 system-ui,sans-serif;text-align:center';\n              panel.innerHTML='<h2 style=\"margin-top:0\">Train momentanément indisponible</h2><p>Ta session Portail est valide, mais les données Train n’ont pas pu être synchronisées.</p><button id=\"wfggTrainBootRetryV6\" style=\"padding:11px 16px;border:0;border-radius:12px;font-weight:700\">Réessayer</button>';\n              document.body.appendChild(panel);\n              document.getElementById('wfggTrainBootRetryV6')?.addEventListener('click',()=>location.reload());\n            }\n          }\n        } else {\n          showPortal();\n        }\n"""
if old not in text:
    raise SystemExit('portal-only boot V4 block not found')
text = text.replace(old, new, 1)
if "location.replace('/?returnTo=' + returnTo)" in text:
    raise SystemExit('client returnTo redirect still present')
app.write_text(text, encoding='utf-8')

worker = Path('frontend/_worker.js')
w = worker.read_text(encoding='utf-8')
count = w.count('wfgg_auth=v4')
if count < 1:
    raise SystemExit('wfgg_auth=v4 cache-bust not found')
w = w.replace('wfgg_auth=v4', 'wfgg_auth=v6')
worker.write_text(w, encoding='utf-8')

# Refresh checksum expected by the Train source contract.
import hashlib
sha = hashlib.sha256(app.read_bytes()).hexdigest()
Path('frontend/train-native/app.v15.js.sha256').write_text(f'{sha}  app.v15.js\n', encoding='utf-8')

# Keep the Pages production verification aligned with the current cleanboot V2 asset.
deploy = Path('.github/workflows/deploy-cloudflare-pages-v1.yml')
d = deploy.read_text(encoding='utf-8')
d = d.replace("portal-train-cleanboot-v1.js?v=001", "portal-train-cleanboot-v1.js?v=002-session-bridge")
d = d.replace("WFGG_PORTAL_TRAIN_CLEANBOOT_V1", "WFGG_PORTAL_TRAIN_CLEANBOOT_V2")
deploy.write_text(d, encoding='utf-8')

print('WFGG_PORTAL_ONLY_TRAIN_BOOT_V6=PATCHED')
