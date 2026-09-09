from pathlib import Path

WORKER=Path('frontend/_worker.js')
CLIENT=Path('frontend/train-native/sentinel-train-v1.js')
worker=WORKER.read_text(encoding='utf-8')
client=CLIENT.read_text(encoding='utf-8')

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'PATCH_MISSING {label}')
    return text.replace(old,new,1)

if 'WFGG_SENTINEL_FUNCTIONAL_COVERAGE_V11' not in worker:
    old="  const diagnosis=await sentinelRunDeepDiagnostics(request,token,meCall,snapCall,checks);"
    new="""  /* WFGG_SENTINEL_FUNCTIONAL_COVERAGE_V11
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

  const diagnosis=await sentinelRunDeepDiagnostics(request,token,meCall,snapCall,checks);"""
    worker=replace_once(worker,old,new,'portal feature audit insertion')

worker=worker.replace("script.src='/train/sentinel-train-v1.js?v=010';","script.src='/train/sentinel-train-v1.js?v=011';")

client=client.replace("const VERSION = 'sentinel-train-v10';","const VERSION = 'sentinel-train-v11';")
client=client.replace('WFGG_SENTINEL_REPORT_V3','WFGG_SENTINEL_REPORT_V4')

if 'train-ui-functional-contract-v11' not in client:
    old="""    return items;
  }

  async function runSentinel() {"""
    new="""    /* train-ui-functional-contract-v11
       Inventaire des actions réellement exposées par app.v15. Sentinel ne les
       déclenche pas : il vérifie que le câblage client de chaque famille existe. */
    const uiFunctions = [
      'addCalendar','addAllCalendar','toggleAlerts','testLocalPushNotification','testPushReminder',
      'changeWeek','openExchange','publishMarketExchange','cancelMarketExchange','pickMyDateForMarket','executeMarketSwap',
      'markUnavailable','showUnavailableChoice','openUnavailableDayPicker','saveUnavailableDayFromPicker','openUnavailablePeriod','saveUnavailablePeriod','saveUnavailableDay','removeUnavailableRange','removeUnavailable','showUnavailable',
      'toggleRotation','showRotationStatus','openProfileInfo','openSelfProfileEdit','saveSelfProfile','openChangePin','changeMyPin','changeLanguage','setPortalLanguage',
      'saveAdminSettings','saveDay','clearDayOverride','adminToggleRotation','filterMembers','searchMembers','openMemberForm','saveMemberForm','deleteMember','renderRotationOrder','moveRotation','saveRotationRanks','resetMemberPin','downloadGeneratedCodesCsv','clearGeneratedCodes',
      'generateMessage','nextMessage','copyGeneratedMessage','openAdminSection','renderAdminHome','togglePresenceList','refreshAdminPresence',
      'openGameHelp','openGameLink','addGameLinkDraft','removeGameLinkDraft','saveGameLinks',
      'openAdminAnalytics','renderAnalyticsMenu','openAnalyticsSub','renderTrainHistory','setAnalyticsRotationDays','setAnalyticsRotationPool','setAnalyticsRotationSort','setAnalyticsActivitySort','setAnalyticsSettingsFilter','setAnalyticsFilter','setAnalyticsHistorySort','setAnalyticsSearch'
    ];
    const missingUi = uiFunctions.filter((name) => typeof window.W?.[name] !== 'function');
    items.push(localCheck(
      'train-ui-functional-contract', missingUi.length ? 'error' : 'ok',
      'Contrat des fonctionnalités de l’interface',
      `${uiFunctions.length} actions Train exposées`,
      missingUi.length ? `${missingUi.length} manquante(s): ${missingUi.slice(0,12).join(', ')}` : `${uiFunctions.length}/${uiFunctions.length} présentes`,
      'Couvre calendrier, alertes, échanges, indisponibilités, statut, profil/PIN/langue, administration, présence, messages, liens et statistiques.',
      missingUi.length ? 'Une fonction visible dans l’interface n’est plus exposée par app.v15.' : ''
    ));
    const calendarRuntime = typeof Blob === 'function' && typeof URL?.createObjectURL === 'function' && typeof window.W?.addCalendar === 'function' && typeof window.W?.addAllCalendar === 'function';
    items.push(localCheck(
      'train-calendar-runtime',calendarRuntime?'ok':'error','Export calendrier téléphone',
      'Blob + URL.createObjectURL + fonctions ICS disponibles',calendarRuntime?'disponible':'incomplet','Test de capacité uniquement; aucun fichier calendrier n’est téléchargé par Sentinel.',
      calendarRuntime?'':'Le navigateur ou le code client ne peut pas produire les fichiers calendrier.'
    ));
    return items;
  }

  async function runSentinel() {"""
    client=replace_once(client,old,new,'client UI contract insertion')

WORKER.write_text(worker,encoding='utf-8')
CLIENT.write_text(client,encoding='utf-8')
print('WFGG_SENTINEL_FUNCTIONAL_COVERAGE_V11=PATCHED')
