import fs from 'node:fs';

const WORKER='frontend/_worker.js';
let src=fs.readFileSync(WORKER,'utf8');

function mustReplace(label,before,after){
  if(!src.includes(before)) throw new Error(`${label}: source pattern missing`);
  src=src.replace(before,after);
}

mustReplace(
  'reactivate forceTrainPortalEntry as passive-only shell',
`  function forceTrainPortalEntry(){
    if(ROUTE!=='train')return;

    /* WFGG_TRAIN_FORCE_GATE_DISABLED_V3
       L'ancien gate imposait un second bootstrap, un probe et une navigation
       globale par-dessus app.v15. Le bootstrap autoritatif est maintenant
       WFGG_PORTAL_DIRECT_TRAIN_BOOTSTRAP_V2 dans app.v15.js. En mode intégré,
       ce gate ne doit donc plus masquer Train ni pouvoir renvoyer vers '/'.
    */
    console.info('WFGG_TRAIN_FORCE_GATE_DISABLED_V3=ACTIVE');
    return;

    if(!localStorage.getItem(PORTAL_TOKEN))return;`,
`  function forceTrainPortalEntry(){
    if(ROUTE!=='train')return;
    if(!localStorage.getItem(PORTAL_TOKEN))return;

    /* WFGG_TRAIN_PASSIVE_SPLASH_SENTINEL_V4
       Ce wrapper n'effectue plus AUCUNE décision d'authentification, aucun probe,
       aucun reload et aucune navigation. Il sert uniquement l'animation de
       chargement, masque l'ancienne landing Train pendant le boot autoritatif
       app.v15, puis charge Sentinel APRES que #appView soit réellement visible.
    */
    console.info('WFGG_TRAIN_PASSIVE_SPLASH_SENTINEL_V4=ACTIVE');`);

const navMarker=`    /* WFGG_PORTAL_TRAIN_NAV_GUARD_V2
       Le Home et le Logout historiques reviennent au Portail global et ne doivent
       jamais réafficher la landing/login locale Train en mode session Portail.
    */`;
if(!src.includes(navMarker)) throw new Error('legacy nav marker missing');

const passiveBlock=`    /* WFGG_TRAIN_PASSIVE_SPLASH_RUNTIME_V4
       La Micheline est purement visuelle. Le démarrage reste exclusivement
       piloté par WFGG_PORTAL_DIRECT_TRAIN_BOOTSTRAP_V2 dans app.v15.js.
    */
    const loadSentinelAfterBoot=()=>{
      if(document.getElementById('wfggTrainSentinelLoaderV4'))return;
      const script=document.createElement('script');
      script.id='wfggTrainSentinelLoaderV4';
      script.src='/train/sentinel-train-v1.js?v=004';
      script.async=true;
      script.dataset.wfggAfterBoot='1';
      script.onerror=()=>console.warn('WFGG_SENTINEL_AFTER_BOOT_V4=LOAD_ERROR');
      script.onload=()=>console.info('WFGG_SENTINEL_AFTER_BOOT_V4=LOADED');
      document.head.appendChild(script);
    };

    gate();
    hideLegacyEntry();

    let passiveAttempts=0;
    const passiveWatch=()=>{
      passiveAttempts++;
      hideLegacyEntry();
      const app=document.getElementById('appView');

      if(app&&!app.classList.contains('hidden')){
        document.getElementById('wfggTrainPortalGate')?.remove();
        document.getElementById('wfggTrainGateStyle')?.remove();
        loadSentinelAfterBoot();
        console.info('WFGG_TRAIN_PASSIVE_SPLASH_SENTINEL_V4=READY');
        return;
      }

      if(passiveAttempts<180){
        setTimeout(passiveWatch,100);
        return;
      }

      /* Ne jamais masquer une vraie erreur de boot. Après 18 s on retire
         seulement le splash et on laisse app.v15 afficher son diagnostic. */
      document.getElementById('wfggTrainPortalGate')?.remove();
      document.getElementById('wfggTrainGateStyle')?.remove();
      console.warn('WFGG_TRAIN_PASSIVE_SPLASH_SENTINEL_V4=TIMEOUT');
    };

    passiveWatch();
    return;

`;
src=src.replace(navMarker,passiveBlock+navMarker);

mustReplace(
  'run Train splash immediately from injected head bridge',
`  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',function(){
      localizeGuideLanding();
      forceTrainLanguage();
      forceTrainPortalEntry();
    },{once:true});
  }else{
    localizeGuideLanding();
    forceTrainLanguage();
    forceTrainPortalEntry();
  }`,
`  /* WFGG_TRAIN_EARLY_SPLASH_V4
     Le bridge est injecté dans <head> : démarrer le splash immédiatement
     empêche l'ancienne page « Bienvenue chez WfGg » d'être peinte avant Train. */
  if(ROUTE==='train')forceTrainPortalEntry();

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',function(){
      localizeGuideLanding();
      forceTrainLanguage();
      if(ROUTE!=='train')forceTrainPortalEntry();
    },{once:true});
  }else{
    localizeGuideLanding();
    forceTrainLanguage();
    if(ROUTE!=='train')forceTrainPortalEntry();
  }`);

const appShadow=`  /* WFGG_TRAIN_NATIVE_APP_V15_SHADOW
     Première étape de consolidation : sur la branche native v15, app.js est
     servi depuis une capture vérifiée du bridge v14 réellement déployé.
     Le fallback proxy reste actif si l'asset est absent, afin de ne jamais
     casser Train pendant la migration progressive.
  */`;
if(!src.includes(appShadow)) throw new Error('native app shadow marker missing');
const sentinelShadow=`  /* WFGG_TRAIN_SENTINEL_STATIC_V4
     Sentinel est servi comme asset local du Portail mais n'est chargé qu'après
     que Train soit visible. Il reste ainsi totalement hors du chemin critique
     de démarrage de app.v15. */
  if (suffix === '/sentinel-train-v1.js') {
    const assetUrl = new URL(request.url);
    assetUrl.pathname = '/train-native/sentinel-train-v1.js';
    assetUrl.search = '';
    const assetResponse = await env.ASSETS.fetch(new Request(assetUrl.toString(), {method:'GET',headers:request.headers}));
    if (assetResponse.ok) {
      const headers = new Headers(assetResponse.headers);
      headers.set('Cache-Control','no-store');
      headers.set('Content-Type','application/javascript; charset=utf-8');
      headers.set('X-WfGg-Train-Sentinel','after-boot-v4');
      return new Response(assetResponse.body,{status:assetResponse.status,statusText:assetResponse.statusText,headers});
    }
  }

`;
src=src.replace(appShadow,sentinelShadow+appShadow);

for(const marker of [
  'WFGG_TRAIN_PASSIVE_SPLASH_SENTINEL_V4',
  'WFGG_TRAIN_PASSIVE_SPLASH_RUNTIME_V4',
  'WFGG_TRAIN_EARLY_SPLASH_V4',
  'WFGG_TRAIN_SENTINEL_STATIC_V4',
  "script.src='/train/sentinel-train-v1.js?v=004'"
]){
  if(!src.includes(marker)) throw new Error(`missing generated marker: ${marker}`);
}

fs.writeFileSync(WORKER,src);
console.log('WFGG_TRAIN_SPLASH_SENTINEL_V4=PATCHED');
