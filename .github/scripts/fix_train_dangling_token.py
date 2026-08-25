from pathlib import Path

path = Path('frontend/_worker.js')
src = path.read_text(encoding='utf-8')

old = """    const rewritten = source.split(legacyOrigin).join('');

    const jsHeaders = new Headers(headers);
"""

new = """    let rewritten = source.split(legacyOrigin).join('');

    /* WFGG_TRAIN_DANGLING_TOKEN_FIX_V1
       Le frontend portal-only-auth ne déclare plus `token`, mais conserve
       encore un `if (token)` orphelin dans api(). Cela déclenche un
       ReferenceError avant chaque fetch et empêche syncSnapshot() de poser
       state.currentUserId. On retire uniquement ce garde devenu invalide.
    */
    rewritten = rewritten.replace(
      "        if (token)\\n\\n        setSyncStatus('work');",
      "        setSyncStatus('work');"
    );

    const jsHeaders = new Headers(headers);
"""

if old not in src:
    raise SystemExit('Expected app.js rewrite block not found; refusing blind patch')

src = src.replace(old, new, 1)
path.write_text(src, encoding='utf-8')
