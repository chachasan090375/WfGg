import fs from 'node:fs';

const workerPath='frontend/_worker.js';
const clientPath='frontend/train-native/sentinel-train-v1.js';
let worker=fs.readFileSync(workerPath,'utf8');
let client=fs.readFileSync(clientPath,'utf8');

function replaceWorker(from,to,label){
  if(!worker.includes(from))throw new Error(`WORKER_PATCH_MISSING ${label}`);
  worker=worker.replace(from,to);
}
function replaceClient(from,to,label){
  if(!client.includes(from))throw new Error(`CLIENT_PATCH_MISSING ${label}`);
  client=client.replace(from,to);
}

/* ---------- Portal edge ---------- */
if(!worker.includes("'X-WfGg-Sentinel-Diagnostic':'v10'")){
  replaceWorker(
    "{'Authorization':null,'X-WfGg-Portal-Token':token,'Accept':'application/json'}",
    "{'Authorization':null,'X-WfGg-Portal-Token':token,'X-WfGg-Sentinel-Diagnostic':'v10','Accept':'application/json'}",
    'snapshot diagnostic header'
  );
}

if(!worker.includes('sentinel-source-index')){
  replaceWorker(
`  const contextOk=!!contextCall?.response?.ok;
  checks.push(sentinelEdgeCheck(
    'sentinel-deep-portal-context','Diagnostic automatique',contextOk?'ok':'error',
    'Contexte Portail → Train','/api/train/context HTTP 200',
    contextCall?'HTTP '+contextCall.response.status:'Erreur réseau',
    contextCall?sentinelResponseMeta(contextCall):contextError,
    contextOk?'':'La résolution d’identité Portail destinée à Train échoue avant même le snapshot.'
  ));

  if(snapCall?.response){`,
`  const contextOk=!!contextCall?.response?.ok;
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

  if(snapCall?.response){`,
    'train source index probe'
  );
}

if(!worker.includes('runtimeDiagnostic=snapCall?.data?.sentinelDiagnostic')){
  replaceWorker(
`  let root={
    component:'Sentinel',stage:'anomalie à classifier',codeArea:'contrôle '+String(anomalies[0]?.id||'inconnu'),
    cause:String(anomalies[0]?.probableCause||'Une anomalie a été détectée mais la couche exacte reste à confirmer.')
  };`,
`  const runtimeDiagnostic=snapCall?.data?.sentinelDiagnostic||null;
  const trainSourceMap=trainSourceCall?.data||null;
  let root={
    component:'Sentinel',stage:'anomalie à classifier',codeArea:'contrôle '+String(anomalies[0]?.id||'inconnu'),
    cause:String(anomalies[0]?.probableCause||'Une anomalie a été détectée mais la couche exacte reste à confirmer.')
  };`,
    'runtime diagnostic vars'
  );
}

if(!worker.includes("stage:'étape interne '+runtimeDiagnostic.stage")){
  replaceWorker(
`  }else if(!snapCall.response.ok){
    const cf=sentinelClassifyCloudflareFailure(snapCall);
    if(cf){
      root=cf;
    }else{`,
`  }else if(!snapCall.response.ok){
    if(runtimeDiagnostic?.stage){
      root={
        component:'wfgg-train',
        stage:'étape interne '+runtimeDiagnostic.stage,
        codeArea:'worker.js :: '+runtimeDiagnostic.stage,
        cause:'Le Worker Train a identifié lui-même la première étape ayant levé l’erreur.',
        source:runtimeDiagnostic.source||trainSourceMap?.stages?.[runtimeDiagnostic.stage]||null,
        stack:sentinelSanitizeSnippet(runtimeDiagnostic.stack||'')
      };
    }else{
      const cf=sentinelClassifyCloudflareFailure(snapCall);
      if(cf){
        root=cf;
      }else{`,
    'runtime diagnostic priority'
  );
  replaceWorker(
`      };
    }
  }else if(checks.some(item=>item.id==='train-access-roster'&&item.level==='error')){`,
`      };
      }
    }
  }else if(checks.some(item=>item.id==='train-access-roster'&&item.level==='error')){`,
    'close runtime diagnostic branch'
  );
}

