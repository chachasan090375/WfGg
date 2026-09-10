import fs from 'node:fs';

const workerPath='frontend/_worker.js';
const guardPath='frontend/portal-auth-mobile-guard-v1.js';

let worker=fs.readFileSync(workerPath,'utf8');
let guard=fs.readFileSync(guardPath,'utf8');

if(!worker.includes('WFGG_PORTAL_MODULE_SESSION_ENDPOINT_V1')){
  const anchor=`function portalLoginRedirect(request) {\n  const incoming = new URL(request.url);\n  const target = new URL('/', incoming.origin);\n  target.searchParams.set('returnTo', incoming.pathname + incoming.search);\n  return Response.redirect(target.toString(), 302);\n}\n`;
  if(!worker.includes(anchor)) throw new Error('worker anchor portalLoginRedirect not found');
  const addition=`${anchor}\n/* WFGG_PORTAL_MODULE_SESSION_ENDPOINT_V1\n   Le portail actif stocke sa session dans localStorage, invisible au Worker.\n   Cette route same-origin valide d'abord le Bearer auprès de wfgg-api, puis pose\n   un cookie HttpOnly utilisé uniquement pour autoriser les navigations modules. */\nasync function issuePortalModuleSession(request) {\n  if (request.method === 'DELETE') {\n    return new Response(null, {\n      status: 204,\n      headers: {\n        'Cache-Control': 'no-store',\n        'Set-Cookie': 'wfgg_portal_session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict'\n      }\n    });\n  }\n\n  if (request.method !== 'POST') {\n    return new Response('Method not allowed', { status: 405, headers: { 'Cache-Control': 'no-store' } });\n  }\n\n  const authorization = request.headers.get('Authorization') || '';\n  const match = authorization.match(/^Bearer\\s+(.+)$/i);\n  if (!match) return new Response('Portal auth required', { status: 401, headers: { 'Cache-Control': 'no-store' } });\n\n  const token = match[1].trim();\n  if (!token) return new Response('Portal auth required', { status: 401, headers: { 'Cache-Control': 'no-store' } });\n\n  try {\n    const check = await fetch(UPSTREAMS.portalApi.origin + '/api/me', {\n      method: 'GET',\n      headers: { 'Authorization': 'Bearer ' + token, 'Accept': 'application/json' }\n    });\n    if (!check.ok) return new Response('Portal auth required', { status: 401, headers: { 'Cache-Control': 'no-store' } });\n  } catch {\n    return new Response('Portal session validation unavailable', { status: 503, headers: { 'Cache-Control': 'no-store' } });\n  }\n\n  return new Response(null, {\n    status: 204,\n    headers: {\n      'Cache-Control': 'no-store',\n      'Set-Cookie': 'wfgg_portal_session=' + encodeURIComponent(token) + '; Path=/; Max-Age=2592000; Secure; HttpOnly; SameSite=Strict'\n    }\n  });\n}\n`;
  worker=worker.replace(anchor,addition);
}

if(!worker.includes("url.pathname === '/api/module-session'")){
  const anchor=`      /* WFGG_TRAIN_API_PROXY\n         Les API historiques du frontend Train utilisent /api/*.\n         Le Portail les transmet au backend Train.\n      */`;
  if(!worker.includes(anchor)) throw new Error('worker API routing anchor not found');
  worker=worker.replace(anchor,`      if (url.pathname === '/api/module-session') {\n        return await issuePortalModuleSession(request);\n      }\n\n${anchor}`);
}

if(!guard.includes('WFGG_PORTAL_MODULE_LINK_BRIDGE_V1')){
  const anchor="const input=document.getElementById('authCode');\n";
  if(!guard.includes(anchor)) throw new Error('mobile guard anchor not found');
  const addition=`/* WFGG_PORTAL_MODULE_LINK_BRIDGE_V1\n   Synchronise une session serveur HttpOnly avant d'ouvrir Guides/Train. Le\n   contrôle final reste dans le Worker : sans session Portail valide, le module\n   est refusé même si son URL exacte est connue. */\nconst PORTAL_TOKEN_KEY='wfgg_portal_session';\nlet moduleSessionReady=false;\nlet moduleSessionPromise=null;\nasync function syncPortalModuleSession(){\n  const portalToken=localStorage.getItem(PORTAL_TOKEN_KEY);\n  if(!portalToken){moduleSessionReady=false;return false;}\n  if(moduleSessionPromise)return moduleSessionPromise;\n  moduleSessionPromise=fetch('/api/module-session',{\n    method:'POST',\n    headers:{'Authorization':'Bearer '+portalToken},\n    credentials:'same-origin',\n    cache:'no-store'\n  }).then(r=>{moduleSessionReady=r.ok;return r.ok;}).catch(()=>{moduleSessionReady=false;return false;}).finally(()=>{moduleSessionPromise=null;});\n  return moduleSessionPromise;\n}\nif(localStorage.getItem(PORTAL_TOKEN_KEY))syncPortalModuleSession();\nwindow.addEventListener('pageshow',()=>{if(localStorage.getItem(PORTAL_TOKEN_KEY))syncPortalModuleSession();});\ndocument.addEventListener('click',event=>{\n  const link=event.target.closest?.('a[data-module][href]');\n  if(!link)return;\n  if(moduleSessionReady)return;\n  event.preventDefault();\n  const target=link.href;\n  syncPortalModuleSession().then(ok=>{\n    if(ok){location.href=target;return;}\n    const u=new URL('/',location.origin);\n    try{const t=new URL(target,location.href);u.searchParams.set('returnTo',t.pathname+t.search);}catch{}\n    location.href=u.toString();\n  });\n},true);\n\n${anchor}`;
  guard=guard.replace(anchor,addition);
}

fs.writeFileSync(workerPath,worker);
fs.writeFileSync(guardPath,guard);
console.log('WFGG_PORTAL_MODULE_LINKS_FIX_V1=PATCHED');
