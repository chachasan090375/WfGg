from pathlib import Path

path = Path('frontend/_worker.js')
src = path.read_text(encoding='utf-8')

old_root = """      if (value.startsWith('/') && !value.startsWith('//')) {
        element.setAttribute(attr, `${this.prefix}${value}`);
        continue;
      }
"""
new_root = """      if (value.startsWith('/') && !value.startsWith('//')) {
        let rewrittenValue = `${this.prefix}${value}`;

        /* WFGG_TRAIN_APP_CACHE_BUST_V1
           La Preview Train doit toujours charger le bridge JS courant, même
           si un ancien service worker / cache HTTP connaît déjà /app.js.
        */
        if (
          this.prefix === '/train' &&
          attr === 'src' &&
          /^\\/app\\.js(?:[?#]|$)/i.test(value)
        ) {
          rewrittenValue +=
            (rewrittenValue.includes('?') ? '&' : '?') +
            'wfgg_bridge=v6';
        }

        element.setAttribute(attr, rewrittenValue);
        continue;
      }
"""

old_train_start = """  if(ROUTE==='train'){
    const initialPortalToken=localStorage.getItem(PORTAL_TOKEN);
"""
new_train_start = """  if(ROUTE==='train'){
    /* WFGG_TRAIN_SW_CACHE_RESET_V1
       Le frontend historique enregistrait un service worker sous /train/.
       Il peut continuer à servir un ancien app.js malgré les corrections du
       proxy. On retire uniquement les registrations dont le scope est /train/
       et les caches Train/WfGg. localStorage (donc la session Portail) reste intact.
    */
    const WFGG_SW_RESET_KEY='wfgg_train_sw_reset_v1';
    if('serviceWorker' in navigator){
      const hadTrainController=!!navigator.serviceWorker.controller;

      Promise.all([
        navigator.serviceWorker.getRegistrations()
          .then(registrations=>Promise.all(
            registrations
              .filter(registration=>{
                try{
                  return new URL(registration.scope).pathname.startsWith('/train/');
                }catch(_){return false;}
              })
              .map(registration=>registration.unregister())
          )),
        ('caches' in window)
          ? caches.keys().then(keys=>Promise.all(
              keys
                .filter(key=>/train|wfgg/i.test(key))
                .map(key=>caches.delete(key))
            ))
          : Promise.resolve([])
      ]).finally(()=>{
        if(
          hadTrainController &&
          sessionStorage.getItem(WFGG_SW_RESET_KEY)!=='1'
        ){
          sessionStorage.setItem(WFGG_SW_RESET_KEY,'1');
          const fresh=new URL(location.href);
          fresh.searchParams.set('wfgg_fresh','v6');
          location.replace(fresh.toString());
        }
      });
    }

    const initialPortalToken=localStorage.getItem(PORTAL_TOKEN);
"""

old_fix = """    rewritten = rewritten.replace(
      \"        if (token)\\n\\n        setSyncStatus('work');\",
      \"        setSyncStatus('work');\"
    );

    const jsHeaders = new Headers(headers);
"""
new_fix = """    rewritten = rewritten.replace(
      \"        if (token)\\n\\n        setSyncStatus('work');\",
      \"        setSyncStatus('work');\"
    );

    /* WFGG_TRAIN_PROXY_NO_SERVICE_WORKER_V1
       Sous le Portail unifié, le proxy est la source de vérité pour app.js.
       Ne pas réenregistrer le service worker historique qui pourrait remettre
       une version antérieure du frontend dans le chemin d'exécution.
    */
    rewritten = rewritten.replace(
      \"        if ('serviceWorker' in navigator)\\n            navigator.serviceWorker.register('service-worker.js?v=44').catch(() => { });\",
      \"        /* WFGG_TRAIN_PROXY_NO_SERVICE_WORKER_V1 */\"
    );

    const jsHeaders = new Headers(headers);
"""

old_headers = """    jsHeaders.set('Cache-Control', 'no-store');
    jsHeaders.set('X-WfGg-Train-Api-Bridge', 'v3');
"""
new_headers = """    jsHeaders.set('Cache-Control', 'no-store');
    jsHeaders.set('Pragma', 'no-cache');
    jsHeaders.set('Expires', '0');
    jsHeaders.set('X-WfGg-Train-Api-Bridge', 'v3');
    jsHeaders.set('X-WfGg-Train-Cache-Bridge', 'v1');
"""

for old, new, label in [
    (old_root, new_root, 'root asset rewriter'),
    (old_train_start, new_train_start, 'Train cache reset injection'),
    (old_fix, new_fix, 'app.js rewrite block'),
    (old_headers, new_headers, 'app.js headers')
]:
    if old not in src:
        raise SystemExit(f'Expected {label} not found; refusing blind patch')
    src = src.replace(old, new, 1)

path.write_text(src, encoding='utf-8')
print('TRAIN_CACHE_RESET_PATCH=OK')