if(!worker.includes('Source exacte: ')){
  replaceWorker(
`  const evidence=[
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

  return {rootCause:root,evidence,readonly:true,anomalyIds:anomalies.map(item=>item.id)};`,
`  if(!root.source&&trainSourceMap?.stages){
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

  return {rootCause:root,evidence,source,readonly:true,anomalyIds:anomalies.map(item=>item.id)};`,
    'source-enriched root cause'
  );
}

worker=worker.replace("version:'sentinel-edge-v9'","version:'sentinel-edge-v10'");
worker=worker.replace("script.src='/train/sentinel-train-v1.js?v=007';","script.src='/train/sentinel-train-v1.js?v=010';");

/* ---------- Sentinel client ---------- */
client=client.replace("const VERSION = 'sentinel-train-v7';","const VERSION = 'sentinel-train-v10';");

if(!client.includes('async function loadPortalSourceMap')){
  replaceClient(
`  async function confirmAccess() {`,
`  async function loadPortalSourceMap() {
    try {
      const response = await fetch('/sentinel-source-map-v10.json?sentinel=' + Date.now(), { method:'GET', cache:'no-store', credentials:'omit' });
      if (!response.ok) return null;
      const data = await response.json();
      return data?.version === 'sentinel-portal-source-map-v10' ? data : null;
    } catch (_) { return null; }
  }

  async function confirmAccess() {`,
    'portal source map loader'
  );
}

if(!client.includes('historique résolu')){
  replaceClient(
`      const [serverResult, local] = await Promise.all([portalFetch('/api/sentinel/run'), localChecks()]);
      const { response, data } = serverResult;`,
`      const [serverResult, local, portalSourceMap] = await Promise.all([portalFetch('/api/sentinel/run'), localChecks(), loadPortalSourceMap()]);
      const { response, data } = serverResult;`,
    'run source map promise'
  );
  replaceClient(
`      const checks = [...(Array.isArray(data?.checks) ? data.checks : []), ...local];
      const counts = { ok:0, info:0, warning:0, error:0 };`,
`      const serverChecks=Array.isArray(data?.checks) ? data.checks : [];
      const liveSnapshotOk=serverChecks.some(item=>item?.id==='train-snapshot'&&item?.level==='ok');
      const staleProbe=local.find(item=>item?.id==='train-portal-bridge-probe');
      if(liveSnapshotOk&&staleProbe&&staleProbe.level==='warning'){
        const oldObserved=staleProbe.observed;
        staleProbe.level='ok';
        staleProbe.title='Probe Portail → Train (historique résolu)';
        staleProbe.expected='Le snapshot courant doit être valide';
        staleProbe.observed='Snapshot courant HTTP 200 · ancien probe: '+oldObserved;
        staleProbe.detail='L’ancien échec est conservé comme trace locale mais il n’est plus une anomalie active.';
        staleProbe.probableCause='';
      }
      if(portalSourceMap){
        local.push({
          id:'sentinel-source-build',area:'Sentinel · sources',level:'ok',title:'Index des sources Portail',
          expected:'Build courant localisable',
          observed:'commit '+String(portalSourceMap.sourceCommit||'').slice(0,12)+' · '+Object.keys(portalSourceMap.files||{}).length+' fichier(s) indexé(s)',
          detail:'Sentinel peut rattacher ses diagnostics Portail aux lignes du build déployé.',probableCause:''
        });
      }
      const checks = [...serverChecks, ...local];
      const counts = { ok:0, info:0, warning:0, error:0 };`,
    'resolve stale probe and add build check'
  );
  replaceClient(
`      lastReport = { ...data, checks, summary:{ status, counts, total:checks.length }, finishedAt:data?.finishedAt || new Date().toISOString(), source:'train' };`,
`      lastReport = { ...data, checks, portalSourceMap, summary:{ status, counts, total:checks.length }, finishedAt:data?.finishedAt || new Date().toISOString(), source:'train' };`,
    'keep portal source map'
  );
}

