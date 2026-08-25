from pathlib import Path

path = Path('frontend/_worker.js')
text = path.read_text(encoding='utf-8')

marker = 'WFGG_TRAIN_INIT_LIFECYCLE_FIX_V1'
if marker in text:
    print('INIT_LIFECYCLE_PATCH=ALREADY_PRESENT')
    raise SystemExit(0)

needle = '''    rewritten = rewritten.replace(
      "        if (token)\\n\\n        setSyncStatus('work');",
      "        setSyncStatus('work');"
    );
'''

if needle not in text:
    raise SystemExit('Expected dangling-token rewrite block not found')

patch = needle + '''
    /* WFGG_TRAIN_INIT_LIFECYCLE_FIX_V1
       Le frontend Train attache historiquement init() uniquement à
       DOMContentLoaded. Quand app.js est servi/rechargé tardivement par le
       bridge du Portail, cet événement peut déjà avoir eu lieu : bootApp()
       affiche alors l'écran mais aucun onclick de navigation n'est branché.
       On garde le comportement historique pendant le chargement du DOM et on
       lance init() immédiatement lorsque le DOM est déjà prêt.
    */
    rewritten = rewritten.replace(
      "    document.addEventListener('DOMContentLoaded', init);",
      "    if (document.readyState === 'loading') {\\n" +
      "        document.addEventListener('DOMContentLoaded', init, { once: true });\\n" +
      "    } else {\\n" +
      "        init();\\n" +
      "    }"
    );
'''

text = text.replace(needle, patch, 1)

# Cache-bust the corrected Train frontend explicitly.
text = text.replace('wfgg_bridge=v6', 'wfgg_bridge=v7')
text = text.replace("fresh.searchParams.set('wfgg_fresh','v6');", "fresh.searchParams.set('wfgg_fresh','v7');")

path.write_text(text, encoding='utf-8')
print('INIT_LIFECYCLE_PATCH=OK')
