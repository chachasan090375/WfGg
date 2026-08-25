from pathlib import Path

p = Path('frontend/_worker.js')
s = p.read_text(encoding='utf-8')
original = s

marker = 'WFGG_TRAIN_PORTAL_PRESENCE_TOKEN_FIX_V1'
anchor = '    /* WFGG_TRAIN_INIT_DOM_GUARD_V1'

block = """    /* WFGG_TRAIN_PORTAL_PRESENCE_TOKEN_FIX_V1
       Le frontend Train historique vérifie encore `token` avant le heartbeat,
       alors que cette variable n'existe plus dans le mode session Portail.
       Le bridge fetch porte désormais l'authentification via
       X-WfGg-Portal-Token : seul l'état de visibilité reste à vérifier ici.
    */
    rewritten = rewritten.replace(
      \"        if(!token || document.visibilityState!=='visible')return;\",
      \"        if(document.visibilityState!=='visible')return;\"
    );

"""

if marker not in s:
    if anchor not in s:
        raise SystemExit('missing DOM guard anchor')
    s = s.replace(anchor, block + anchor, 1)

s = s.replace('wfgg_bridge=v8', 'wfgg_bridge=v9')
s = s.replace("wfgg_fresh','v8'", "wfgg_fresh','v9'")

if s == original:
    print('PRESENCE_FRONTEND_PATCH=ALREADY_APPLIED')
else:
    p.write_text(s, encoding='utf-8')
    print('PRESENCE_FRONTEND_PATCH=OK')
