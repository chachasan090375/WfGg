const UPSTREAMS = {
  guides: {
    prefix: '/guides',
    origin: 'https://wfgg-guides.pages.dev'
  },
  train: {
    prefix: '/train',
    origin: 'https://wfgg-train-app.pages.dev'
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

function upstreamRequest(request, targetUrl) {
  return new Request(targetUrl.toString(), {
    method: request.method,
    headers: request.headers,
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

      if (value.startsWith('/') && !value.startsWith('//')) {
        element.setAttribute(attr, `${this.prefix}${value}`);
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

  /* WFGG_PORTAL_TRAIN_FETCH_BRIDGE
     Ajoute la session Portail en parallèle.
     L'ancien Authorization Train n'est jamais remplacé.
  */
  if(ROUTE==='train'){
    const WFGG_NATIVE_FETCH=window.fetch.bind(window);

    window.fetch=function(input,init){
      const options=init?{...init}:{};

      try{
        const raw=
          typeof input==='string'||input instanceof URL
            ? String(input)
            : input?.url;

        const target=new URL(raw||'',location.href);

        if(
          target.origin===location.origin &&
          target.pathname.startsWith('/api/')
        ){
          const portalToken=localStorage.getItem(PORTAL_TOKEN);

          if(portalToken){
            const headers=new Headers(
              options.headers ||
              (input instanceof Request ? input.headers : undefined)
            );

            headers.set('X-WfGg-Portal-Token',portalToken);
            options.headers=headers;

            if(input instanceof Request){
              return WFGG_NATIVE_FETCH(
                new Request(input,options)
              );
            }
          }
        }
      }catch(e){}

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

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',function(){
      localizeGuideLanding();
      forceTrainLanguage();
    },{once:true});
  }else{
    localizeGuideLanding();
    forceTrainLanguage();
  }
})();
</script>`;
}

async function proxyRoute(request, route, upstreamPath, options = {}) {
  const incoming = new URL(request.url);
  const target = new URL(route.origin);

  target.pathname = upstreamPath;
  target.search = incoming.search;

  const upstream = await fetch(upstreamRequest(request, target));
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

async function routeTrain(request) {
  const url = new URL(request.url);
  const route = UPSTREAMS.train;

  if (url.pathname === '/train') {
    return redirectSlash(request, '/train/');
  }

  const suffix = url.pathname.slice(route.prefix.length) || '/';
  return proxyRoute(request, route, suffix, { routeName: 'train' });
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
      /* WFGG_TRAIN_API_PROXY
         Les API historiques du frontend Train utilisent /api/*.
         Le Portail les transmet au backend Train.
      */
      if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
        return await proxyRoute(
          request,
          UPSTREAMS.trainApi,
          url.pathname,
          { routeName: 'train-api' }
        );
      }

      if (url.pathname === '/guides' || url.pathname.startsWith('/guides/')) {
        return await routeGuides(request);
      }

      if (url.pathname === '/train' || url.pathname.startsWith('/train/')) {
        return await routeTrain(request);
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
