import fs from 'node:fs';

const WORKER='frontend/_worker.js';
const SENTINEL='frontend/train-native/sentinel-train-v1.js';
let worker=fs.readFileSync(WORKER,'utf8');
let sentinel=fs.readFileSync(SENTINEL,'utf8');

function replaceOnce(label, source, before, after){
  const first=source.indexOf(before);
  if(first<0) throw new Error(`${label}: source pattern missing`);
  if(source.indexOf(before,first+before.length)>=0) throw new Error(`${label}: source pattern repeated`);
  return source.replace(before,after);
}

// 1) Le logo WfGg du bandeau Train doit revenir au vrai Portail, jamais à la landing historique Train.
const passiveMarker=`    console.info('WFGG_TRAIN_PASSIVE_SPLASH_SENTINEL_V4=ACTIVE');`;
const polishBlock=`    console.info('WFGG_TRAIN_PASSIVE_SPLASH_SENTINEL_V4=ACTIVE');

    /* WFGG_TRAIN_PORTAL_HOME_AND_PROFILE_POLISH_V5
       - le logo #brandHome retourne toujours au Portail global ;
       - la photo de profil de la carte Moi est légèrement agrandie ;
       - aucune de ces règles ne participe au bootstrap/authentification. */
    if(!document.getElementById('wfggTrainPolishV5')){
      const polish=document.createElement('style');
      polish.id='wfggTrainPolishV5';
      polish.textContent='#appView .hero-card .profile-head{gap:16px!important;align-items:center!important}#appView .hero-card .profile-head>.avatar.sm{width:78px!important;height:78px!important;min-width:78px!important;object-fit:cover!important;border-radius:19px!important;border:2px solid rgba(226,196,112,.72)!important;box-shadow:0 8px 22px rgba(0,0,0,.28),0 0 0 3px rgba(255,255,255,.035)!important}@media(max-width:420px){#appView .hero-card .profile-head>.avatar.sm{width:72px!important;height:72px!important;min-width:72px!important;border-radius:17px!important}}';
      document.head.appendChild(polish);
    }
    document.addEventListener('click',function(event){
      const target=event.target&&event.target.closest?event.target.closest('#brandHome'):null;
      if(!target)return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const homeLang=norm(localStorage.getItem(PORTAL_LANG))||'fr';
      location.assign('/?lang='+homeLang);
    },true);`;
worker=replaceOnce('portal home + profile polish',worker,passiveMarker,polishBlock);

// 2) Sentinel utilise un proxy Portail same-origin dédié : pas de collision avec /api Train et pas de dépendance CORS.
const apiMarker=`      /* WFGG_TRAIN_API_PROXY
         Les API historiques du frontend Train utilisent /api/*.
         Le Portail les transmet au backend Train.
      */`;
const portalProxy=`      /* WFGG_SENTINEL_PORTAL_PROXY_V5
         Routes Portail strictement dédiées à Sentinel. Elles gardent l'authentification
         Bearer du Portail et évitent que le routage /api du contexte Train les envoie
         par erreur au Worker Train. Les contrôles OWNER restent côté wfgg-api. */
      if (url.pathname === '/portal-api/me') {
        return await proxyRoute(request, UPSTREAMS.portalApi, '/api/me', {
          routeName: 'portal-sentinel-api'
        });
      }
      if (url.pathname === '/portal-api/sentinel/run') {
        return await proxyRoute(request, UPSTREAMS.portalApi, '/api/sentinel/run', {
          routeName: 'portal-sentinel-api'
        });
      }

${apiMarker}`;
worker=replaceOnce('sentinel portal proxy',worker,apiMarker,portalProxy);

// Cache-bust Sentinel après le correctif.
worker=replaceOnce(
  'sentinel cache bust v5',
  worker,
  `script.src='/train/sentinel-train-v1.js?v=004';`,
  `script.src='/train/sentinel-train-v1.js?v=005';`
);

// 3) Sentinel : endpoint same-origin, ancrage DOM direct sur le h2 de la carte Moi, retry OWNER.
sentinel=replaceOnce(
  'sentinel portal endpoint',
  sentinel,
  `  const PORTAL_API = 'https://wfgg-api.chachasan090375.workers.dev';`,
  `  const PORTAL_API = '/portal-api';`
);
sentinel=replaceOnce(
  'sentinel version',
  sentinel,
  `  const VERSION = 'sentinel-train-v1';`,
  `  const VERSION = 'sentinel-train-v5';`
);

const oldPortalFetch=`  async function portalFetch(path) {
    const response = await fetch(PORTAL_API + path, {
      method: 'GET',
      headers: { 'Authorization': \`Bearer \${token()}\`, 'Accept': 'application/json' },
      mode: 'cors', credentials: 'omit', cache: 'no-store'
    });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    return { response, data };
  }`;
