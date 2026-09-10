from pathlib import Path

sentinel = Path('frontend/train-native/sentinel-train-v1.js')
s = sentinel.read_text(encoding='utf-8')
old = "const VERSION = 'sentinel-train-v14.6';"
if old not in s:
    raise SystemExit('sentinel v14.6 anchor not found')
s = s.replace(old, "const VERSION = 'sentinel-train-v14.7';\n  window.__WFGG_SENTINEL_VERSION__ = VERSION;", 1)
sentinel.write_text(s, encoding='utf-8')

worker = Path('frontend/_worker.js')
w = worker.read_text(encoding='utf-8')
old_block = """    const loadSentinelAfterBoot=()=>{\n      if(document.getElementById('wfggTrainSentinelLoaderV4'))return;\n      const script=document.createElement('script');\n      script.id='wfggTrainSentinelLoaderV4';\n      script.src='/train/sentinel-train-v1.js?v=0146';\n      script.async=true;\n      script.dataset.wfggAfterBoot='1';\n      script.onerror=()=>console.warn('WFGG_SENTINEL_AFTER_BOOT_V4=LOAD_ERROR');\n      script.onload=()=>console.info('WFGG_SENTINEL_AFTER_BOOT_V4=LOADED');\n      document.head.appendChild(script);\n    };\n"""
new_block = """    /* WFGG_SENTINEL_VERSION_SELFHEAL_V14_7\n       Une instance Sentinel ancienne ne doit jamais survivre à un build plus récent.\n       Si un loader obsolète est déjà présent dans le document, on reconstruit une\n       seule fois le document Train afin d'éviter les anciens listeners encore actifs. */\n    const EXPECTED_SENTINEL_VERSION='sentinel-train-v14.7';\n    const SENTINEL_RELOAD_KEY='wfgg_sentinel_doc_reload_0147';\n    const loadSentinelAfterBoot=()=>{\n      const activeVersion=String(window.__WFGG_SENTINEL_VERSION__||'');\n      const existing=document.getElementById('wfggTrainSentinelLoaderV5')||document.getElementById('wfggTrainSentinelLoaderV4');\n      const existingSrc=String(existing?.src||'');\n      const staleActive=!!activeVersion && activeVersion!==EXPECTED_SENTINEL_VERSION;\n      const staleLoader=!!existing && !existingSrc.includes('v=0147');\n\n      if(staleActive||staleLoader){\n        if(sessionStorage.getItem(SENTINEL_RELOAD_KEY)!=='1'){\n          sessionStorage.setItem(SENTINEL_RELOAD_KEY,'1');\n          const fresh=new URL(location.href);\n          fresh.searchParams.set('wfgg_sentinel','0147');\n          location.replace(fresh.toString());\n          return;\n        }\n        existing?.remove();\n      }\n\n      if(activeVersion===EXPECTED_SENTINEL_VERSION)return;\n      const current=document.getElementById('wfggTrainSentinelLoaderV5');\n      if(current && String(current.src||'').includes('v=0147'))return;\n      current?.remove();\n\n      const script=document.createElement('script');\n      script.id='wfggTrainSentinelLoaderV5';\n      script.src='/train/sentinel-train-v1.js?v=0147';\n      script.async=true;\n      script.dataset.wfggAfterBoot='1';\n      script.dataset.wfggSentinelVersion=EXPECTED_SENTINEL_VERSION;\n      script.onerror=()=>console.warn('WFGG_SENTINEL_AFTER_BOOT_V5=LOAD_ERROR');\n      script.onload=()=>{\n        sessionStorage.removeItem(SENTINEL_RELOAD_KEY);\n        console.info('WFGG_SENTINEL_AFTER_BOOT_V5=LOADED',window.__WFGG_SENTINEL_VERSION__||'unknown');\n      };\n      document.head.appendChild(script);\n    };\n"""
if old_block not in w:
    raise SystemExit('Sentinel loader V4 anchor not found')
w = w.replace(old_block, new_block, 1)
worker.write_text(w, encoding='utf-8')
print('WFGG_SENTINEL_VERSION_SELFHEAL_V14_7=PATCHED')
