from pathlib import Path

WORKER=Path('frontend/_worker.js')
CLIENT=Path('frontend/train-native/sentinel-train-v1.js')
worker=WORKER.read_text(encoding='utf-8')
client=CLIENT.read_text(encoding='utf-8')

def replace_once(text,old,new,label):
    if old not in text:
        raise SystemExit('PATCH_MISSING '+label)
    return text.replace(old,new,1)

if 'WFGG_SENTINEL_PRESCRIPTIVE_EDGE_V12' not in worker:
    old="  const diagnosis=await sentinelRunDeepDiagnostics(request,token,meCall,snapCall,checks);"
    new="""  const diagnosis=await sentinelRunDeepDiagnostics(request,token,meCall,snapCall,checks);

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
  }"""
    worker=replace_once(worker,old,new,'edge repair-plan insertion')
    worker=replace_once(worker,"    diagnosis,\n    checks","    diagnosis,\n    repairPlan,\n    checks",'edge response repairPlan')

worker=worker.replace("script.src='/train/sentinel-train-v1.js?v=012';","script.src='/train/sentinel-train-v1.js?v=013';")

client=client.replace("const VERSION = 'sentinel-train-v11';","const VERSION = 'sentinel-train-v12';")
client=client.replace('WFGG_SENTINEL_REPORT_V4','WFGG_SENTINEL_REPORT_V5')