if(!client.includes("item.source ? `<b>Source</b>")){
  replaceClient(
`        <div class="wfgg-sentinel-kv"><b>${esc(t('expected'))}</b><span>${esc(item.expected || '—')}</span><b>${esc(t('observed'))}</b><span>${esc(item.observed || '—')}</span>${item.detail ? `<b>${esc(t('details'))}</b><span>${esc(item.detail)}</span>` : ''}</div>
        ${item.probableCause ? `<div class="wfgg-sentinel-cause"><b>${esc(t('cause'))} :</b> ${esc(item.probableCause)}</div>` : ''}`,
`        <div class="wfgg-sentinel-kv"><b>${esc(t('expected'))}</b><span>${esc(item.expected || '—')}</span><b>${esc(t('observed'))}</b><span>${esc(item.observed || '—')}</span>${item.detail ? `<b>${esc(t('details'))}</b><span>${esc(item.detail)}</span>` : ''}${item.source ? `<b>Source</b><span>${esc([item.source.repository,item.source.file+(item.source.line?':'+item.source.line:''),item.source.function?'fonction '+item.source.function:'',item.source.sourceCommit?'commit '+String(item.source.sourceCommit).slice(0,12):''].filter(Boolean).join(' · '))}</span>` : ''}${item.stack ? `<b>Pile</b><span>${esc(item.stack)}</span>` : ''}</div>
        ${item.probableCause ? `<div class="wfgg-sentinel-cause"><b>${esc(t('cause'))} :</b> ${esc(item.probableCause)}</div>` : ''}`,
    'render source and stack'
  );
}

client=client.replace("'WFGG_SENTINEL_REPORT_V2',","'WFGG_SENTINEL_REPORT_V3',");
client=client.replace("if (!lastReport) return `WFGG_SENTINEL_REPORT_V2\\n${t('noReport')}`;","if (!lastReport) return `WFGG_SENTINEL_REPORT_V3\\n${t('noReport')}`;");

if(!client.includes('Build Portail:')){
  replaceClient(
`      `Résumé: ok=${lastReport.summary?.counts?.ok || 0}; info=${lastReport.summary?.counts?.info || 0}; warning=${lastReport.summary?.counts?.warning || 0}; error=${lastReport.summary?.counts?.error || 0}`,
      '',`,
`      `Résumé: ok=${lastReport.summary?.counts?.ok || 0}; info=${lastReport.summary?.counts?.info || 0}; warning=${lastReport.summary?.counts?.warning || 0}; error=${lastReport.summary?.counts?.error || 0}`,
      `Build Portail: ${lastReport.portalSourceMap?.sourceCommit || '—'} · Sentinel ${VERSION}`,
      '',`,
    'report build header'
  );
  replaceClient(
`      if (item.detail) lines.push(`Détail: ${item.detail}`);
      if (item.probableCause) lines.push(`Cause probable: ${item.probableCause}`);`,
`      if (item.detail) lines.push(`Détail: ${item.detail}`);
      if (item.source) lines.push('Source: '+[item.source.repository,item.source.file+(item.source.line?':'+item.source.line:''),item.source.function?'fonction '+item.source.function:'',item.source.sourceCommit?'commit '+String(item.source.sourceCommit).slice(0,12):''].filter(Boolean).join(' · '));
      if (item.stack) lines.push('Pile: '+String(item.stack).replace(/\\n/g,' | '));
      if (item.probableCause) lines.push(`Cause probable: ${item.probableCause}`);`,
    'report source fields'
  );
}

fs.writeFileSync(workerPath,worker);
fs.writeFileSync(clientPath,client);
console.log('WFGG_SENTINEL_SOURCE_DIAGNOSTICS_V10=OK');
