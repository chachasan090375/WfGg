const UPSTREAMS = {
  guides: {
    prefix: '/guides',
    origin: 'https://wfgg-guides.pages.dev'
  },
  train: {
    prefix: '/train',
    origin: 'https://portal-only-auth.wfgg-train-app.pages.dev'
  },
  portalApi: {
    prefix: '/api',
    origin: 'https://wfgg-api.chachasan090375.workers.dev'
  },
  trainApi: {
    prefix: '/api',
    origin: 'https://wfgg-train.chachasan090375.workers.dev'
  }
};

const SIMULATOR_FILES = {
  fr: 'simulateur.html',
  it: 'simulatore.html',
  en: 'simulator.html',
  es: 'simulador.html'
};

const SUPPORTED_LANGS = new Set(['fr', 'it', 'en', 'es']);

function safeLang(value, fallback = 'fr') {
  const lang = String(value || '').trim().toLowerCase().replace('_', '-').split('-')[0];
  return SUPPORTED_LANGS.has(lang) ? lang : fallback;
}

function explicitLang(value) {
  return safeLang(value, '');
}

function redirectSlash(request, pathname) {
  const url = new URL(request.url);
  url.pathname = pathname;
  return Response.redirect(url.toString(), 308);
}

/* WFGG_GUEST_SERVER_GUARD_V2
   Le cookie invité est contrôlé côté Worker : un invité ne peut pas ouvrir
   Train/Simulateur ni appeler l'API en contournant l'interface du Portail.
*/
function isGuestRequest(request) {
  const cookie = request.headers.get('Cookie') || '';
  return /(?:^|;\s*)wfgg_guest=1(?:;|$)/.test(cookie);
}

function guestRedirect(request) {
  const incoming = new URL(request.url);
  const target = new URL(request.url);
  const lang = explicitLang(incoming.searchParams.get('lang'));
  target.pathname = '/guides/';
  target.search = lang ? `?lang=${lang}` : '';
  target.hash = '';
  return Response.redirect(target.toString(), 302);
}

function upstreamRequest(request, targetUrl, options = {}) {
  const headers = new Headers(request.headers);

  /* WFGG_PORTAL_PROXY_STRIP_ORIGIN_V1
     Le navigateur parle en same-origin au portail.
     L'Origin navigateur ne doit pas être retransmis au hop interne wfgg-api.
  */
  if (options.stripOrigin) {
    headers.delete('Origin');
  }

  return new Request(targetUrl.toString(), {
    method: request.method,
    headers,
    body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
    redirect: 'manual'
  });
}

function rewriteLocation(location, route, requestUrl) {
  if (!location) return location;

  const upstreamOrigin = route.origin;
  const portalOrigin = requestUrl.origin;

  try {
    const absolute = new URL(location, upstreamOrigin);

    if (absolute.origin === upstreamOrigin) {
      return `${portalOrigin}${route.prefix}${absolute.pathname}${absolute.search}${absolute.hash}`;
    }
  } catch {}

  return location;
}

class RootAttributeRewriter {
  constructor(prefix, upstreamOrigin) {
    this.prefix = prefix;
    this.upstreamOrigin = upstreamOrigin;
  }

