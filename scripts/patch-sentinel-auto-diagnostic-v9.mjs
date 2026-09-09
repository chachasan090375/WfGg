import fs from 'node:fs';

const path='frontend/_worker.js';
let source=fs.readFileSync(path,'utf8');

function replaceOnce(from,to,label){
  if(!source.includes(from))throw new Error(`PATCH_MISSING ${label}`);
  source=source.replace(from,to);
}

replaceOnce(
`async function sentinelEdgeFetchJson(request,origin,path,extraHeaders={}){
  const target=new URL(path,origin);
  const headers=new Headers(request.headers);
  headers.delete('Origin');
  headers.delete('Referer');
  for(const [key,value] of Object.entries(extraHeaders)){
    if(value==null)headers.delete(key);else headers.set(key,String(value));
  }
  const response=await fetch(new Request(target.toString(),{
    method:'GET',headers,redirect:'manual'
  }));
  let data=null;
  try{data=await response.clone().json();}catch(_){}
  return {response,data};
}`,
`async function sentinelEdgeFetchJson(request,origin,path,extraHeaders={}){
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
}`,
  'enhanced edge fetch metadata'
);

replaceOnce(
`async function runSentinelAtPortalEdge(request){`,
`/* WFGG_SENTINEL_AUTO_DIAGNOSTIC_V9
   Sentinel reste strictement en lecture seule. Quand une anomalie est détectée,
   une seconde passe suit automatiquement la chaîne Portail -> contexte Train ->
   Worker Train et classe la première rupture observable. Aucun POST/PUT/DELETE
   n'est exécuté par ce diagnostic. */
function sentinelSanitizeSnippet(value){
  return String(value||'')
    .replace(/Bearer\\s+[A-Za-z0-9._~+\\/-]+/gi,'Bearer [redacted]')
    .replace(/(token|session|authorization)(["']?\\s*[:=]\\s*["'])[^"']+/gi,'$1$2[redacted]')
    .replace(/\\s+/g,' ')
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

  const evidence=[
    'Portail /api/me: HTTP '+String(meCall?.response?.status||'?'),
    'Contexte Train: '+(contextCall?'HTTP '+contextCall.response.status:'sans réponse'),
    'Snapshot Train: '+(snapCall?'HTTP '+snapCall.response.status:'sans réponse')
  ].join(' · ');

  checks.push(sentinelEdgeCheck(
    'sentinel-root-cause','Diagnostic automatique','info',
    'Cause racine Sentinel','Premier composant fautif isolé sans modification',
    root.component+' · '+root.stage,
    'Zone code: '+root.codeArea+' · '+evidence,
    root.cause
  ));

  return {rootCause:root,evidence,readonly:true,anomalyIds:anomalies.map(item=>item.id)};
}

async function runSentinelAtPortalEdge(request){`,
  'deep diagnostic helpers'
);

replaceOnce(
`  const counts={ok:0,info:0,warning:0,error:0};
  for(const item of checks)counts[item.level]=(counts[item.level]||0)+1;
  const status=counts.error?'error':counts.warning?'warning':counts.info?'info':'ok';
  return sentinelEdgeJson({
    ok:!counts.error,
    version:'sentinel-edge-v8',
    mode:'observer',
    readonly:true,
    finishedAt:new Date().toISOString(),
    summary:{status,counts,total:checks.length},
    checks
  });`,
`  const diagnosis=await sentinelRunDeepDiagnostics(request,token,meCall,snapCall,checks);

  const counts={ok:0,info:0,warning:0,error:0};
  for(const item of checks)counts[item.level]=(counts[item.level]||0)+1;
  const status=counts.error?'error':counts.warning?'warning':counts.info?'info':'ok';
  return sentinelEdgeJson({
    ok:!counts.error,
    version:'sentinel-edge-v9',
    mode:'observer',
    readonly:true,
    autoDiagnostic:true,
    finishedAt:new Date().toISOString(),
    summary:{status,counts,total:checks.length},
    diagnosis,
    checks
  });`,
  'run deep diagnostics before summary'
);

fs.writeFileSync(path,source);
console.log('WFGG_SENTINEL_AUTO_DIAGNOSTIC_V9=OK');