if 'WFGG_SENTINEL_LOCAL_REPAIR_V12' not in client:
    old="""    return items;
  }

  async function runSentinel() {"""
    new="""    return items;
  }

  /* WFGG_SENTINEL_LOCAL_REPAIR_V12
     Les anomalies exclusivement visibles sur l'appareil reçoivent elles aussi
     des hypothèses de correction. Rien n'est exécuté : ces objets sont des
     recommandations destinées à une deuxième validation humaine. */
  function localRepairCandidateV12(input){
    return {...input,readonly:true,applied:false,source:input.source||null,evidence:input.evidence||[],risks:input.risks||[],manualValidation:input.manualValidation||[]};
  }
  function localRepairCandidatesV12(items,portalSourceMap){
    const out=[];
    const bad=new Map((items||[]).filter(x=>x&&(x.level==='error'||x.level==='warning')).map(x=>[x.id,x]));
    const portalSource=(file,fn)=>({repository:'chachasan090375/WfGg',file,function:fn||null,line:portalSourceMap?.files?.[file]?.functions?.[fn]?.line||null,sourceCommit:portalSourceMap?.sourceCommit||null});
    if(bad.has('train-local-notification-handler'))out.push(localRepairCandidateV12({
      id:'repair-local-notification-export-v12',title:'Rétablir le câblage du test notification locale',score:97,verdict:'recommended',
      target:'frontend/train-native/app.v15.js :: window.W',proposedChange:'Exporter testLocalNotification dans window.W sans remplacer le test Push serveur.',
      simulation:{handlerPresent:typeof window.W?.testLocalNotification==='function',expectedAfterPatch:true},
      evidence:['Le bouton appelle W.testLocalNotification().','Le contrôle local vérifie directement cet export.'],risks:['Ne pas aliaser vers le test Push serveur : les deux tests ont des rôles différents.'],
      manualValidation:['Relancer Sentinel.','Appuyer manuellement sur Tester l’affichage local.'],source:portalSource('frontend/train-native/app.v15.js','testLocalNotification')
    }));
    if(bad.has('train-push-sw'))out.push(localRepairCandidateV12({
      id:'repair-push-sw-register-v12',title:'Réenregistrer le Service Worker Push Train',score:94,verdict:'recommended-manual',
      target:'/train/wfgg-push-sw.js',proposedChange:'Réenregistrer le Service Worker Push sous le scope /train/ puis vérifier son état active.',
      simulation:{serviceWorkerSupported:'serviceWorker' in navigator},evidence:['Le canal Push local est absent ou inactif.'],risks:['Ne pas supprimer la session Portail ni les autres Service Workers du site.'],manualValidation:['Vérifier active puis relancer Sentinel.']
    }));
    if(bad.has('train-push-subscription'))out.push(localRepairCandidateV12({
      id:'repair-local-push-subscribe-v12',title:'Recréer l’abonnement Push de cet appareil',score:95,verdict:'recommended-manual',
      target:'PushManager + /api/push/subscribe',proposedChange:'Créer un abonnement avec la clé VAPID serveur courante puis l’enregistrer côté Train.',
      simulation:{permission:('Notification' in window)?Notification.permission:'unsupported'},evidence:['Aucun endpoint Push local utilisable.'],risks:['Une autorisation refusée par le navigateur bloque cette correction.'],manualValidation:['Vérifier ensuite l’abonnement serveur et envoyer explicitement un Push de test.']
    }));
    if(bad.has('train-notification-permission'))out.push(localRepairCandidateV12({
      id:'repair-notification-permission-v12',title:'Autoriser les notifications pour WfGg',score:93,verdict:'recommended-manual',
      target:'Réglages navigateur / Android',proposedChange:'Autoriser les notifications pour wfgg.pages.dev puis refaire l’abonnement Push.',
      simulation:{permission:('Notification' in window)?Notification.permission:'unsupported'},evidence:['La permission système/navigateur n’est pas granted.'],risks:['Sentinel ne peut pas changer une permission système.'],manualValidation:['Revenir dans Train puis relancer Sentinel.']
    }));
    if(bad.has('train-ui-functional-contract'))out.push(localRepairCandidateV12({
      id:'repair-ui-export-contract-v12',title:'Rétablir les actions Train manquantes dans window.W',score:90,verdict:'recommended-manual',
      target:'frontend/train-native/app.v15.js :: window.W',proposedChange:'Réexporter uniquement les fonctions signalées manquantes, sans modifier leur logique métier.',
      simulation:{contractCheck:'typeof window.W[name] === function'},evidence:['Une action visible n’est plus exposée par le runtime.'],risks:['Une fonction réellement supprimée ne doit pas être recréée par simple alias.'],manualValidation:['Comparer la liste des fonctions manquantes avec leurs handlers réels.'],source:portalSource('frontend/train-native/app.v15.js','window.W')
    }));
    if(bad.has('train-calendar-runtime'))out.push(localRepairCandidateV12({
      id:'repair-calendar-runtime-v12',title:'Rétablir le runtime d’export calendrier',score:78,verdict:'alternative',
      target:'app.v15.js :: addCalendar/addAllCalendar',proposedChange:'Vérifier Blob, URL.createObjectURL et les deux handlers ICS avant de toucher au format calendrier.',
      simulation:{blob:typeof Blob==='function',objectUrl:typeof URL?.createObjectURL==='function',addCalendar:typeof window.W?.addCalendar==='function',addAllCalendar:typeof window.W?.addAllCalendar==='function'},
      evidence:['Sentinel peut isoler le maillon runtime absent.'],risks:['Le problème peut venir du navigateur plutôt que du code.'],manualValidation:['Tester un export ICS manuel après correction.']
    }));
    return out;
  }

  async function runSentinel() {"""
    client=replace_once(client,old,new,'local repair helpers')

    old="""      const checks = [...serverChecks, ...local];
      const counts = { ok:0, info:0, warning:0, error:0 };"""
    new="""      const checks = [...serverChecks, ...local];
      const backendCandidates=Array.isArray(data?.repairPlan?.candidates)?data.repairPlan.candidates:[];
      const localCandidates=localRepairCandidatesV12(local,portalSourceMap);
      const repairCandidates=[...backendCandidates,...localCandidates].sort((a,b)=>Number(b?.score||0)-Number(a?.score||0)||String(a?.id||'').localeCompare(String(b?.id||'')));
      const repairRecommended=repairCandidates.find(x=>x?.verdict==='recommended'||x?.verdict==='recommended-manual')||null;
      const repairPlan={
        version:'sentinel-repair-plan-v12',readonly:true,applied:false,
        server:data?.repairPlan||null,candidates:repairCandidates,recommended:repairRecommended
      };
      const counts = { ok:0, info:0, warning:0, error:0 };"""
    client=replace_once(client,old,new,'merge repair candidates')
    client=replace_once(client,"lastReport = { ...data, checks, portalSourceMap, summary:{ status, counts, total:checks.length }, finishedAt:data?.finishedAt || new Date().toISOString(), source:'train' };","lastReport = { ...data, checks, repairPlan, portalSourceMap, summary:{ status, counts, total:checks.length }, finishedAt:data?.finishedAt || new Date().toISOString(), source:'train' };",'lastReport repair plan')

if 'wfgg-sentinel-repair-card' not in client:
    css_anchor="#${OVERLAY_ID} .wfgg-sentinel-foot{margin:13px 1px 2px;color:#858f9f;font-size:.72rem}"
    css_extra=css_anchor+"\n      #${OVERLAY_ID} .wfgg-sentinel-repair-head{margin:17px 0 8px;padding-top:13px;border-top:1px solid rgba(255,255,255,.1);font-weight:900;color:#e4c975}#${OVERLAY_ID} .wfgg-sentinel-repair-card{border:1px solid rgba(118,91,160,.42);background:linear-gradient(180deg,rgba(78,57,108,.22),rgba(21,27,39,.92));border-radius:15px;padding:12px 13px;margin-top:9px}#${OVERLAY_ID} .wfgg-sentinel-repair-card[data-verdict^=\"recommended\"]{border-color:rgba(89,197,139,.5);background:linear-gradient(180deg,rgba(35,101,71,.18),rgba(21,27,39,.94))}#${OVERLAY_ID} .wfgg-sentinel-repair-score{float:right;font-weight:950;color:#f1d27b}#${OVERLAY_ID} .wfgg-sentinel-repair-badge{display:inline-block;margin:6px 0;padding:3px 7px;border-radius:999px;background:rgba(255,255,255,.07);font-size:.67rem;font-weight:900;letter-spacing:.04em}"
    client=replace_once(client,css_anchor,css_extra,'repair css')

