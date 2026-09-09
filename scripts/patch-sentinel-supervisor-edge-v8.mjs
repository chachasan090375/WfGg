import fs from 'node:fs';

const path = 'frontend/_worker.js';
let source = fs.readFileSync(path, 'utf8');

function replaceOnce(from, to, label) {
  if (!source.includes(from)) throw new Error(`PATCH_MISSING ${label}`);
  source = source.replace(from, to);
}

replaceOnce(
`async function runSentinelAtPortalEdge(request){`,
`/* WFGG_SENTINEL_SUPERVISOR_FALLBACK_V8
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

async function runSentinelAtPortalEdge(request){`,
  'insert supervisor fallback'
);

replaceOnce(
`  const sentinelRole=String(meCall.data?.system?.role||'');
  if(!['OWNER','SUPERVISOR'].includes(sentinelRole)){`,
`  const sentinelRole=sentinelEffectiveRole(meCall.data);
  if(!['OWNER','SUPERVISOR'].includes(sentinelRole)){`,
  'effective role in runner'
);

replaceOnce(
`      'train-owner-roster','Session & données',rosterHasMe?'ok':'error','Utilisateur courant dans le roster','OWNER présent dans le roster',rosterHasMe?'Présent':'Absent','',`,
`      'train-access-roster','Session & données',rosterHasMe?'ok':'error','Utilisateur courant dans le roster','Utilisateur autorisé présent dans le roster',rosterHasMe?'Présent':'Absent','',`,
  'neutral roster wording'
);

replaceOnce("version:'sentinel-edge-v7'", "version:'sentinel-edge-v8'", 'edge version');

replaceOnce(
`      if (url.pathname === '/portal-api/me') {
        return await proxyRoute(request, UPSTREAMS.portalApi, '/api/me', {
          routeName: 'portal-sentinel-api'
        });
      }`,
`      if (url.pathname === '/portal-api/me') {
        return await sentinelPortalMeAtEdge(request);
      }`,
  'decorate portal me route'
);

fs.writeFileSync(path, source);
console.log('WFGG_SENTINEL_SUPERVISOR_EDGE_V8=OK');
