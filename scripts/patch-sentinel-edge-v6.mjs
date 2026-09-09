import fs from 'node:fs';

const FILE='frontend/_worker.js';
let src=fs.readFileSync(FILE,'utf8');

const oldRoute=`      if (url.pathname === '/portal-api/sentinel/run') {
        return await proxyRoute(request, UPSTREAMS.portalApi, '/api/sentinel/run', {
          routeName: 'portal-sentinel-api'
        });
      }`;
const newRoute=`      if (url.pathname === '/portal-api/sentinel/run') {
        return await runSentinelAtPortalEdge(request);
      }`;
if(!src.includes(oldRoute)) throw new Error('Sentinel proxy route not found');
src=src.replace(oldRoute,newRoute);

const insertionPoint='async function routeSimulator(request) {';
if(!src.includes(insertionPoint)) throw new Error('routeSimulator insertion point missing');

const helper=`/* WFGG_SENTINEL_EDGE_RUNNER_V6
   Sentinel reste strictement OWNER et lecture seule, mais sa recette est exécutée
   par le Worker Pages déjà déployé. Cela évite de dépendre d'un second déploiement
   wfgg-api tout en conservant la validation OWNER côté serveur. */
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
  const response=await fetch(new Request(target.toString(),{
    method:'GET',headers,redirect:'manual'
  }));
  let data=null;
  try{data=await response.clone().json();}catch(_){}
  return {response,data};
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
  if(meCall.data?.system?.role!=='OWNER'){
    return sentinelEdgeJson({ok:false,error:'SENTINEL_OWNER_ONLY'},403);
  }

  const checks=[];
  checks.push(sentinelEdgeCheck(
    'owner-access','Sécurité','ok','Accès Sentinel','Rôle système OWNER','OWNER validé côté serveur',
    'Le bouton et la recette restent inaccessibles aux autres rangs.',''
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
      {'Authorization':null,'X-WfGg-Portal-Token':token,'Accept':'application/json'}
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
      'train-owner-roster','Session & données',rosterHasMe?'ok':'error','Utilisateur courant dans le roster','OWNER présent dans le roster',rosterHasMe?'Présent':'Absent','',
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

  const counts={ok:0,info:0,warning:0,error:0};
  for(const item of checks)counts[item.level]=(counts[item.level]||0)+1;
  const status=counts.error?'error':counts.warning?'warning':counts.info?'info':'ok';
  return sentinelEdgeJson({
    ok:!counts.error,
    version:'sentinel-edge-v6',
    mode:'observer',
    readonly:true,
    finishedAt:new Date().toISOString(),
    summary:{status,counts,total:checks.length},
    checks
  });
}

`;
src=src.replace(insertionPoint,helper+insertionPoint);

if(!src.includes('WFGG_SENTINEL_EDGE_RUNNER_V6'))throw new Error('edge marker missing');
if(!src.includes("return await runSentinelAtPortalEdge(request);"))throw new Error('edge route missing');
fs.writeFileSync(FILE,src);
console.log('WFGG_SENTINEL_EDGE_RUNNER_V6=PATCHED');