if 'renderRepairPlanV12' not in client:
    old="""    syncButtonState();
  }

  function reportText() {"""
    new="""    renderRepairPlanV12(report);
    syncButtonState();
  }

  function repairVerdictLabelV12(value){
    return value==='recommended'?'RECOMMANDÉ':value==='recommended-manual'?'RECOMMANDÉ · VALIDATION MANUELLE':value==='alternative'?'ALTERNATIVE':value==='manual-review'?'REVUE MANUELLE':'REJETÉ';
  }
  function repairJsonV12(value){try{return JSON.stringify(value)}catch(_){return String(value??'—')}}
  function renderRepairPlanV12(report){
    const list=popup().querySelector('#wfggTrainSentinelList');
    const repairs=Array.isArray(report?.repairPlan?.candidates)?report.repairPlan.candidates:[];
    if(!repairs.length)return;
    const cards=repairs.slice(0,8).map(item=>`<article class=\"wfgg-sentinel-repair-card\" data-verdict=\"${esc(item.verdict||'')}\"><span class=\"wfgg-sentinel-repair-score\">${Number(item.score||0)}/100</span><strong>${esc(item.title||item.id||'Correctif')}</strong><br><span class=\"wfgg-sentinel-repair-badge\">${esc(repairVerdictLabelV12(item.verdict))}</span><div class=\"wfgg-sentinel-kv\"><b>Cible</b><span>${esc(item.target||'—')}</span><b>Proposition</b><span>${esc(item.proposedChange||'—')}</span><b>Simulation</b><span>${esc(repairJsonV12(item.simulation))}</span>${item.risks?.length?`<b>Risques</b><span>${esc(item.risks.join(' · '))}</span>`:''}${item.manualValidation?.length?`<b>Validation</b><span>${esc(item.manualValidation.join(' · '))}</span>`:''}</div>${item.source?`<div class=\"wfgg-sentinel-cause\"><b>Source :</b> ${esc([item.source.repository,item.source.file+(item.source.line?':'+item.source.line:''),item.source.function?'fonction '+item.source.function:''].filter(Boolean).join(' · '))}</div>`:''}</article>`).join('');
    list.insertAdjacentHTML('beforeend',`<div class=\"wfgg-sentinel-repair-head\">🧭 CORRECTIFS SIMULÉS (${repairs.length}) · AUCUN CORRECTIF APPLIQUÉ</div>${cards}`);
  }

  function reportText() {"""
    client=replace_once(client,old,new,'repair render functions')

    old="""    lines.push('', 'MODE: OBSERVATEUR / LECTURE SEULE', 'Aucune correction automatique effectuée par Sentinel.');"""
    new="""    const repairs=Array.isArray(lastReport.repairPlan?.candidates)?lastReport.repairPlan.candidates:[];
    lines.push('', `CORRECTIFS SIMULÉS (${repairs.length})`);
    for(const item of repairs){
      lines.push('', `[${repairVerdictLabelV12(item.verdict)}] ${item.title||item.id||'Correctif'} · score=${Number(item.score||0)}/100`);
      if(item.target)lines.push(`Cible: ${item.target}`);
      if(item.proposedChange)lines.push(`Correctif proposé: ${item.proposedChange}`);
      if(item.simulation)lines.push(`Simulation: ${repairJsonV12(item.simulation)}`);
      if(item.evidence?.length)lines.push(`Preuves: ${item.evidence.join(' | ')}`);
      if(item.risks?.length)lines.push(`Risques: ${item.risks.join(' | ')}`);
      if(item.manualValidation?.length)lines.push(`Validation manuelle: ${item.manualValidation.join(' | ')}`);
      if(item.source)lines.push('Source correctif: '+[item.source.repository,item.source.file+(item.source.line?':'+item.source.line:''),item.source.function?'fonction '+item.source.function:'',item.source.sourceCommit?'commit '+String(item.source.sourceCommit).slice(0,12):''].filter(Boolean).join(' · '));
      lines.push('Appliqué: NON');
    }
    lines.push('', 'MODE: OBSERVATEUR / LECTURE SEULE', 'AUCUN CORRECTIF APPLIQUÉ PAR SENTINEL. Toute proposition nécessite une deuxième validation manuelle.');"""
    client=replace_once(client,old,new,'repair report text')

WORKER.write_text(worker,encoding='utf-8')
CLIENT.write_text(client,encoding='utf-8')
print('WFGG_SENTINEL_PRESCRIPTIVE_V12=PATCHED')