const newPortalFetch=`  async function portalFetch(path) {
    const suffix = String(path || '').replace(/^\\/api(?=\\/|$)/, '');
    const response = await fetch(PORTAL_API + suffix, {
      method: 'GET',
      headers: { 'Authorization': \`Bearer \${token()}\`, 'Accept': 'application/json' },
      credentials: 'omit', cache: 'no-store'
    });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    return { response, data };
  }`;
sentinel=replaceOnce('same-origin portalFetch',sentinel,oldPortalFetch,newPortalFetch);

const findStart=sentinel.indexOf('  function findNameAnchor() {');
const findEnd=sentinel.indexOf('\n\n  function syncButtonState()',findStart);
if(findStart<0||findEnd<0) throw new Error('findNameAnchor block not found');
const newFind=`  function findNameAnchor() {
    /* WFGG_SENTINEL_NAME_ANCHOR_V5
       La carte Moi est la cible autoritative visuelle. On ne dépend plus de la
       forme du roster local pour retrouver le pseudo avant d'afficher le bouton. */
    const anchor = document.querySelector('#appView:not(.hidden) .hero-card .profile-name h2');
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return null;
    return anchor;
  }`;
sentinel=sentinel.slice(0,findStart)+newFind+sentinel.slice(findEnd);

const oldInit=`  async function init() {
    installStyle();
    if (!(await confirmOwner())) return;
    let tries = 0;
    const timer = setInterval(() => { tries += 1; if (injectButton() || tries > 100) clearInterval(timer); }, 120);
    const observer = new MutationObserver(() => { if (ownerConfirmed) injectButton(); });
    observer.observe(document.documentElement,{childList:true,subtree:true});
  }`;
const newInit=`  async function init() {
    installStyle();
    /* WFGG_SENTINEL_OWNER_RETRY_V5
       Le script est chargé juste après le boot ; la session Portail peut encore
       être en train de se stabiliser. On retente sans jamais afficher le bouton
       tant que OWNER n'a pas été validé par le serveur. */
    let ownerTry = 0;
    while (ownerTry < 8 && !(await confirmOwner())) {
      ownerTry += 1;
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    if (!ownerConfirmed) {
      console.warn('WFGG_SENTINEL_OWNER_V5=NOT_CONFIRMED');
      return;
    }
    console.info('WFGG_SENTINEL_OWNER_V5=CONFIRMED');
    let tries = 0;
    const timer = setInterval(() => { tries += 1; if (injectButton() || tries > 120) clearInterval(timer); }, 120);
    const observer = new MutationObserver(() => { if (ownerConfirmed) injectButton(); });
    observer.observe(document.documentElement,{childList:true,subtree:true});
  }`;
sentinel=replaceOnce('owner retry',sentinel,oldInit,newInit);

// Le h2 reste propre et le bouton rond s'aligne à droite du pseudo.
sentinel=replaceOnce(
  'sentinel name anchor css',
  sentinel,
  `.wfgg-sentinel-name-anchor{display:inline-flex!important;align-items:center!important;gap:0!important;max-width:100%}`,
  `.wfgg-sentinel-name-anchor{display:inline-flex!important;align-items:center!important;gap:8px!important;max-width:100%;white-space:nowrap}`
);
sentinel=replaceOnce(
  'sentinel button margin',
  sentinel,
  `width:36px;height:36px;min-width:36px;border-radius:999px;padding:0;margin-left:8px;`,
  `width:38px;height:38px;min-width:38px;border-radius:999px;padding:0;margin-left:2px;`
);
sentinel=replaceOnce(
  'sentinel button mobile size',
  sentinel,
  `@media(max-width:520px){#\${BUTTON_ID}{width:34px;height:34px;min-width:34px;margin-left:7px}`,
  `@media(max-width:520px){#\${BUTTON_ID}{width:36px;height:36px;min-width:36px;margin-left:1px}`
);

if(!worker.includes('WFGG_TRAIN_PORTAL_HOME_AND_PROFILE_POLISH_V5')) throw new Error('worker polish marker missing');
if(!worker.includes('WFGG_SENTINEL_PORTAL_PROXY_V5')) throw new Error('worker sentinel proxy marker missing');
if(!worker.includes("script.src='/train/sentinel-train-v1.js?v=005'")) throw new Error('worker sentinel v005 missing');
if(!sentinel.includes('WFGG_SENTINEL_NAME_ANCHOR_V5')) throw new Error('sentinel name anchor v5 missing');
if(!sentinel.includes('WFGG_SENTINEL_OWNER_RETRY_V5')) throw new Error('sentinel owner retry v5 missing');

fs.writeFileSync(WORKER,worker);
fs.writeFileSync(SENTINEL,sentinel);
console.log('WFGG_TRAIN_POLISH_SENTINEL_V5=PATCHED');