  element(element) {
    for (const attr of ['href', 'src', 'action', 'poster']) {
      const value = element.getAttribute(attr);
      if (!value) continue;

      /* WFGG_TRAIN_VECTOR_LOGO_V1
         Le Train intégré réutilise le logo vectoriel du Portail au lieu de
         l'ancien PNG historique. Le lien brandHome conserve son rôle de retour
         vers l'accueil général WfGg.
      */
      if (
        this.prefix === '/train' &&
        attr === 'src' &&
        /^(?:\.\/)?assets\/wfgg-logo\.png(?:[?#]|$)/i.test(value)
      ) {
        element.setAttribute(attr, '/assets/wfgg-logo-mini.svg');
        continue;
      }

      /* WFGG_TRAIN_RELATIVE_APP_CACHE_BUST_V1
         L'upstream Train référence aussi app.js relativement à /train/.
         Versionner ce cas avant la réécriture des chemins absolus.
      */
      if (
        this.prefix === '/train' &&
        attr === 'src' &&
        /^(?:\.\/)?app\.js(?:[?#]|$)/i.test(value)
      ) {
        const versioned =
          value +
          (value.includes('?') ? '&' : '?') +
          'wfgg_bridge=v15';
        element.setAttribute(attr, versioned);
        continue;
      }

      if (value.startsWith('/') && !value.startsWith('//')) {
        let rewrittenValue = `${this.prefix}${value}`;

        /* WFGG_TRAIN_APP_CACHE_BUST_V1
           La Preview Train doit toujours charger le bridge JS courant, même
           si un ancien service worker / cache HTTP connaît déjà /app.js.
        */
        if (
          this.prefix === '/train' &&
          attr === 'src' &&
          /^\/app\.js(?:[?#]|$)/i.test(value)
        ) {
          rewrittenValue +=
            (rewrittenValue.includes('?') ? '&' : '?') +
            'wfgg_bridge=v15';
        }

        element.setAttribute(attr, rewrittenValue);
        continue;
      }

      if (value.startsWith(this.upstreamOrigin)) {
        const u = new URL(value);
        element.setAttribute(attr, `${this.prefix}${u.pathname}${u.search}${u.hash}`);
      }
    }
  }
}

class PortalLegacyLinkRewriter {
  element(element) {
    const href = element.getAttribute('href');
    if (!href) return;

    if (/^https:\/\/wfgg-guides\.pages\.dev/i.test(href)) {
      const u = new URL(href);
      element.setAttribute('href', `/guides${u.pathname}${u.search}${u.hash}`);
    } else if (/^https:\/\/wfgg-train-app\.pages\.dev/i.test(href)) {
      const u = new URL(href);
      element.setAttribute('href', `/train${u.pathname}${u.search}${u.hash}`);
    }
  }
}

function languageBridgeScript(routeName) {
  const routeJson = JSON.stringify(routeName);

  return `<script id="wfgg-global-lang-bridge">
(function(){
  'use strict';

  const ROUTE=${routeJson};
  const SUPPORTED=['fr','it','en','es'];
  const PORTAL_LANG='wfgg_portal_language';
  const PORTAL_SOURCE='wfgg_portal_language_source';
  const PORTAL_TOKEN='wfgg_portal_session';
  const MODULE_KEY=ROUTE==='train'?'wfgg_train_lang':'wfgg_lang';
  const API='https://wfgg-api.chachasan090375.workers.dev';

  /* WFGG_GUEST_ROUTE_GUARD_V2
     Ne dépend pas de norm() : ce guard s'exécute avant la déclaration de norm.
  */
  const GUEST_KEY='wfgg_portal_guest_v1';
  if(localStorage.getItem(GUEST_KEY)==='1' && ROUTE!=='guides'){
    const rawGuestLang=String(localStorage.getItem(PORTAL_LANG)||'fr')
      .trim().toLowerCase().replace('_','-').split('-')[0];
    const gl=SUPPORTED.includes(rawGuestLang)?rawGuestLang:'fr';
    location.replace('/guides/?lang='+gl);
    return;
  }

  /* WFGG_PORTAL_TRAIN_FETCH_BRIDGE_V2
     Le frontend Train V1.12 ne lance son snapshot que si wfgg_train_session existe.
     Une sentinelle locale réveille ce chemin, mais elle n'est jamais envoyée au backend :
     l'identité réelle reste exclusivement la session Portail transmise par X-WfGg-Portal-Token.
  */
  const TRAIN_TOKEN='wfgg_train_session';
  const TRAIN_BRIDGE_SENTINEL='__WFGG_PORTAL_BRIDGE_V2__';
  if(ROUTE==='train'){
    /* WFGG_TRAIN_SW_CACHE_RESET_V1
       Le frontend historique enregistrait un service worker sous /train/.
       Il peut continuer à servir un ancien app.js malgré les corrections du
       proxy. On retire uniquement les registrations dont le scope est /train/
       et les caches Train/WfGg. localStorage (donc la session Portail) reste intact.
    */
    const WFGG_SW_RESET_KEY='wfgg_train_sw_reset_v1';
    if('serviceWorker' in navigator){
      const hadTrainController=!!navigator.serviceWorker.controller;
      /* WFGG_WEB_PUSH_SW_RESET_GUARD_V2 */
      let removedLegacyTrainWorker=false;

      Promise.all([
        navigator.serviceWorker.getRegistrations()
          .then(registrations=>Promise.all(
            registrations
              /* WFGG_WEB_PUSH_SW_PRESERVE_V1 */
              .filter(registration=>{
                try{
                  const scopePath=new URL(registration.scope).pathname;
                  const script=registration.active?.scriptURL||registration.waiting?.scriptURL||registration.installing?.scriptURL||'';
                  const scriptPath=script?new URL(script).pathname:'';
                  return scopePath.startsWith('/train/') && scriptPath!=='/train/wfgg-push-sw.js';
                }catch(_){return false;}
              })
              .map(async registration=>{const removed=await registration.unregister();if(removed)removedLegacyTrainWorker=true;return removed;})
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
          removedLegacyTrainWorker &&
          hadTrainController &&
          sessionStorage.getItem(WFGG_SW_RESET_KEY)!=='1'
        ){
          sessionStorage.setItem(WFGG_SW_RESET_KEY,'1');
          const fresh=new URL(location.href);
          fresh.searchParams.set('wfgg_fresh','v14');
          location.replace(fresh.toString());
        }
      });
    }

    const initialPortalToken=localStorage.getItem(PORTAL_TOKEN);
    if(initialPortalToken){
      localStorage.setItem(TRAIN_TOKEN,TRAIN_BRIDGE_SENTINEL);
    }else if(localStorage.getItem(TRAIN_TOKEN)===TRAIN_BRIDGE_SENTINEL){
      localStorage.removeItem(TRAIN_TOKEN);
    }

    const WFGG_NATIVE_FETCH=window.fetch.bind(window);
    const WFGG_TRAIN_API_ORIGIN=location.origin;

    /* WFGG_PORTAL_TRAIN_SAME_ORIGIN_API_V2
       En session Portail, le navigateur reste sur wfgg.pages.dev pour les appels Train.
       Le Worker du Portail route ensuite /api vers Train avec le token Portail.
       Le token Portail reste transmis uniquement par en-tête et jamais dans l'URL.
    */
    window.fetch=async function(input,init){
      const options=init?{...init}:{};

      try{
        const raw=
          typeof input==='string'||input instanceof URL
            ? String(input)
            : input?.url;

        const target=new URL(raw||'',location.href);

        if(
          target.origin===location.origin &&
          (target.pathname==='/api'||target.pathname.startsWith('/api/'))
        ){
          const portalToken=localStorage.getItem(PORTAL_TOKEN);

          if(portalToken){
            const headers=new Headers(
              options.headers ||
              (input instanceof Request ? input.headers : undefined)
            );

            headers.set('X-WfGg-Portal-Token',portalToken);
            if(headers.get('Authorization')==='Bearer '+TRAIN_BRIDGE_SENTINEL){
              headers.delete('Authorization');
            }

            const directUrl=
              WFGG_TRAIN_API_ORIGIN+target.pathname+target.search;

            if(input instanceof Request){
              const bridged=new Request(input,{...options,headers});
              const method=String(bridged.method||'GET').toUpperCase();
              const directOptions={
                method,
                headers:new Headers(bridged.headers),
                mode:'cors',
                credentials:'omit',
                cache:bridged.cache,
                redirect:bridged.redirect,
                referrerPolicy:bridged.referrerPolicy,
                keepalive:bridged.keepalive,
                signal:bridged.signal
              };

              if(method!=='GET'&&method!=='HEAD'){
                directOptions.body=await bridged.clone().arrayBuffer();
              }

              return WFGG_NATIVE_FETCH(directUrl,directOptions);
            }

            return WFGG_NATIVE_FETCH(directUrl,{
              ...options,
              headers,
              mode:'cors',
              credentials:'omit'
            });
          }
        }
      }catch(e){
        console.warn(
          'WFGG_TRAIN_DIRECT_API_BRIDGE_ERROR',
          String(e&&e.message||e)
        );
      }

      return WFGG_NATIVE_FETCH(input,options);
    };
  }

  const norm=v=>{
    const x=String(v||'').trim().toLowerCase().replace('_','-').split('-')[0];
    return SUPPORTED.includes(x)?x:'';
  };

  const params=new URL(location.href).searchParams;
  const fromQuery=norm(params.get('lang'));
  const pathMatch=location.pathname.match(/\\/(?:season6|interseason)\\/(fr|it|en|es)(?:\\/|$)/i);
  const fromPath=pathMatch?norm(pathMatch[1]):'';
  const fromPortal=norm(localStorage.getItem(PORTAL_LANG));
  const fromModule=norm(localStorage.getItem(MODULE_KEY));
  const fromDevice=norm((navigator.languages&&navigator.languages[0])||navigator.language);
  const lang=fromQuery||fromPath||fromPortal||fromModule||fromDevice||'fr';

  function persist(next){
    next=norm(next);
    if(!next)return;

    localStorage.setItem(PORTAL_LANG,next);
    localStorage.setItem(PORTAL_SOURCE,localStorage.getItem(PORTAL_TOKEN)?'profile':'manual');
    localStorage.setItem(MODULE_KEY,next);

    if(ROUTE==='guides'||ROUTE==='simulateur')localStorage.setItem('wfgg_lang',next);
    if(ROUTE==='train')localStorage.setItem('wfgg_train_lang',next);

    document.documentElement.lang=next;
    window.__WFGG_GLOBAL_LANG__=next;
  }

  function syncProfile(next){
    next=norm(next);
    if(!next)return;

    persist(next);

    const token=localStorage.getItem(PORTAL_TOKEN);
    if(!token)return;

    fetch(API+'/api/profile/language',{
      method:'PATCH',
      headers:{
        'Content-Type':'application/json',
        'Authorization':'Bearer '+token
      },
      body:JSON.stringify({language:next}),
      keepalive:true
    }).catch(()=>{});
  }

  persist(lang);

  /* Une arrivée avec ?lang=xx est un choix explicite du portail/module. */
  if(fromQuery)syncProfile(lang);

  /*
    Synchronisation retour Module -> Portail.
    Les Guides utilisent data-lang / data-set-lang.
    Le listener est délégué : il fonctionne aussi sur les éléments ajoutés plus tard.
  */
  document.addEventListener('click',function(event){
    const target=event.target.closest('[data-lang],[data-set-lang],a[href]');
    if(!target)return;

    let next=norm(target.dataset&&target.dataset.lang);
    if(!next)next=norm(target.dataset&&target.dataset.setLang);

    if(!next&&target.tagName==='A'){
      try{
        const u=new URL(target.href,location.href);
        const m=u.pathname.match(/\\/(fr|it|en|es)(?:\\/|$)/i);
        if(m)next=norm(m[1]);
      }catch(e){}
    }

    if(next)syncProfile(next);
  },true);

  document.addEventListener('change',function(event){
    const el=event.target;
    if(!el)return;

    const marker=((el.id||'')+' '+(el.name||'')+' '+(el.className||'')).toLowerCase();
    const next=norm(el.value);

    if(next&&(marker.includes('lang')||marker.includes('language')))syncProfile(next);
  },true);

  function localizeGuideLanding(){
    if(ROUTE!=='guides'||location.pathname!=='/guides/')return;

    const T={
      fr:{
        title:'GUIDES WfGg',
        intro:'Retrouvez les guides WfGg de Last War, les fiches visuelles, les outils et les stratégies utiles pour progresser.',
        back:'← Retour au portail général WfGg',
        s6:'Saison 6',
        s6p:'Progression, ressources, alliance, territoire, PvP, héros et fiches visuelles de la Saison 6.',
        s6go:'Ouvrir le Guide Saison 6 →',
        inter:'Inter-Saison',
        interp:"Événements, Capitole, Zone de Guerre, Codes 39/64/87, héros, équipements et stratégies d'inter-saison.",
        intergo:"Ouvrir le Guide Inter-Saison →",
        footer:'WfGg · Unis • Forts • Solidaires · Guide communautaire non officiel'
      },
      it:{
        title:'GUIDE WfGg',
        intro:'Ritrova le guide WfGg di Last War, le schede visive, gli strumenti e le strategie utili per progredire.',
        back:'← Torna al portale generale WfGg',
        s6:'Stagione 6',
        s6p:'Progressione, risorse, alleanza, territorio, PvP, eroi e schede visive della Stagione 6.',
        s6go:'Apri la Guida Stagione 6 →',
        inter:'Interstagione',
        interp:'Eventi, Campidoglio, Zona di Guerra, Codici 39/64/87, eroi, equipaggiamento e strategie di interstagione.',
        intergo:'Apri la Guida Interstagione →',
        footer:'WfGg · Uniti • Forti • Solidali · Guida comunitaria non ufficiale'
      },
      en:{
        title:'WfGg GUIDES',
        intro:'Find WfGg Last War guides, visual sheets, tools and strategies to help you progress.',
        back:'← Back to the WfGg main portal',
        s6:'Season 6',
        s6p:'Progression, resources, alliance, territory, PvP, heroes and Season 6 visual sheets.',
        s6go:'Open Season 6 Guide →',
        inter:'Interseason',
        interp:'Events, Capitol, War Zone, Codes 39/64/87, heroes, equipment and interseason strategies.',
        intergo:'Open Interseason Guide →',
        footer:'WfGg · United • Strong • Supportive · Unofficial community guide'
      },
      es:{
        title:'GUÍAS WfGg',
        intro:'Encuentra las guías WfGg de Last War, fichas visuales, herramientas y estrategias para progresar.',
        back:'← Volver al portal general WfGg',
        s6:'Temporada 6',
        s6p:'Progresión, recursos, alianza, territorio, PvP, héroes y fichas visuales de la Temporada 6.',
        s6go:'Abrir Guía Temporada 6 →',
        inter:'Intertemporada',
        interp:'Eventos, Capitolio, Zona de Guerra, Códigos 39/64/87, héroes, equipo y estrategias de intertemporada.',
        intergo:'Abrir Guía Intertemporada →',
        footer:'WfGg · Unidos • Fuertes • Solidarios · Guía comunitaria no oficial'
      }
    };

    const x=T[lang]||T.fr;
    const title=document.querySelector('.brand h1');
    const intro=document.querySelector('.brand p');
    const back=document.querySelector('.portal-back');
    const cards=document.querySelectorAll('.grid .card');
    const footer=document.querySelector('footer');

    if(title)title.textContent=x.title;
    if(intro)intro.textContent=x.intro;

    if(back){
      back.textContent=x.back;
      back.href='/?lang='+lang;
    }

    if(cards[0]){
      const h=cards[0].querySelector('h2');
      const p=cards[0].querySelector('p');
      const go=cards[0].querySelector('.go');
      if(h)h.textContent=x.s6;
      if(p)p.textContent=x.s6p;
      if(go)go.textContent=x.s6go;
      cards[0].href='/guides/season6/'+lang+'/cover.html?lang='+lang;
    }

    if(cards[1]){
      const h=cards[1].querySelector('h2');
      const p=cards[1].querySelector('p');
      const go=cards[1].querySelector('.go');
      if(h)h.textContent=x.inter;
      if(p)p.textContent=x.interp;
      if(go)go.textContent=x.intergo;
      cards[1].href='/guides/interseason/'+lang+'/index.html?lang='+lang;
    }

    if(footer)footer.textContent=x.footer;
  }

  function forceTrainLanguage(){
    if(ROUTE!=='train'||!fromQuery)return;

    /*
      Le frontend Train historique peut avoir une préférence utilisateur
      plus ancienne que localStorage. On force son propre contrôle de langue
      une seule fois après son initialisation si nécessaire.
    */
    const onceKey='wfgg_train_lang_force_'+lang+'_'+location.pathname;
    if(sessionStorage.getItem(onceKey))return;
    sessionStorage.setItem(onceKey,'1');

    const apply=()=>{
      const direct=document.querySelector('[data-lang="'+lang+'"],[data-set-lang="'+lang+'"]');
      if(direct){
        const active=direct.classList.contains('active')||
          direct.getAttribute('aria-pressed')==='true'||
          direct.getAttribute('aria-current')==='page';
        if(!active){ direct.click(); return true; }
      }

      const selects=[...document.querySelectorAll('select')];
      const select=selects.find(el=>{
        const marker=((el.id||'')+' '+(el.name||'')+' '+(el.className||'')).toLowerCase();
        return marker.includes('lang')||marker.includes('language');
      });
      if(select&&norm(select.value)!==lang){
        select.value=lang;
        select.dispatchEvent(new Event('change',{bubbles:true}));
        return true;
      }
      return false;
    };

    setTimeout(apply,120);
    setTimeout(apply,450);
    setTimeout(apply,1100);
  }

  function forceTrainPortalEntry(){
    if(ROUTE!=='train')return;
    if(!localStorage.getItem(PORTAL_TOKEN))return;

    /* WFGG_TRAIN_PASSIVE_SPLASH_SENTINEL_V4
       Ce wrapper n'effectue plus AUCUNE décision d'authentification, aucun probe,
       aucun reload et aucune navigation. Il sert uniquement l'animation de
       chargement, masque l'ancienne landing Train pendant le boot autoritatif
       app.v15, puis charge Sentinel APRES que #appView soit réellement visible.
    */
    console.info('WFGG_TRAIN_PASSIVE_SPLASH_SENTINEL_V4=ACTIVE');

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
    },true);

    const T={
      fr:{loading:'Ouverture de Train…',failed:'Impossible d’ouvrir Train avec la session Portail.',back:'Retour au portail WfGg'},
      it:{loading:'Apertura di Train…',failed:'Impossibile aprire Train con la sessione del Portale.',back:'Torna al portale WfGg'},
      en:{loading:'Opening Train…',failed:'Unable to open Train with the Portal session.',back:'Back to WfGg portal'},
      es:{loading:'Abriendo Train…',failed:'No se puede abrir Train con la sesión del Portal.',back:'Volver al portal WfGg'}
    };

    const words=()=>T[norm(localStorage.getItem(PORTAL_LANG))||'fr']||T.fr;
    const globalPortal=()=>location.assign('/?lang='+(norm(localStorage.getItem(PORTAL_LANG))||'fr'));

    const hideLegacyEntry=()=>{
      document.getElementById('loginView')?.classList.add('hidden');
      document.getElementById('portalView')?.classList.add('hidden');
    };

    /* WFGG_PORTAL_TRAIN_SESSION_SWITCH_V1
       Dans le Train intégré, l'ancien bouton d'installation devient le bouton
       explicite de changement de session. Le clic est intercepté en capture
       avant le handler historique d'installation.
    */
    const prepareSessionSwitch=()=>{
      const button=document.getElementById('installBtn');
      if(!button)return;
      const labels={
        fr:'Changer de session',
        it:'Cambia sessione',
        en:'Switch session',
        es:'Cambiar de sesión'
      };
      const current=norm(localStorage.getItem(PORTAL_LANG))||'fr';
      const label=labels[current]||labels.fr;
      button.textContent='🚪';
      button.title=label;
      button.setAttribute('aria-label',label);
      button.dataset.wfggSessionSwitch='1';
    };

    const gate=()=>{
      let el=document.getElementById('wfggTrainPortalGate');
      if(el)return el;
      el=document.createElement('div');
      el.id='wfggTrainPortalGate';
      el.setAttribute('role','status');
      el.setAttribute('aria-label',words().loading);
      el.style.cssText='position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;padding:24px;background:#101019;color:#fff;font:600 16px/1.4 system-ui,sans-serif;text-align:center';
      const style=document.createElement('style');
      style.id='wfggTrainGateStyle';
      style.textContent='@keyframes wfggTrainRide{0%{transform:translateX(-235px)}100%{transform:translateX(390px)}}@keyframes wfggWheelSpin{to{transform:rotate(360deg)}}@keyframes wfggBodyFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-1px)}}#wfggTrainPortalGate .wfgg-train-stage{position:relative;width:min(360px,86vw);height:104px;overflow:hidden}#wfggTrainPortalGate .wfgg-train-track{position:absolute;left:0;right:0;bottom:15px;height:3px;background:linear-gradient(90deg,transparent,rgba(235,235,235,.75) 8%,rgba(235,235,235,.75) 92%,transparent)}#wfggTrainPortalGate .wfgg-train-track:after{content:"";position:absolute;left:7%;right:7%;top:8px;height:3px;background:repeating-linear-gradient(90deg,rgba(190,190,190,.36) 0 12px,transparent 12px 25px)}#wfggTrainPortalGate .wfgg-train-sprite{position:absolute;left:0;bottom:25px;width:205px;height:68px;filter:drop-shadow(0 7px 12px rgba(0,0,0,.5));animation:wfggTrainRide 2.55s linear infinite}#wfggTrainPortalGate .wfgg-micheline{position:absolute;inset:0;animation:wfggBodyFloat .75s ease-in-out infinite}#wfggTrainPortalGate .wfgg-micheline svg{display:block;width:205px;height:68px;overflow:visible}#wfggTrainPortalGate .wfgg-micheline-wheel{transform-box:fill-box;transform-origin:center;animation:wfggWheelSpin .58s linear infinite}@media (prefers-reduced-motion:reduce){#wfggTrainPortalGate .wfgg-train-sprite{animation-duration:5.5s}#wfggTrainPortalGate .wfgg-micheline,#wfggTrainPortalGate .wfgg-micheline-wheel{animation:none}}';
      document.head.appendChild(style);
      el.innerHTML='<div class="wfgg-train-stage" aria-hidden="true"><div class="wfgg-train-track"></div><div class="wfgg-train-sprite"><div class="wfgg-micheline"><svg viewBox="0 0 205 68" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Micheline ancienne"><defs><linearGradient id="wfggMichCream" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f3e7c8"/><stop offset="1" stop-color="#cbbd9e"/></linearGradient><linearGradient id="wfggMichRed" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a83d37"/><stop offset="1" stop-color="#642421"/></linearGradient><linearGradient id="wfggMichMetal" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ddd8cc"/><stop offset=".5" stop-color="#827f78"/><stop offset="1" stop-color="#4a4947"/></linearGradient></defs><path d="M18 17 Q28 7 49 6 H156 Q179 7 192 20 Q198 26 199 39 L196 49 H10 L8 35 Q8 24 18 17Z" fill="url(#wfggMichCream)" stroke="#e8dec7" stroke-width="1.3"/><path d="M9 35 H199 L196 50 H10Z" fill="url(#wfggMichRed)"/><path d="M24 14 Q31 9 49 8 H158 Q174 9 185 17" fill="none" stroke="rgba(255,255,255,.68)" stroke-width="2"/><path d="M17 32 Q20 18 34 14 H48 L45 32Z" fill="#24313a" stroke="#817866" stroke-width="1"/><path d="M50 13 H72 V31 H48Z" fill="#26353e" stroke="#817866" stroke-width="1"/><rect x="76" y="13" width="22" height="18" rx="2" fill="#26353e" stroke="#817866"/><rect x="102" y="13" width="22" height="18" rx="2" fill="#26353e" stroke="#817866"/><rect x="128" y="13" width="22" height="18" rx="2" fill="#26353e" stroke="#817866"/><path d="M154 13 H168 Q179 14 187 23 L190 31 H154Z" fill="#26353e" stroke="#817866" stroke-width="1"/><path d="M66 35 V49 M139 35 V49" stroke="#d8c9aa" stroke-width="1.2" opacity=".8"/><rect x="84" y="36" width="37" height="4" rx="2" fill="#e8dcc2" opacity=".8"/><circle cx="194" cy="37" r="2.6" fill="#f6dc80" stroke="#6c5641"/><circle cx="13" cy="39" r="1.8" fill="#c63831"/><path d="M14 50 H194" stroke="#c9b99b" stroke-width="2"/><path d="M33 51 H64 M141 51 H173" stroke="#3f4042" stroke-width="4" stroke-linecap="round"/><circle class="wfgg-micheline-wheel" cx="42" cy="55" r="8" fill="#252628" stroke="url(#wfggMichMetal)" stroke-width="3"/><circle cx="42" cy="55" r="2.2" fill="#9e9b93"/><circle class="wfgg-micheline-wheel" cx="57" cy="55" r="8" fill="#252628" stroke="url(#wfggMichMetal)" stroke-width="3"/><circle cx="57" cy="55" r="2.2" fill="#9e9b93"/><circle class="wfgg-micheline-wheel" cx="149" cy="55" r="8" fill="#252628" stroke="url(#wfggMichMetal)" stroke-width="3"/><circle cx="149" cy="55" r="2.2" fill="#9e9b93"/><circle class="wfgg-micheline-wheel" cx="164" cy="55" r="8" fill="#252628" stroke="url(#wfggMichMetal)" stroke-width="3"/><circle cx="164" cy="55" r="2.2" fill="#9e9b93"/><path d="M7 43 L2 45 M199 43 L204 45" stroke="#a9a69f" stroke-width="2" stroke-linecap="round"/></svg></div></div></div>';
      document.documentElement.appendChild(el);
      return el;
    };

    const fail=(code='')=>{
      const w=words();
      const el=gate();
      const currentLang=norm(localStorage.getItem(PORTAL_LANG))||'fr';
      const safeCode=String(code||'').replace(/[^A-Z0-9_:\-]/gi,'').slice(0,90);
      el.innerHTML='<div><p>'+w.failed+'</p>'+(safeCode?'<p style="margin:.65rem 0 1rem;opacity:.62;font:500 12px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace">Diagnostic : '+safeCode+'</p>':'')+'<p><a href="/?lang='+currentLang+'" style="color:inherit">'+w.back+'</a></p></div>';
    };

    /* WFGG_TRAIN_PASSIVE_SPLASH_RUNTIME_V4
       La Micheline est purement visuelle. Le démarrage reste exclusivement
       piloté par WFGG_PORTAL_DIRECT_TRAIN_BOOTSTRAP_V2 dans app.v15.js.
    */
    const loadSentinelAfterBoot=()=>{
      if(document.getElementById('wfggTrainSentinelLoaderV4'))return;
      const script=document.createElement('script');
      script.id='wfggTrainSentinelLoaderV4';
      script.src='/train/sentinel-train-v1.js?v=013';
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

    /* WFGG_PORTAL_TRAIN_NAV_GUARD_V2
       Le Home et le Logout historiques reviennent au Portail global et ne doivent
       jamais réafficher la landing/login locale Train en mode session Portail.
    */
    document.addEventListener('click',function(event){
      if(!localStorage.getItem(PORTAL_TOKEN))return;
      const target=event.target.closest('#brandHome,#logoutBtn,#loginPortalBack,#installBtn');
      if(!target)return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const isSessionSwitch=target.id==='installBtn'||target.id==='logoutBtn';
      if(localStorage.getItem(TRAIN_TOKEN)===TRAIN_BRIDGE_SENTINEL){
        localStorage.removeItem(TRAIN_TOKEN);
      }
      if(isSessionSwitch){
        localStorage.removeItem(PORTAL_TOKEN);
      }
      globalPortal();
    },true);

    gate();
    hideLegacyEntry();
    prepareSessionSwitch();

    /* WFGG_PORTAL_TRAIN_SESSION_PROBE_V1
       Vérifie la vraie session Portail avant d'attendre le boot du frontend Train.
       Le résultat non sensible est conservé en sessionStorage pour diagnostic.
    */
    const probePortalTrain=async()=>{
      const token=localStorage.getItem(PORTAL_TOKEN);
      if(!token)return {ok:false,code:'NO_PORTAL_SESSION'};

      try{
        const response=await fetch(
          '/api/snapshot',
          {
            method:'GET',
            headers:{
              'X-WfGg-Portal-Token':token,
              'Accept':'application/json'
            },
            mode:'cors',
            credentials:'omit',
            cache:'no-store'
          }
        );

        let data=null;
        try{data=await response.clone().json();}catch(_){}
        const code=String((data&&data.error)||('HTTP_'+response.status));
        const bridge=response.headers.get('X-WfGg-Portal-Bridge')||'';
        const meId=String(data&&data.me&&data.me.id||'');
        const rosterHasMe=!!(
          meId &&
          data &&
          Array.isArray(data.roster) &&
          data.roster.some(row=>String(row&&row.id||'')===meId)
        );

        /* WFGG_PORTAL_TRAIN_SNAPSHOT_SEED_V1
           Le snapshot authentifié est exactement la source que le frontend
           Train applique dans applySnapshot(). On la précharge dans les mêmes
           clés locales afin que le prochain boot connaisse déjà currentUserId
           et le roster avant même l'exécution de init().
        */
        let seeded=false;
        if(response.ok&&meId&&rosterHasMe&&data&&data.state){
          try{
            let previous={};
            try{
              previous=JSON.parse(localStorage.getItem('wfgg_train_v13')||'{}')||{};
            }catch(_){previous={};}

            const localVariants=previous.messageVariant||{
              weekly:0,daily:0,driver:0,vip:0
            };

            const seededState={
              ...(data.state||{}),
              currentUserId:meId,
              __serverSchedule:Array.isArray(data.schedule)?data.schedule:[],
              messageVariant:localVariants,
              playerEdits:{},
              addedPlayers:[],
              removedPlayers:[]
            };

            localStorage.setItem(
              'wfgg_train_roster_cache',
              JSON.stringify(data.roster||[])
            );
            localStorage.setItem(
              'wfgg_train_v13',
              JSON.stringify(seededState)
            );
            seeded=true;
          }catch(_){seeded=false;}
        }

        sessionStorage.setItem(
          'wfgg_train_bridge_probe_v1',
          JSON.stringify({
            ok:response.ok,
            status:response.status,
            code,
            bridge,
            meId:meId?meId.slice(0,24):'',
            rosterHasMe,
            seeded,
            at:Date.now()
          })
        );
        return {ok:response.ok,code,bridge,meId,rosterHasMe,seeded};
      }catch(error){
        const code='NETWORK_'+String(error&&error.name||'ERROR').toUpperCase();
        sessionStorage.setItem(
          'wfgg_train_bridge_probe_v1',
          JSON.stringify({ok:false,status:0,code,at:Date.now()})
        );
        return {ok:false,code};
      }
    };

    let attempts=0;
    let successfulProbe=null;
    const maxAttempts=80;

    const bootDiagnostic=()=>{
      try{
        if(!window.W||typeof window.W.showTrainEntry!=='function'){
          return 'BOOT_W_NOT_READY';
        }

        const app=document.getElementById('appView');
        if(!app)return 'BOOT_APPVIEW_MISSING';

        let trainState={};
        try{
          trainState=JSON.parse(localStorage.getItem('wfgg_train_v13')||'{}')||{};
        }catch(_){return 'BOOT_STATE_INVALID';}

        const currentUserId=String(trainState.currentUserId||'');
        if(!currentUserId){
          if(successfulProbe&&successfulProbe.meId){
            return successfulProbe.rosterHasMe
              ? 'BOOT_STATE_USER_MISSING'
              : 'SNAPSHOT_ROSTER_USER_MISSING';
          }
          return 'BOOT_STATE_USER_MISSING';
        }

        let roster=[];
        try{
          roster=JSON.parse(localStorage.getItem('wfgg_train_roster_cache')||'[]');
        }catch(_){return 'BOOT_ROSTER_CACHE_INVALID';}

        if(!Array.isArray(roster)||!roster.some(row=>String(row&&row.id||'')===currentUserId)){
          return 'BOOT_LOCAL_ROSTER_USER_MISSING';
        }

        return app.classList.contains('hidden')
          ? 'BOOT_APPVIEW_STILL_HIDDEN'
          : 'BOOT_UNKNOWN';
      }catch(_){
        return 'BOOT_DIAGNOSTIC_ERROR';
      }
    };

    const open=()=>{
      attempts++;
      hideLegacyEntry();

      try{
        const app=document.getElementById('appView');
        if(app&&!app.classList.contains('hidden')){
          document.getElementById('wfggTrainPortalGate')?.remove();
          document.getElementById('wfggTrainGateStyle')?.remove();
          return;
        }

        if(window.W&&typeof window.W.showTrainEntry==='function'){
          window.W.showTrainEntry();
        }
      }catch(error){}

      hideLegacyEntry();
      if(attempts<maxAttempts)setTimeout(open,150);
      else fail(bootDiagnostic());
    };

    probePortalTrain().then((probe)=>{
      if(!probe.ok){
        fail(probe.code);
        return;
      }
      successfulProbe=probe;
      if(probe.meId&&!probe.rosterHasMe){
        fail('SNAPSHOT_ROSTER_USER_MISSING');
        return;
      }

      const seedReloadKey='wfgg_train_snapshot_seed_reload_v1';
      if(
        probe.seeded &&
        sessionStorage.getItem(seedReloadKey)!=='1'
      ){
        sessionStorage.setItem(seedReloadKey,'1');
        const fresh=new URL(location.href);
        fresh.searchParams.set('wfgg_seed','v1');
        location.replace(fresh.toString());
        return;
      }

      open();
    });
  }

  /* WFGG_TRAIN_EARLY_SPLASH_V4
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
  }
})();
</script>`;
}

async function proxyRoute(request, route, upstreamPath, options = {}) {
  const incoming = new URL(request.url);
  const target = new URL(route.origin);

  target.pathname = upstreamPath;
  target.search = incoming.search;

  const upstream = await fetch(
    upstreamRequest(request, target, {
      stripOrigin: route === UPSTREAMS.portalApi
    })
  );
  const headers = new Headers(upstream.headers);

  const location = headers.get('Location');
  if (location) {
    headers.set('Location', rewriteLocation(location, route, incoming));
  }

  headers.set('X-WfGg-Route', options.routeName || route.prefix.slice(1));
  headers.set('X-WfGg-Language-Bridge', 'v1');

  let response = new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers
  });

  const contentType = headers.get('Content-Type') || '';

  /* WFGG_TRAIN_LEGACY_API_REWRITE_V3
     Train V1.12 contient encore un API_BASE absolu vers son ancien Worker.
     Lorsque /train/app.js passe par le Portail, on remplace uniquement cet
     origin par une chaîne vide afin que les appels deviennent /api/... en
     same-origin et passent par le bridge de session Portail.
  */
  if (
    options.routeName === 'train' &&
    upstreamPath === '/app.js'
  ) {
    const source = await response.text();
    const legacyOrigin =
      'https://wfgg-train.chachasan090375.workers.dev';
    let rewritten = source.split(legacyOrigin).join('');


    /* WFGG_TRAIN_SERVER_SCHEDULE_V1
       La Bourse doit valider exactement le même planning que le backend.
       Le snapshot renvoie désormais le planning autoritatif; on l'attache à
       l'état local et schedule() l'utilise au lieu de recalculer une variante
       historique dans le navigateur.
    */
    {
      const applySnapshotTail = "        refreshRoster();\n        const serverLang=state.languages?.[state.currentUserId];";
      const applySnapshotTailFixed = "        state.__serverSchedule=Array.isArray(snap.schedule)?snap.schedule:[];\n        refreshRoster();\n        const serverLang=state.languages?.[state.currentUserId];";
      rewritten = rewritten.replace(applySnapshotTail, applySnapshotTailFixed);

      const scheduleLegacy = "    function schedule() { return generateSchedule(); }";
      const scheduleServer = "    function schedule() { return Array.isArray(state.__serverSchedule) && state.__serverSchedule.length ? state.__serverSchedule : generateSchedule(); }";
      rewritten = rewritten.replace(scheduleLegacy, scheduleServer);
    }

    /* WFGG_TRAIN_MUTATE_REFRESH_GUARD_V1
       Une mutation n'est annoncée comme réussie que si le snapshot serveur a
       pu être relu. Cela évite le faux positif 'Annonce publiée' avec un écran
       resté sur un état local périmé.
    */
    {
      const mutateRefresh = "            await syncSnapshot({ render: true, quiet: true });";
      const mutateRefreshGuard = "            const refreshed = await syncSnapshot({ render: true, quiet: true });\n            if (!refreshed) throw new Error('Modification enregistrée mais synchronisation impossible');";
      rewritten = rewritten.replace(mutateRefresh, mutateRefreshGuard);
    }

    /* WFGG_TRAIN_EXCHANGE_ORPHAN_FALLBACK_V1
       Une annonce ouverte ne doit jamais disparaître silencieusement lorsque
       son auteur n'est plus résolu dans le roster courant.
    */
    {
      const orphanLegacy = "            const p = byId[x.fromId];\n            if (!p)\n                return '';";
      const orphanFallback = "            const p = byId[x.fromId] || {id:x.fromId,pseudo:'Joueur indisponible',rank:'',avatar:'assets/icon-192.png',active:false};";
      rewritten = rewritten.replace(orphanLegacy, orphanFallback);
    }

    /* WFGG_TRAIN_ROSTER_INTEGRATION_UI_RUNTIME_V1
       Le Train servi en production reste l'upstream historique patché par le Portail.
       Ce bloc aligne ce runtime sur le contrat des trois cycles autoritatifs et
       expose les compteurs d'intégration calculés par le backend. */
    {
      const rosterIntegrationUiPatches = [
        ["                vip: ['R3', 'R2', 'R1']","                vip: ['R3']","default VIP pool"],
        ["            state.settings.rotationRanks.vip = ['R3', 'R2', 'R1'];","            state.settings.rotationRanks.vip = ['R3'];","fallback VIP pool"],
        ["    function roleKeyLabel(key) {\n        if (key === 'vip')\n            return rolePoolLabel('vip');\n        if (key === 'driver-r3')\n            return rolePoolLabel('r3driver');\n        return rolePoolLabel('officer');\n    }\n","    function roleKeyLabel(key) {\n        if (key === 'vip')\n            return rolePoolLabel('vip');\n        if (key === 'driver-r3')\n            return rolePoolLabel('r3driver');\n        return rolePoolLabel('officer');\n    }\n    /* WFGG_ROSTER_INTEGRATION_UI_V1\n       Le backend est l'autorité pour les quotas d'intégration. Le frontend\n       affiche les compteurs calculés côté serveur sans recalculer les cycles. */\n    function integrationText(fr,en,it,es){\n        const lang=currentLanguage();\n        return lang==='en'?en:lang==='it'?it:lang==='es'?es:fr;\n    }\n    function integrationPoolLabel(poolKey){\n        if(poolKey==='officer')return integrationText('Conducteur A','Driver A','Conducente A','Conductor A');\n        if(poolKey==='r3driver')return integrationText('Conducteur B','Driver B','Conducente B','Conductor B');\n        return 'VIP R3';\n    }\n    function integrationReasonLabel(reason){\n        const map={\n          new_member:integrationText('Nouveau membre','New member','Nuovo membro','Nuevo miembro'),\n          promotion:integrationText('Promotion','Promotion','Promozione','Promoción'),\n          demotion:integrationText('Rétrogradation','Demotion','Retrocessione','Descenso'),\n          reactivation:integrationText('Réactivation','Reactivation','Riattivazione','Reactivación')\n        };\n        return map[reason]||integrationText('Intégration','Integration','Integrazione','Integración');\n    }\n    function integrationTierLabel(tier){\n        const n=Number(tier)||0;\n        if(n===1)return integrationText('1er tiers','1st third','1° terzo','1.er tercio');\n        if(n===2)return integrationText('2e tiers','2nd third','2° terzo','2.º tercio');\n        if(n===3)return integrationText('dernier tiers','last third','ultimo terzo','último tercio');\n        return '';\n    }\n    function rotationIntegrationStatuses(){\n        return Array.isArray(state.rotationIntegrationStatus)?state.rotationIntegrationStatus:[];\n    }\n    function activeIntegrationStatusesFor(id){\n        return rotationIntegrationStatuses().filter(x=>String(x.memberId)===String(id)&&!x.integrationCompleted);\n    }\n    function integrationCounterLabel(x){\n        const done=Math.max(0,Number(x.completedCount)||0);\n        const remainingRaw=Number(x.remainingCount);\n        const remaining=Number.isFinite(remainingRaw)?Math.max(0,remainingRaw):Math.max(0,(Number(x.targetCount)||0)-done);\n        const target=done+remaining;\n        return `${integrationPoolLabel(x.poolKey)} ${done}/${target}`;\n    }\n    function memberIntegrationHtml(id,{compact=false}={}){\n        const rows=activeIntegrationStatusesFor(id);\n        if(!rows.length)return '';\n        const first=rows[0],head=[integrationReasonLabel(first.reason),first.previousRank&&first.newRank?`${first.previousRank}→${first.newRank}`:'',integrationTierLabel(first.tier)].filter(Boolean).join(' · ');\n        const counters=rows.map(integrationCounterLabel).join(' · ');\n        const effective=first.effectiveFrom?`${integrationText('Effet','Effective','Effetto','Efecto')} ${fmtShort(parseISO(first.effectiveFrom))}`:'';\n        return `<div class=\"warning roster-integration-status ${compact?'compact':''}\"><b>🧭 ${esc(head)}</b><br><span>${esc(counters)}</span>${effective?`<br><small>${esc(effective)}</small>`:''}</div>`;\n    }\n    function allIntegrationStatusHtml(){\n        const rows=rotationIntegrationStatuses().filter(x=>!x.integrationCompleted);\n        if(!rows.length)return `<div class=\"success\">✅ ${integrationText('Aucune intégration en cours','No integration in progress','Nessuna integrazione in corso','No hay ninguna integración en curso')}</div>`;\n        const ids=[...new Set(rows.map(x=>String(x.memberId)))];\n        return `<div class=\"option-list\">${ids.map(id=>{\n          const p=byId[id],sub=rows.filter(x=>String(x.memberId)===id),first=sub[0];\n          const head=[integrationReasonLabel(first.reason),first.previousRank&&first.newRank?`${first.previousRank}→${first.newRank}`:'',integrationTierLabel(first.tier)].filter(Boolean).join(' · ');\n          return `<div class=\"option\"><span>🧭</span><span><b>${esc(p?.pseudo||id)}</b><small>${esc(head)}<br>${esc(sub.map(integrationCounterLabel).join(' · '))}</small></span></div>`;\n        }).join('')}</div>`;\n    }\n","integration helper block"],
        ["    <button type=\"button\" class=\"stat-card stat-button\" onclick=\"W.showRotationStatus()\"><small>🔁 Rotation</small><strong>${isOut(m.id) ? 'PAUSE' : 'ACTIVE'}</strong><em>Gérer mon statut</em></button>\n  </div>\n  `;","    <button type=\"button\" class=\"stat-card stat-button\" onclick=\"W.showRotationStatus()\"><small>🔁 Rotation</small><strong>${isOut(m.id) ? 'PAUSE' : 'ACTIVE'}</strong><em>Gérer mon statut</em></button>\n  </div>\n  ${memberIntegrationHtml(m.id)}\n  `;","Moi integration card"],
        ["    <div class=\"warning\">${pools.length ? `Tu participes actuellement à : ${pools.join(' · ')}.` : 'Ton rang n’est actuellement sélectionné dans aucune rotation automatique.'}</div>\n    ${canSelfManage() ? `<button class=\"btn ${isOut(m.id) ? 'success' : 'outline'} full\" onclick=\"W.toggleRotation();W.showRotationStatus()\">${isOut(m.id) ? '✅ Reprendre la rotation' : '⏸ Me retirer de la rotation'}</button>` : ''}`);","    <div class=\"warning\">${pools.length ? `Tu participes actuellement à : ${pools.join(' · ')}.` : 'Ton rang n’est actuellement sélectionné dans aucune rotation automatique.'}</div>\n    ${memberIntegrationHtml(m.id,{compact:true})}\n    ${canSelfManage() ? `<button class=\"btn ${isOut(m.id) ? 'success' : 'outline'} full\" onclick=\"W.toggleRotation();W.showRotationStatus()\">${isOut(m.id) ? '✅ Reprendre la rotation' : '⏸ Me retirer de la rotation'}</button>` : ''}`);","rotation modal integration card"],
        ["    async function saveRotationRanks() {\n        if (!isAdmin())\n            return;\n        const rotationRanks = {};\n        for (const key of ['officer', 'r3driver', 'vip']) {\n            rotationRanks[key] = [...document.querySelectorAll(`input[data-rotation-key=\"${key}\"]:checked`)].map(x => x.value);\n            if (!rotationRanks[key].length)\n                return toast('Sélectionne au moins un rang dans chaque rotation');\n        }\n        const ok = await mutate('/api/admin/rotation-ranks', { method: 'PUT', body: JSON.stringify({ rotationRanks }) }, 'Rotations mises à jour');\n        if (ok)\n            openAdminSection('rotations');\n    }\n","    async function saveRotationRanks() {\n        if (!isAdmin()) return;\n        const rotationRanks={officer:['R5','R4'],r3driver:['R3'],vip:['R3']};\n        const ok=await mutate('/api/admin/rotation-ranks',{method:'PUT',body:JSON.stringify({rotationRanks})},'Rotations vérifiées');\n        if(ok)openAdminSection('rotations');\n    }\n","fixed saveRotationRanks"],
        ["      <div class=\"admin-panel\">\n        <h3>🎚️ Rangs autorisés</h3>\n        <p class=\"admin-lead\">Choisis librement les rangs qui participent automatiquement à chacun des trois pools. Tu peux par exemple mettre le VIP sur R3 uniquement, ou sur R3+R2+R1.</p>\n        ${rankCheckHtml('officer', 'Conducteur A — un jour sur deux')}\n        ${rankCheckHtml('r3driver', 'Conducteur B — l’autre jour')}\n        ${rankCheckHtml('vip', 'VIP — tous les jours')}\n        <div class=\"warning\">Un même rang peut être présent dans plusieurs pools. Un joueur ne pourra toutefois jamais être Conducteur et VIP le même jour.</div>\n        <button class=\"btn gold full\" onclick=\"W.saveRotationRanks()\">💾 Enregistrer les rangs autorisés</button>\n      </div>\n","      <div class=\"admin-panel\">\n        <h3>🔒 Cycles automatiques</h3>\n        <p class=\"admin-lead\">Les trois cycles sont autoritatifs et indépendants. Les rangs ne sont pas modifiables depuis l’interface.</p>\n        <div class=\"mini-grid\">\n          <div class=\"stat-card\"><small>🚂 Conducteur A</small><strong>R4 / R5</strong><em>1 passage par cycle</em></div>\n          <div class=\"stat-card\"><small>🚆 Conducteur B</small><strong>R3</strong><em>1 passage par cycle</em></div>\n          <div class=\"stat-card\"><small>⭐ VIP</small><strong>R3</strong><em>2 passages par cycle</em></div>\n          <div class=\"stat-card\"><small>🎁 R2 / R1</small><strong>Hors cycle</strong><em>VIP uniquement sur nomination exceptionnelle</em></div>\n        </div>\n        <div class=\"warning\">Une nomination VIP exceptionnelle R2/R1 apparaît bien au planning mais ne consomme jamais le compteur VIP R3.</div>\n      </div>\n\n      <div class=\"admin-panel\">\n        <h3>🧭 Intégrations en cours</h3>\n        <p class=\"admin-lead\">Arrivées, promotions, rétrogradations et réactivations : le quota affiché est celui du cycle réellement rejoint.</p>\n        ${allIntegrationStatusHtml()}\n      </div>\n","fixed cycles admin panel"],
      ];
      for (const [before, after, label] of rosterIntegrationUiPatches) {
        if (rewritten.includes(before)) {
          rewritten = rewritten.replace(before, after);
        } else if (!rewritten.includes(after)) {
          console.warn('WFGG_TRAIN_ROSTER_INTEGRATION_PATCH_MISS', label);
        }
      }
    }
    /* WFGG_TRAIN_DANGLING_TOKEN_FIX_V1
       Le frontend portal-only-auth ne déclare plus `token`, mais conserve
       encore un `if (token)` orphelin dans api(). Cela déclenche un
       ReferenceError avant chaque fetch et empêche syncSnapshot() de poser
       state.currentUserId. On retire uniquement ce garde devenu invalide.
    */
    rewritten = rewritten.replace(
      "        if (token)\n\n        setSyncStatus('work');",
      "        setSyncStatus('work');"
    );

    /* WFGG_TRAIN_PORTAL_PRESENCE_TOKEN_FIX_V1
       Le frontend Train historique vérifie encore `token` avant le heartbeat,
       alors que cette variable n'existe plus dans le mode session Portail.
       Le bridge fetch porte désormais l'authentification via
       X-WfGg-Portal-Token : seul l'état de visibilité reste à vérifier ici.
    */
    rewritten = rewritten.replace(
      "        if(!token || document.visibilityState!=='visible')return;",
      "        if(document.visibilityState!=='visible')return;"
    );

    /* WFGG_TRAIN_ADMIN_OWNERSHIP_V1
       Le Portail est l'unique propriétaire de l'identité alliance : joueurs,
       codes d'accès, activité des joueurs, page d'accueil et ressources
       globales. Train ne conserve que les réglages et statistiques propres au
       train (messages, horaires, rotations, planning, équité, historique).
    */
    rewritten = rewritten.replace(
      /\n\s*<button class="admin-menu-card (?:players|access|portal|help)"[\s\S]*?<\/button>/g,
      ''
    );
    rewritten = rewritten.replace(
      /\n\s*<button class="analytics-icon-card (?:overview|activity|settings|history)"[\s\S]*?<\/button>/g,
      ''
    );
    rewritten = rewritten
      .replaceAll('Statistiques & historique', 'Statistiques du train')
      .replaceAll(
        'Rotations, activité des joueurs et journal des changements',
        'Rotations, équité et historique des passages'
      );

    /* WFGG_TRAIN_STATS_SCOPE_V1
       Les statistiques globales/joueurs sont administrées dans le Portail.
       La page Statistiques du train ne conserve que des indicateurs propres au
       train, aux rotations et à son historique.
    */
    rewritten = rewritten
      .replace(
        "          <div><span>🗓️</span><small>Actions sur 7 jours</small><strong>${s.actions7||0}</strong></div>",
        "          <div><span>🚂</span><small>Trains historiques</small><strong>${adminAnalyticsCache.manualHistory?.eventCount||0}</strong></div>"
      )
      .replace(
        "          <div><span>👥</span><small>Joueurs actifs</small><strong>${s.activeMembers||0}</strong></div>",
        "          <div><span>⚖️</span><small>Écart Conducteur A</small><strong>${adminAnalyticsCache.rotation30?.spread?.officer??0}</strong></div>"
      )
      .replace(
        "          <div><span>🔄</span><small>Échanges ouverts</small><strong>${s.openExchanges||0}</strong></div>",
        "          <div><span>⭐</span><small>Écart VIP</small><strong>${adminAnalyticsCache.rotation30?.spread?.vip??0}</strong></div>"
      );

    /* WFGG_TRAIN_EXCHANGE_OWN_CANCEL_V1
       Une annonce ouverte du joueur doit toujours rester visible dans
       « Mes demandes » avec la possibilité de la retirer. Le frontend amont
       affichait le bouton uniquement dans la liste générale des annonces.
    */
    {
      const ownExchangeTail = "${x.status === 'accepted' && x.swapWithDate ? `<p>Nouvelle date : ${fmtShort(parseISO(x.swapWithDate))}</p>` : ''}</div>`).join('') : '<div class=\\\"empty\\\">Aucune demande publiée.</div>'}";
      const ownExchangeTailFixed = "${x.status === 'accepted' && x.swapWithDate ? `<p>Nouvelle date : ${fmtShort(parseISO(x.swapWithDate))}</p>` : ''}${x.status === 'open' ? `<button class=\\\"btn danger small\\\" onclick=\\\"W.cancelMarketExchange('${x.id}')\\\">Retirer mon annonce</button>` : ''}</div>`).join('') : '<div class=\\\"empty\\\">Aucune demande publiée.</div>'}";
      rewritten = rewritten.replace(ownExchangeTail, ownExchangeTailFixed);
    }

    /* WFGG_TRAIN_EXCHANGE_OWN_CANCEL_V2
       Patch ciblé sur le fragment exact du rendu « Mes demandes ».
       Le V1 incluait trop de contexte et ne correspondait pas au JS upstream.
    */
    {
      const ownOpenTail = "${x.status === 'accepted' && x.swapWithDate ? `<p>Nouvelle date : ${fmtShort(parseISO(x.swapWithDate))}</p>` : ''}</div>";
      const ownOpenTailFixed = "${x.status === 'accepted' && x.swapWithDate ? `<p>Nouvelle date : ${fmtShort(parseISO(x.swapWithDate))}</p>` : ''}${x.status === 'open' ? `<button class=\"btn danger small\" onclick=\"W.cancelMarketExchange('${x.id}')\">Retirer mon annonce</button>` : ''}</div>";
      rewritten = rewritten.replace(ownOpenTail, ownOpenTailFixed);
    }

    /* WFGG_TRAIN_INIT_DOM_GUARD_V1
       Le HTML portal-only-auth ne contient plus loginBtn ni loginPortalBack,
       alors que l'ancien init() les déréférence sans contrôle. Le premier
       getElementById(...).onclick lançait donc une exception avant le câblage
       des .nav-btn. On rend uniquement ces deux liaisons optionnelles.
    */
    rewritten = rewritten.replace(
      "        document.getElementById('loginBtn').onclick = login;",
      "        { const el = document.getElementById('loginBtn'); if (el) el.onclick = login; }"
    );
    rewritten = rewritten.replace(
      "        document.getElementById('loginPortalBack').onclick = showPortal;",
      "        { const el = document.getElementById('loginPortalBack'); if (el) el.onclick = showPortal; }"
    );

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
      "    if (document.readyState === 'loading') {\n" +
      "        document.addEventListener('DOMContentLoaded', init, { once: true });\n" +
      "    } else {\n" +
      "        init();\n" +
      "    }"
    );

    /* WFGG_TRAIN_PROXY_NO_SERVICE_WORKER_V1
       Sous le Portail unifié, le proxy est la source de vérité pour app.js.
       Ne pas réenregistrer le service worker historique qui pourrait remettre
       une version antérieure du frontend dans le chemin d'exécution.
    */
    rewritten = rewritten.replace(
      "        if ('serviceWorker' in navigator)\n            navigator.serviceWorker.register('service-worker.js?v=44').catch(() => { });",
      "        /* WFGG_TRAIN_PROXY_NO_SERVICE_WORKER_V1 */"
    );

    const jsHeaders = new Headers(headers);
    jsHeaders.delete('Content-Length');
    jsHeaders.delete('Content-Encoding');
    jsHeaders.delete('ETag');
    jsHeaders.set('Cache-Control', 'no-store');
    jsHeaders.set('Pragma', 'no-cache');
    jsHeaders.set('Expires', '0');
    jsHeaders.set('X-WfGg-Train-Api-Bridge', 'v3');
    jsHeaders.set('X-WfGg-Train-Cache-Bridge', 'v1');
    jsHeaders.set('X-WfGg-Train-Roster-Integration-Bridge', 'v1');

    return new Response(rewritten, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: jsHeaders
    });
  }

  if (!contentType.toLowerCase().includes('text/html')) {
    return response;
  }

  /*
    Les HTML des modules sont pilotés par le Worker : éviter qu'un vieux
    document HTML masque la nouvelle synchronisation pendant les tests.
  */
  headers.set('Cache-Control', 'no-store');

  let rewriter = new HTMLRewriter()
    .on('[href], [src], [action], [poster]',
      new RootAttributeRewriter(route.prefix, route.origin))
    .on('a[href]', new PortalLegacyLinkRewriter())
    .on('head', {
      element(element) {
        let html = languageBridgeScript(options.routeName || route.prefix.slice(1));
        /* WFGG_TRAIN_PUSH_MANIFEST_HEAD_V1 */
        if (options.routeName === 'train') {
          html = '<link rel="manifest" href="/train/manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="theme-color" content="#00182b">' + html;
        }
        if (options.baseHref) {
          html = `<base href="${options.baseHref}">` + html;
        }
        element.prepend(html, { html: true });
      }
    });

  return rewriter.transform(response);
}

async function routeGuides(request) {
  const url = new URL(request.url);
  const route = UPSTREAMS.guides;

  if (url.pathname === '/guides') {
    return redirectSlash(request, '/guides/');
  }

  const lang = explicitLang(url.searchParams.get('lang'));

  /* Accès direct à un hub de guide avec langue connue : pas de page FR intermédiaire. */
  if (lang && (url.pathname === '/guides/season6' || url.pathname === '/guides/season6/')) {
    const target = new URL(request.url);
    target.pathname = `/guides/season6/${lang}/cover.html`;
    return Response.redirect(target.toString(), 302);
  }

  if (lang && (url.pathname === '/guides/interseason' || url.pathname === '/guides/interseason/')) {
    const target = new URL(request.url);
    target.pathname = `/guides/interseason/${lang}/index.html`;
    return Response.redirect(target.toString(), 302);
  }

  const suffix = url.pathname.slice(route.prefix.length) || '/';
  return proxyRoute(request, route, suffix, { routeName: 'guides' });
}

async function routeTrain(request, env) {
  const url = new URL(request.url);
  const route = UPSTREAMS.train;

  if (url.pathname === '/train') {
    return redirectSlash(request, '/train/');
  }

  const suffix = url.pathname.slice(route.prefix.length) || '/';

  /* WFGG_TRAIN_PUSH_STATIC_V1
     Le Service Worker Push doit être servi par wfgg.pages.dev sous /train/
     pour posséder exactement le même origin et le bon scope sur Android/iOS. */
  if (suffix === '/wfgg-push-sw.js' || suffix === '/manifest.webmanifest') {
    const assetUrl = new URL(request.url);
    assetUrl.pathname = '/train-native' + suffix;
    assetUrl.search = '';
    const assetResponse = await env.ASSETS.fetch(new Request(assetUrl.toString(), {method:'GET',headers:request.headers}));
    if (assetResponse.ok) {
      const headers = new Headers(assetResponse.headers);
      headers.set('Cache-Control', suffix.endsWith('.js') ? 'no-store' : 'public, max-age=300');
      if (suffix.endsWith('.js')) headers.set('Content-Type','application/javascript; charset=utf-8');
      if (suffix.endsWith('.webmanifest')) headers.set('Content-Type','application/manifest+json; charset=utf-8');
      return new Response(assetResponse.body,{status:assetResponse.status,statusText:assetResponse.statusText,headers});
    }
  }

  /* WFGG_TRAIN_SENTINEL_STATIC_V4
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

  /* WFGG_TRAIN_NATIVE_APP_V15_SHADOW
     Première étape de consolidation : sur la branche native v15, app.js est
     servi depuis une capture vérifiée du bridge v14 réellement déployé.
     Le fallback proxy reste actif si l'asset est absent, afin de ne jamais
     casser Train pendant la migration progressive.
  */
  if (suffix === '/app.js') {
    const assetUrl = new URL(request.url);
    assetUrl.pathname = '/train-native/app.v15.js';
    assetUrl.search = '';

    const assetRequest = new Request(assetUrl.toString(), {
      method: 'GET',
      headers: request.headers
    });
    const assetResponse = await env.ASSETS.fetch(assetRequest);

    if (assetResponse.ok) {
      const headers = new Headers(assetResponse.headers);
      headers.set('Cache-Control', 'no-store');
      headers.set('X-WfGg-Train-Frontend', 'native-v15-shadow');
      return new Response(assetResponse.body, {
        status: assetResponse.status,
        statusText: assetResponse.statusText,
        headers
      });
    }
  }

  return proxyRoute(request, route, suffix, { routeName: 'train' });
}

/* WFGG_SENTINEL_EDGE_ACCESS_V7
   Sentinel reste strictement en lecture seule. Son accès est réservé aux rôles
   système OWNER et SUPERVISOR, indépendamment du rang d'alliance R1..R5. */
function sentinelEdgeJson(data,status=200){
  return new Response(JSON.stringify(data),{
    status,
    headers:{
      'Content-Type':'application/json; charset=utf-8',
      'Cache-Control':'no-store',
      'X-WfGg-Route':'portal-sentinel-edge'
    }
  });
}

function sentinelEdgeCheck(id,area,level,title,expected,observed,detail='',probableCause=''){
  return {id,area,level,title,expected,observed,detail,probableCause};
}

async function sentinelEdgeFetchJson(request,origin,path,extraHeaders={}){
  const target=new URL(path,origin);
  const headers=new Headers(request.headers);
  headers.delete('Origin');
  headers.delete('Referer');
  for(const [key,value] of Object.entries(extraHeaders)){
    if(value==null)headers.delete(key);else headers.set(key,String(value));
  }
  const started=Date.now();
  const response=await fetch(new Request(target.toString(),{
    method:'GET',headers,redirect:'manual'
  }));
  let raw='';
  try{raw=await response.clone().text();}catch(_){}
  let data=null;
  try{data=raw?JSON.parse(raw):null;}catch(_){}
  const responseHeaders={};
  for(const name of ['content-type','cf-ray','server','x-wfgg-route','x-wfgg-portal-bridge','x-wfgg-presence-entry','x-wfgg-rotation-guard']){
    const value=response.headers.get(name);
    if(value)responseHeaders[name]=value;
  }
  return {response,data,raw:raw.slice(0,1600),durationMs:Date.now()-started,responseHeaders,target:target.toString()};
}

/* WFGG_SENTINEL_SUPERVISOR_FALLBACK_V8
   Le rôle SUPERVISOR est d'abord lu depuis le rôle système persistant. Tant que
   le jeton de déploiement ne permet pas d'écrire D1, les deux comptes demandés
   sont également reconnus à l'edge à partir de l'identité Portail authentifiée.
   Ce fallback n'accorde aucun droit métier R4/R5 supplémentaire. */
const SENTINEL_SUPERVISOR_NAMES_V8=new Set([
  'flawene','flawen','elo','εlο ツ','εlα ツ','εlo ツ'
]);

function sentinelNormalizeIdentity(value){
  return String(value||'').normalize('NFKC').trim().toLowerCase();
}

function sentinelEffectiveRole(data){
  const persisted=String(data?.system?.role||'').toUpperCase();
  if(persisted==='OWNER'||persisted==='SUPERVISOR')return persisted;
  const rank=String(data?.membership?.rank||'').toUpperCase();
  if(!['R4','R5'].includes(rank))return '';
  const names=[data?.user?.display_name,data?.user?.player_name]
    .map(sentinelNormalizeIdentity)
    .filter(Boolean);
  return names.some(name=>SENTINEL_SUPERVISOR_NAMES_V8.has(name))?'SUPERVISOR':'';
}

function sentinelDecorateMe(data){
  const role=sentinelEffectiveRole(data);
  if(!role)return data;
  return {
    ...data,
    system:{...(data?.system||{}),role},
    permissions:{...(data?.permissions||{}),can_use_sentinel:true}
  };
}

async function sentinelPortalMeAtEdge(request){
  let call;
  try{
    call=await sentinelEdgeFetchJson(request,UPSTREAMS.portalApi.origin,'/api/me');
  }catch(error){
    return sentinelEdgeJson({ok:false,error:'PORTAL_API_UNAVAILABLE',detail:String(error?.message||error)},503);
  }
  if(!call.response.ok){
    return sentinelEdgeJson(call.data||{ok:false,error:'HTTP_'+call.response.status},call.response.status);
  }
  return sentinelEdgeJson(sentinelDecorateMe(call.data),200);
}

/* WFGG_SENTINEL_AUTO_DIAGNOSTIC_V9
   Sentinel reste strictement en lecture seule. Quand une anomalie est détectée,
   une seconde passe suit automatiquement la chaîne Portail -> contexte Train ->
   Worker Train et classe la première rupture observable. Aucun POST/PUT/DELETE
   n'est exécuté par ce diagnostic. */
function sentinelSanitizeSnippet(value){
  return String(value||'')
    .replace(/Bearer\s+[A-Za-z0-9._~+\/-]+/gi,'Bearer [redacted]')
    .replace(/(token|session|authorization)(["']?\s*[:=]\s*["'])[^"']+/gi,'$1$2[redacted]')
    .replace(/\s+/g,' ')
    .trim()
    .slice(0,700);
}

function sentinelResponseMeta(call){
  if(!call?.response)return 'aucune réponse HTTP';
  const h=call.responseHeaders||{};
  const parts=[
    'HTTP '+call.response.status,
    call.durationMs!=null?call.durationMs+' ms':'',
    h['content-type']?'content-type='+h['content-type']:'',
    h['cf-ray']?'cf-ray='+h['cf-ray']:'',
    h['server']?'server='+h['server']:'',
    h['x-wfgg-route']?'route='+h['x-wfgg-route']:''
  ].filter(Boolean);
  return parts.join(' · ');
}

function sentinelClassifyCloudflareFailure(call){
  const raw=String(call?.raw||'');
  if(/1102|cpu time|exceeded.*cpu|worker exceeded/i.test(raw)){
    return {component:'Cloudflare Worker Train',stage:'limite CPU',codeArea:'exécution de /api/snapshot avant réponse JSON',cause:'Le Worker dépasse sa limite CPU pendant la génération du snapshot.'};
  }
  if(/1101|worker threw exception|uncaught exception|internal error/i.test(raw)){
    return {component:'Cloudflare Worker Train',stage:'exception non interceptée',codeArea:'worker.js :: /api/snapshot ou dépendance appelée',cause:'Une exception remonte hors du code applicatif avant qu’une réponse JSON structurée soit produite.'};
  }
  if(/1015|rate limit|too many requests/i.test(raw)){
    return {component:'Cloudflare',stage:'limitation de débit',codeArea:'edge avant worker.js',cause:'Cloudflare limite temporairement les requêtes avant ou autour du Worker Train.'};
  }
  return null;
}

async function sentinelRunDeepDiagnostics(request,token,meCall,snapCall,checks){
  const anomalies=checks.filter(item=>item.level==='error'||item.level==='warning');
  if(!anomalies.length)return null;

  let contextCall=null;
  let contextError='';
  try{
    contextCall=await sentinelEdgeFetchJson(
      request,
      UPSTREAMS.portalApi.origin,
      '/api/train/context',
      {'Authorization':'Bearer '+token,'X-WfGg-Portal-Token':null,'Accept':'application/json'}
    );
  }catch(error){
    contextError=String(error?.message||error);
  }

  const contextOk=!!contextCall?.response?.ok;
  checks.push(sentinelEdgeCheck(
    'sentinel-deep-portal-context','Diagnostic automatique',contextOk?'ok':'error',
    'Contexte Portail → Train','/api/train/context HTTP 200',
    contextCall?'HTTP '+contextCall.response.status:'Erreur réseau',
    contextCall?sentinelResponseMeta(contextCall):contextError,
    contextOk?'':'La résolution d’identité Portail destinée à Train échoue avant même le snapshot.'
  ));

  let trainSourceCall=null;
  try{
    trainSourceCall=await sentinelEdgeFetchJson(
      request,
      UPSTREAMS.trainApi.origin,
      '/api/sentinel/source-map',
      {'Authorization':null,'X-WfGg-Portal-Token':token,'Accept':'application/json'}
    );
  }catch(_){}
  const trainSourceOk=!!trainSourceCall?.response?.ok&&trainSourceCall?.data?.version==='sentinel-source-map-v10';
  checks.push(sentinelEdgeCheck(
    'sentinel-source-index','Diagnostic automatique',trainSourceOk?'ok':'warning',
    'Index des sources Train','source map Sentinel V10 disponible',
    trainSourceCall?'HTTP '+trainSourceCall.response.status:'indisponible',
    trainSourceOk?('commit '+String(trainSourceCall.data?.sourceCommit||'').slice(0,12)):'',
    trainSourceOk?'':'Sentinel peut diagnostiquer la couche, mais pas encore garantir le numéro de ligne exact.'
  ));

  if(snapCall?.response){
    const snippet=sentinelSanitizeSnippet(snapCall.raw||snapCall.data?.error||'');
    checks.push(sentinelEdgeCheck(
      'sentinel-deep-snapshot-envelope','Diagnostic automatique','info',
      'Enveloppe HTTP du snapshot','Réponse JSON Train exploitable',
      sentinelResponseMeta(snapCall),
      snippet?('Corps: '+snippet):'Corps vide ou non exploitable.',
      ''
    ));
  }

  let root={
    component:'Sentinel',stage:'anomalie à classifier',codeArea:'contrôle '+String(anomalies[0]?.id||'inconnu'),
    cause:String(anomalies[0]?.probableCause||'Une anomalie a été détectée mais la couche exacte reste à confirmer.')
  };

  if(!contextOk){
    root={
      component:'wfgg-api',stage:'résolution identité Portail → Train',codeArea:'API Portail :: /api/train/context',
      cause:'Le contexte Train ne répond pas correctement. Le Worker Train ne peut donc pas recevoir une identité Portail cohérente.'
    };
  }else if(!snapCall){
    root={
      component:'liaison edge → Worker Train',stage:'appel réseau /api/snapshot',codeArea:'frontend/_worker.js :: runSentinelAtPortalEdge',
      cause:'Le contexte Portail est valide mais aucun retour HTTP n’est obtenu du Worker Train.'
    };
  }else if(!snapCall.response.ok){
    const cf=sentinelClassifyCloudflareFailure(snapCall);
    if(cf){
      root=cf;
    }else{
      const isJson=String(snapCall.responseHeaders?.['content-type']||'').toLowerCase().includes('json');
      root=isJson?{
        component:'wfgg-train',stage:'traitement applicatif du snapshot',codeArea:'worker.js :: /api/snapshot (requireAuth → getState/listUsers → generateSchedule)',
        cause:'Le contexte Portail est HTTP 200 mais /api/snapshot renvoie une erreur applicative. Le corps et le code HTTP ci-dessus donnent le premier indice exploitable.'
      }:{
        component:'Cloudflare / Worker Train',stage:'avant réponse JSON applicative',codeArea:'edge autour de worker.js :: /api/snapshot',
        cause:'Le contexte Portail est HTTP 200 mais le snapshot échoue sans enveloppe JSON normale. La rupture est donc située après l’identité Portail et avant le retour applicatif du snapshot.'
      };
    }
  }else if(checks.some(item=>item.id==='train-access-roster'&&item.level==='error')){
    root={
      component:'données Train',stage:'cohérence identité ↔ roster',codeArea:'worker.js :: /api/snapshot → me/roster',
      cause:'Le snapshot répond, mais l’utilisateur authentifié n’est pas présent dans le roster renvoyé.'
    };
  }else if(checks.some(item=>item.id==='train-schedule'&&item.level==='warning')){
    root={
      component:'moteur planning Train',stage:'génération du planning',codeArea:'worker.js :: generateSchedule / état de rotation',
      cause:'Le snapshot répond mais aucun planning autoritatif n’est produit dans la fenêtre courante.'
    };
  }else if(checks.some(item=>['no-double-role','schedule-roster-refs','driver-ranks'].includes(item.id)&&item.level==='error')){
    root={
      component:'règles métier Train',stage:'validation du planning produit',codeArea:'planning autoritatif / roster / règles d’éligibilité',
      cause:'Le transport et l’authentification fonctionnent; l’anomalie se situe dans la cohérence des données ou des règles métier du planning.'
    };
  }

  const trainSourceMap=trainSourceCall?.data||null;
  const runtimeDiagnostic=snapCall?.data?.sentinelDiagnostic||null;
  if(runtimeDiagnostic?.stage){
    root={
      component:'wfgg-train',
      stage:'étape interne '+runtimeDiagnostic.stage,
      codeArea:'worker.js :: '+runtimeDiagnostic.stage,
      cause:'Le Worker Train a identifié lui-même la première étape ayant levé l’erreur.',
      source:runtimeDiagnostic.source||trainSourceMap?.stages?.[runtimeDiagnostic.stage]||null,
      stack:sentinelSanitizeSnippet(runtimeDiagnostic.stack||'')
    };
  }else if(!root.source&&trainSourceMap?.stages){
    if(root.component==='moteur planning Train')root.source=trainSourceMap.stages.generateSchedule||null;
    else if(root.component==='données Train')root.source=trainSourceMap.stages.listUsers||null;
  }

  const evidence=[
    'Portail /api/me: HTTP '+String(meCall?.response?.status||'?'),
    'Contexte Train: '+(contextCall?'HTTP '+contextCall.response.status:'sans réponse'),
    'Snapshot Train: '+(snapCall?'HTTP '+snapCall.response.status:'sans réponse')
  ].join(' · ');
  const source=root.source||null;
  const sourceLabel=source
    ? [source.repository,source.file+(source.line?':'+source.line:''),source.function?'fonction '+source.function:'',source.sourceCommit?'commit '+String(source.sourceCommit).slice(0,12):''].filter(Boolean).join(' · ')
    : '';
  const rootCheck=sentinelEdgeCheck(
    'sentinel-root-cause','Diagnostic automatique','info',
    'Cause racine Sentinel','Premier composant fautif isolé sans modification',
    root.component+' · '+root.stage,
    'Zone code: '+root.codeArea+' · '+evidence+(sourceLabel?' · Source exacte: '+sourceLabel:''),
    root.cause
  );
  if(source)rootCheck.source=source;
  if(root.stack)rootCheck.stack=root.stack;
  checks.push(rootCheck);

  return {rootCause:root,evidence,source,readonly:true,anomalyIds:anomalies.map(item=>item.id)};
}

async function runSentinelAtPortalEdge(request){
  const auth=request.headers.get('Authorization')||'';
  const token=auth.startsWith('Bearer ')?auth.slice(7).trim():'';
  if(!token)return sentinelEdgeJson({ok:false,error:'UNAUTHORIZED'},401);

  let meCall;
  try{
    meCall=await sentinelEdgeFetchJson(request,UPSTREAMS.portalApi.origin,'/api/me');
  }catch(error){
    return sentinelEdgeJson({ok:false,error:'PORTAL_API_UNAVAILABLE',detail:String(error?.message||error)},503);
  }
  if(!meCall.response.ok){
    return sentinelEdgeJson({ok:false,error:meCall.data?.error||('HTTP_'+meCall.response.status)},meCall.response.status);
  }
  const sentinelRole=sentinelEffectiveRole(meCall.data);
  if(!['OWNER','SUPERVISOR'].includes(sentinelRole)){
    return sentinelEdgeJson({ok:false,error:'SENTINEL_ACCESS_FORBIDDEN'},403);
  }

  const checks=[];
  checks.push(sentinelEdgeCheck(
    'sentinel-access','Sécurité','ok','Accès Sentinel','Rôle système OWNER ou SUPERVISOR',sentinelRole+' validé côté serveur',
    'Le rang d’alliance reste indépendant de ce droit système.',''
  ));
  checks.push(sentinelEdgeCheck(
    'portal-api','Portail','ok','API Portail','/api/me HTTP 200','HTTP 200','Session Portail valide.',''
  ));

  let snapCall=null;
  try{
    snapCall=await sentinelEdgeFetchJson(
      request,
      UPSTREAMS.trainApi.origin,
      '/api/snapshot',
      {'Authorization':null,'X-WfGg-Portal-Token':token,'X-WfGg-Sentinel-Diagnostic':'v10','Accept':'application/json'}
    );
  }catch(error){
    checks.push(sentinelEdgeCheck(
      'train-snapshot','Train','error','Snapshot Train','HTTP 200','Erreur réseau',String(error?.message||error),
      'Le Worker Train ou la liaison Portail → Train est indisponible.'
    ));
  }

  if(snapCall){
    const snap=snapCall.data||{};
    const roster=Array.isArray(snap.roster)?snap.roster:[];
    const schedule=Array.isArray(snap.schedule)?snap.schedule:[];
    const meId=String(snap.me?.id||meCall.data?.user?.id||'');
    const rosterHasMe=!!(meId&&roster.some(row=>String(row?.id||'')===meId));

    checks.push(sentinelEdgeCheck(
      'train-snapshot','Train',snapCall.response.ok?'ok':'error','Snapshot Train','HTTP 200','HTTP '+snapCall.response.status,
      snapCall.response.ok?(roster.length+' joueur(s) · '+schedule.length+' affectation(s)'):(snap?.error||''),
      snapCall.response.ok?'':'La session Portail n’est pas acceptée par le Worker Train.'
    ));
    checks.push(sentinelEdgeCheck(
      'train-access-roster','Session & données',rosterHasMe?'ok':'error','Utilisateur courant dans le roster','Utilisateur autorisé présent dans le roster',rosterHasMe?'Présent':'Absent','',
      rosterHasMe?'':'Le snapshot et l’identité Portail ne sont pas cohérents.'
    ));
    checks.push(sentinelEdgeCheck(
      'train-schedule','Planning',schedule.length?'ok':'warning','Planning autoritatif disponible','schedule non vide',schedule.length+' affectation(s)','',
      schedule.length?'':'Le serveur n’a retourné aucune affectation dans la fenêtre courante.'
    ));

    const byId=new Map(roster.map(row=>[String(row?.id||''),row]));
    const conflicts=[];
    const invalidDrivers=[];
    const orphan=[];
    for(const row of schedule.slice(0,240)){
      const d=String(row?.driverId||'');
      const v=String(row?.vipId||'');
      const date=String(row?.date||'?');
      if(d&&v&&d===v)conflicts.push(date);
      if(d){
        const p=byId.get(d);
        if(!p)orphan.push(date+':driver:'+d);
        else if(!['R3','R4','R5'].includes(String(p.rank||'')))invalidDrivers.push(date+':'+(p.pseudo||d)+':'+(p.rank||'?'));
      }
      if(v&&!byId.has(v))orphan.push(date+':vip:'+v);
    }
    checks.push(sentinelEdgeCheck(
      'no-double-role','Règles métier',conflicts.length?'error':'ok','Pas de double rôle Conducteur/VIP','0 conflit',conflicts.length?conflicts.slice(0,8).join(', '):'0 conflit','',
      conflicts.length?'Une affectation place le même joueur dans les deux rôles le même jour.':''
    ));
    checks.push(sentinelEdgeCheck(
      'schedule-roster-refs','Planning',orphan.length?'error':'ok','Références planning valides','0 joueur orphelin',orphan.length?orphan.slice(0,8).join(' · '):'Conforme','',
      orphan.length?'Un ancien planning référence un joueur absent du roster.':''
    ));
    checks.push(sentinelEdgeCheck(
      'driver-ranks','Règles métier',invalidDrivers.length?'error':'ok','Éligibilité Conducteur','R3/R4/R5 uniquement',invalidDrivers.length?invalidDrivers.slice(0,8).join(' · '):'Conforme','',
      invalidDrivers.length?'Une affectation Conducteur est hors des pools autorisés.':''
    ));
  }

  /* WFGG_SENTINEL_FUNCTIONAL_COVERAGE_V11
     Les contrôles ci-dessous sont tous GET/observer-only. Ils étendent Sentinel
     aux fonctions Train et au pipeline Push sans publier, accepter, supprimer,
     modifier ni envoyer quoi que ce soit. */
  let featureAuditCall=null;
  try{
    featureAuditCall=await sentinelEdgeFetchJson(
      request,
      UPSTREAMS.trainApi.origin,
      '/api/sentinel/feature-audit',
      {'Authorization':null,'X-WfGg-Portal-Token':token,'X-WfGg-Sentinel-Diagnostic':'v11','Accept':'application/json'}
    );
  }catch(error){
    checks.push(sentinelEdgeCheck(
      'sentinel-feature-audit-link','Sentinel · couverture','error',
      'Audit fonctionnel Train','GET V11 disponible','Erreur réseau',String(error?.message||error),
      'Sentinel ne peut pas vérifier les familles fonctionnelles du Train.'
    ));
  }
  if(featureAuditCall){
    if(featureAuditCall.response.ok&&featureAuditCall.data?.readonly===true&&Array.isArray(featureAuditCall.data?.checks)){
      checks.push(...featureAuditCall.data.checks);
    }else{
      checks.push(sentinelEdgeCheck(
        'sentinel-feature-audit-link','Sentinel · couverture','error',
        'Audit fonctionnel Train','HTTP 200 · readonly=true',
        'HTTP '+featureAuditCall.response.status,
        sentinelSanitizeSnippet(featureAuditCall.raw||featureAuditCall.data?.error||''),
        'La couche V11 de couverture fonctionnelle n’est pas exploitable.'
      ));
    }
  }

  let selfTestCall=null;
  try{
    selfTestCall=await sentinelEdgeFetchJson(
      request,
      UPSTREAMS.trainApi.origin,
      '/api/sentinel/self-test',
      {'Authorization':null,'X-WfGg-Portal-Token':token,'X-WfGg-Sentinel-Diagnostic':'v11','Accept':'application/json'}
    );
  }catch(_){}
  const selfOk=!!selfTestCall?.response?.ok&&selfTestCall?.data?.readonly===true&&selfTestCall?.data?.synthetic===true&&selfTestCall?.data?.expectedFailureCaptured===true&&selfTestCall?.data?.stage==='generateSchedule'&&!!selfTestCall?.data?.source;
  const selfCheck=sentinelEdgeCheck(
    'sentinel-self-test-v11','Sentinel · auto-recette',selfOk?'ok':'error',
    'Panne synthétique contrôlée','Erreur artificielle capturée et localisée sans écriture',
    selfOk?('capturée · '+String(selfTestCall.data.stage)):(selfTestCall?'HTTP '+selfTestCall.response.status:'sans réponse'),
    selfOk?'Sentinel a exécuté generateSchedule sur un clone puis a capturé l’exception artificielle.':'La chaîne de diagnostic source n’a pas validé son propre test.',
    selfOk?'':'Sentinel ne peut pas garantir actuellement la remontée fichier/fonction/ligne.'
  );
  if(selfTestCall?.data?.source)selfCheck.source=selfTestCall.data.source;
  if(selfTestCall?.data?.stack)selfCheck.stack=sentinelSanitizeSnippet(selfTestCall.data.stack);
  checks.push(selfCheck);

  const diagnosis=await sentinelRunDeepDiagnostics(request,token,meCall,snapCall,checks);

  /* WFGG_SENTINEL_PRESCRIPTIVE_EDGE_V12
     Une anomalie déclenche une demande GET vers le simulateur Train V12.
     Le plan retourné est uniquement descriptif : readonly=true, applied=false. */
  let repairPlan=null;
  const repairIssues=[...new Set(checks
    .filter(item=>item&&(item.level==='error'||item.level==='warning'))
    .map(item=>String(item.id||'').trim()).filter(Boolean))];
  if(repairIssues.length){
    const params=new URLSearchParams();
    for(const id of repairIssues)params.append('issue',id);
    const signal=[
      diagnosis?.rootCause?.observed,diagnosis?.rootCause?.detail,diagnosis?.rootCause?.probableCause,
      ...checks.filter(item=>item?.level==='error').slice(0,4).map(item=>item.detail||item.observed||item.probableCause||'')
    ].filter(Boolean).join(' | ').slice(0,220);
    if(signal)params.set('signal',signal);
    try{
      const repairCall=await sentinelEdgeFetchJson(
        request,UPSTREAMS.trainApi.origin,'/api/sentinel/repair-plan?'+params.toString(),
        {'Authorization':null,'X-WfGg-Portal-Token':token,'X-WfGg-Sentinel-Diagnostic':'v12','Accept':'application/json'}
      );
      if(repairCall.response.ok&&repairCall.data?.readonly===true&&repairCall.data?.applied===false){
        repairPlan=repairCall.data;
      }else{
        repairPlan={ok:false,version:'sentinel-repair-link-v12',readonly:true,applied:false,candidates:[],error:'HTTP_'+repairCall.response.status};
        checks.push(sentinelEdgeCheck(
          'sentinel-repair-plan-link','Sentinel · correctifs simulés','warning','Simulation des correctifs',
          'Plan V12 readonly disponible','HTTP '+repairCall.response.status,
          sentinelSanitizeSnippet(repairCall.raw||repairCall.data?.error||''),'Le diagnostic reste valide mais la simulation des correctifs est indisponible.'
        ));
      }
    }catch(error){
      repairPlan={ok:false,version:'sentinel-repair-link-v12',readonly:true,applied:false,candidates:[],error:String(error?.message||error)};
      checks.push(sentinelEdgeCheck(
        'sentinel-repair-plan-link','Sentinel · correctifs simulés','warning','Simulation des correctifs',
        'Plan V12 readonly disponible','Erreur réseau',String(error?.message||error),
        'Le diagnostic reste valide mais la simulation des correctifs est indisponible.'
      ));
    }
  }

  const counts={ok:0,info:0,warning:0,error:0};
  for(const item of checks)counts[item.level]=(counts[item.level]||0)+1;
  const status=counts.error?'error':counts.warning?'warning':counts.info?'info':'ok';
  return sentinelEdgeJson({
    ok:!counts.error,
    version:'sentinel-edge-v10',
    mode:'observer',
    readonly:true,
    autoDiagnostic:true,
    finishedAt:new Date().toISOString(),
    summary:{status,counts,total:checks.length},
    diagnosis,
    repairPlan,
    checks
  });
}

async function routeSimulator(request) {
  const url = new URL(request.url);

  if (url.pathname === '/simulateur') {
    return redirectSlash(request, '/simulateur/');
  }

  if (url.pathname !== '/simulateur/') {
    return new Response('Not found', { status: 404 });
  }

  const lang = safeLang(url.searchParams.get('lang'));
  const filename = SIMULATOR_FILES[lang];
  const upstreamPath = `/interseason/${lang}/${filename}`;

  return proxyRoute(
    request,
    UPSTREAMS.guides,
    upstreamPath,
    {
      routeName: 'simulateur',
      baseHref: `/guides/interseason/${lang}/`
    }
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    try {
      /* WFGG_GUEST_SERVER_ENFORCEMENT_V2 */
      if (isGuestRequest(request)) {
        if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
          return new Response('Guest access is read-only', {
            status: 403,
            headers: {
              'Content-Type': 'text/plain; charset=utf-8',
              'Cache-Control': 'no-store'
            }
          });
        }

        if (
          url.pathname === '/train' ||
          url.pathname.startsWith('/train/') ||
          url.pathname === '/simulateur' ||
          url.pathname.startsWith('/simulateur/')
        ) {
          return guestRedirect(request);
        }
      }

      /* WFGG_SENTINEL_PORTAL_PROXY_V5
         Routes Portail strictement dédiées à Sentinel. Elles gardent l'authentification
         Bearer du Portail et évitent que le routage /api du contexte Train les envoie
         par erreur au Worker Train. Les contrôles OWNER restent côté wfgg-api. */
      if (url.pathname === '/portal-api/me') {
        return await sentinelPortalMeAtEdge(request);
      }
      if (url.pathname === '/portal-api/sentinel/run') {
        return await runSentinelAtPortalEdge(request);
      }

      /* WFGG_TRAIN_API_PROXY
         Les API historiques du frontend Train utilisent /api/*.
         Le Portail les transmet au backend Train.
      */
      /* WFGG_API_CONTEXT_SPLIT_V1
         Les API du Portail restent sur wfgg-api.
         Les appels provenant de /train/ utilisent le backend Train.
      */
      if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
        const referer = request.headers.get('Referer') || '';
        const hasPortalTrainToken =
          request.headers.has('X-WfGg-Portal-Token');

        let fromTrainPage = false;

        try {
          const refUrl = new URL(referer);

          fromTrainPage =
            refUrl.origin === url.origin &&
            (
              refUrl.pathname === '/train' ||
              refUrl.pathname.startsWith('/train/')
            );
        } catch {}

        const apiRoute =
          (fromTrainPage || hasPortalTrainToken)
            ? UPSTREAMS.trainApi
            : UPSTREAMS.portalApi;

        return await proxyRoute(
          request,
          apiRoute,
          url.pathname,
          {
            routeName:
              apiRoute === UPSTREAMS.trainApi
                ? 'train-api'
                : 'portal-api'
          }
        );
      }

      if (url.pathname === '/guides' || url.pathname.startsWith('/guides/')) {
        return await routeGuides(request);
      }

      if (url.pathname === '/train' || url.pathname.startsWith('/train/')) {
        return await routeTrain(request, env);
      }

      if (url.pathname === '/simulateur' || url.pathname.startsWith('/simulateur/')) {
        return await routeSimulator(request);
      }

      return env.ASSETS.fetch(request);
    } catch (error) {
      console.error('WFGG_UNIFIED_ROUTE_ERROR', url.pathname, error);
      return new Response('WfGg route temporarily unavailable', {
        status: 502,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store'
        }
      });
    }
  }
};
