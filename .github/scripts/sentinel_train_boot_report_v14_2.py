from pathlib import Path

sentinel_path=Path('frontend/train-native/sentinel-train-v1.js')
worker_path=Path('frontend/_worker.js')

sentinel=sentinel_path.read_text()
worker=worker_path.read_text()

if "const VERSION = 'sentinel-train-v14.2';" not in sentinel:
    sentinel=sentinel.replace("const VERSION = 'sentinel-train-v14.1';","const VERSION = 'sentinel-train-v14.2';",1)

if "const BOOT_BUTTON_ID = 'wfggTrainSentinelBootButton';" not in sentinel:
    needle="  const STYLE_ID = 'wfggTrainSentinelStyle';\n"
    if needle not in sentinel: raise SystemExit('STYLE_ID anchor missing')
    sentinel=sentinel.replace(needle,needle+"  const BOOT_BUTTON_ID = 'wfggTrainSentinelBootButton';\n",1)

if 'const bootReportText = () =>' not in sentinel:
    needle="  const t = (key) => TEXT[lang()][key] || TEXT.fr[key] || key;\n"
    if needle not in sentinel: raise SystemExit('translation anchor missing')
    addition="""  const bootReportText = () => ({\n    fr:'Afficher le rapport Sentinel',\n    en:'Show Sentinel report',\n    it:'Mostra il rapporto Sentinel',\n    es:'Mostrar informe Sentinel'\n  }[lang()] || 'Afficher le rapport Sentinel');\n"""
    sentinel=sentinel.replace(needle,needle+addition,1)

if 'WFGG_SENTINEL_BOOT_REPORT_V14_2' not in sentinel:
    needle="""    syncButtonState();\n    return true;\n  }\n\n  function popup() {\n"""
    if needle not in sentinel: raise SystemExit('injectButton end anchor missing')
    addition="""    syncButtonState();\n    return true;\n  }\n\n  /* WFGG_SENTINEL_BOOT_REPORT_V14_2\n     Sentinel reste accessible quand le bootstrap Train échoue avant que la\n     carte utilisateur soit rendue. Le bouton ne contourne aucun droit :\n     confirmAccess() a déjà validé OWNER/SUPERVISOR côté Portail. */\n  function injectBootButton() {\n    if (!accessConfirmed) return false;\n    const panel = document.getElementById('wfggTrainBootErrorV6');\n    if (!panel) return false;\n    let button = document.getElementById(BOOT_BUTTON_ID);\n    if (!button) {\n      button = document.createElement('button');\n      button.type = 'button';\n      button.id = BOOT_BUTTON_ID;\n      button.textContent = '🧪 ' + bootReportText();\n      button.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;gap:8px;margin:14px 7px 0;padding:11px 15px;border-radius:12px;border:1px solid rgba(220,196,255,.4);background:#292238;color:#fff;font-weight:800;cursor:pointer';\n      button.addEventListener('click', async (event) => {\n        event?.preventDefault?.();\n        event?.stopPropagation?.();\n        event?.stopImmediatePropagation?.();\n        if (launchLocked) return;\n        launchLocked = true;\n        try {\n          await openPopup();\n          await runSentinel();\n        } finally {\n          setTimeout(() => { launchLocked = false; }, 350);\n        }\n      }, true);\n      panel.appendChild(button);\n    } else {\n      button.textContent = '🧪 ' + bootReportText();\n    }\n    return true;\n  }\n\n  function popup() {\n"""
    sentinel=sentinel.replace(needle,addition,1)

if 'WFGG_SENTINEL_BOOT_LAUNCHER_INIT_V14_2' not in sentinel:
    needle="""    console.info('WFGG_SENTINEL_ACCESS_V7=CONFIRMED role=' + accessRole);\n    let tries = 0;\n    const timer = setInterval(() => { tries += 1; if (injectButton() || tries > 140) clearInterval(timer); }, 120);\n    const observer = new MutationObserver(() => { if (accessConfirmed) injectButton(); });\n    observer.observe(document.documentElement,{childList:true,subtree:true});\n"""
    if needle not in sentinel: raise SystemExit('init launcher anchor missing')
    replacement="""    console.info('WFGG_SENTINEL_ACCESS_V7=CONFIRMED role=' + accessRole);\n    /* WFGG_SENTINEL_BOOT_LAUNCHER_INIT_V14_2 */\n    const injectLaunchers = () => {\n      const normal = injectButton();\n      const boot = injectBootButton();\n      return normal || boot;\n    };\n    injectLaunchers();\n    let tries = 0;\n    const timer = setInterval(() => { tries += 1; if (injectLaunchers() || tries > 140) clearInterval(timer); }, 120);\n    const observer = new MutationObserver(() => { if (accessConfirmed) injectLaunchers(); });\n    observer.observe(document.documentElement,{childList:true,subtree:true});\n"""
    sentinel=sentinel.replace(needle,replacement,1)

if "script.src='/train/sentinel-train-v1.js?v=0142';" not in worker:
    old="script.src='/train/sentinel-train-v1.js?v=0141';"
    if old not in worker: raise SystemExit('Sentinel loader v0141 anchor missing')
    worker=worker.replace(old,"script.src='/train/sentinel-train-v1.js?v=0142';",1)

if 'WFGG_TRAIN_BOOT_SENTINEL_V14_2' not in worker:
    needle="""      const app=document.getElementById('appView');\n\n      if(app&&!app.classList.contains('hidden')){\n"""
    if needle not in worker: raise SystemExit('passive splash app anchor missing')
    replacement="""      const app=document.getElementById('appView');\n      const bootError=document.getElementById('wfggTrainBootErrorV6');\n\n      /* WFGG_TRAIN_BOOT_SENTINEL_V14_2\n         Charger le vrai Sentinel aussi lorsque le bootstrap des données Train\n         échoue. Sentinel reste hors du chemin critique et ne modifie rien. */\n      if(bootError){\n        loadSentinelAfterBoot();\n        console.info('WFGG_TRAIN_BOOT_SENTINEL_V14_2=READY');\n        return;\n      }\n\n      if(app&&!app.classList.contains('hidden')){\n"""
    worker=worker.replace(needle,replacement,1)

sentinel_path.write_text(sentinel)
worker_path.write_text(worker)
print('WFGG_SENTINEL_BOOT_REPORT_V14_2=PATCHED')
