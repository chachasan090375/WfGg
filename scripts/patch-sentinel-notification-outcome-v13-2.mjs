import fs from 'node:fs';
import crypto from 'node:crypto';

const appPath='frontend/train-native/app.v15.js';
const sentinelPath='frontend/train-native/sentinel-train-v1.js';
const shaPath='frontend/train-native/app.v15.js.sha256';
let app=fs.readFileSync(appPath,'utf8');
let sentinel=fs.readFileSync(sentinelPath,'utf8');

function replaceOne(source, oldText, newText, label){
  const first=source.indexOf(oldText);
  if(first<0) throw new Error(`missing anchor: ${label}`);
  if(source.indexOf(oldText, first+oldText.length)>=0) throw new Error(`duplicate anchor: ${label}`);
  return source.slice(0,first)+newText+source.slice(first+oldText.length);
}

app=replaceOne(app,
`    function notificationSettingsIntentPlan(){
        const android=/Android/i.test(navigator.userAgent||'');
        const ua=navigator.userAgent||'';
        const packageName=/SamsungBrowser/i.test(ua)?'com.sec.android.app.sbrowser':'com.android.chrome';
        const fallback=new URL(location.href);
        fallback.searchParams.set('wfgg_notification_settings_fallback','1');
        const appNotifications=\`intent:#Intent;action=android.settings.APP_NOTIFICATION_SETTINGS;package=com.android.settings;S.android.provider.extra.APP_PACKAGE=\${packageName};S.browser_fallback_url=\${encodeURIComponent(fallback.toString())};end\`;
        return {android,packageName,appNotifications,fallbackUrl:fallback.toString()};
    }`,
`    /* WFGG_NOTIFICATION_SETTINGS_OUTCOME_V13_2
       Le navigateur peut refuser une activité Android non BROWSABLE même si le href
       intent: est valide. On distingue donc le câblage théorique du résultat réel du
       dernier geste utilisateur sur cet appareil. Aucun résultat n'est inventé. */
    const NOTIFICATION_SETTINGS_OUTCOME_KEY='wfgg_notification_settings_outcome_v13_2';
    function notificationSettingsOutcomeRead(){
        try{return JSON.parse(localStorage.getItem(NOTIFICATION_SETTINGS_OUTCOME_KEY)||'null')||null;}catch(_){return null;}
    }
    function notificationSettingsOutcomeWrite(status,detail=''){
        try{
            const value={status:String(status||''),detail:String(detail||''),at:new Date().toISOString()};
            localStorage.setItem(NOTIFICATION_SETTINGS_OUTCOME_KEY,JSON.stringify(value));
            return value;
        }catch(_){return null;}
    }
    function notificationSettingsIntentPlan(){
        const android=/Android/i.test(navigator.userAgent||'');
        const ua=navigator.userAgent||'';
        const packageName=/SamsungBrowser/i.test(ua)?'com.sec.android.app.sbrowser':'com.android.chrome';
        const fallback=new URL(location.href);
        fallback.searchParams.set('wfgg_notification_settings_fallback','1');
        // Laisser Android résoudre Settings est plus compatible que forcer package=com.android.settings.
        const appNotifications=\`intent:#Intent;action=android.settings.APP_NOTIFICATION_SETTINGS;S.android.provider.extra.APP_PACKAGE=\${packageName};S.browser_fallback_url=\${encodeURIComponent(fallback.toString())};end\`;
        return {android,packageName,appNotifications,fallbackUrl:fallback.toString(),lastOutcome:notificationSettingsOutcomeRead()};
    }`,
'notificationSettingsIntentPlan');

app=replaceOne(app,
`    function wireNotificationSettingsModify(){
        const el=document.getElementById('wfggNotifModify');
        if(!el)return;
        if(el.tagName==='A'){
            el.addEventListener('click',()=>sessionStorage.setItem('wfgg_notification_settings_return','1'));
        }else{
            el.addEventListener('click',openNotificationSystemSettings);
        }
    }`,
`    function wireNotificationSettingsModify(){
        const el=document.getElementById('wfggNotifModify');
        if(!el)return;
        if(el.tagName==='A'){
            el.addEventListener('click',()=>{
                sessionStorage.setItem('wfgg_notification_settings_return','1');
                notificationSettingsOutcomeWrite('attempted','intent-click');
            });
        }else{
            el.addEventListener('click',openNotificationSystemSettings);
        }
    }`,
'wireNotificationSettingsModify');

app=replaceOne(app,
`    function notificationSettingsFallback(){
        openModal(`,
`    function notificationSettingsFallback(){
        notificationSettingsOutcomeWrite('fallback','browser_fallback_url');
        openModal(`,
'notificationSettingsFallback outcome');

app=replaceOne(app,
`    document.addEventListener('visibilitychange',()=>{
        if(document.visibilityState!=='visible'||sessionStorage.getItem('wfgg_notification_settings_return')!=='1')return;
        sessionStorage.removeItem('wfgg_notification_settings_return');`,
`    document.addEventListener('visibilitychange',()=>{
        if(document.visibilityState==='hidden'&&sessionStorage.getItem('wfgg_notification_settings_return')==='1'){
            notificationSettingsOutcomeWrite('external-opened','document-hidden-after-intent');
            return;
        }
        if(document.visibilityState!=='visible'||sessionStorage.getItem('wfgg_notification_settings_return')!=='1')return;
        sessionStorage.removeItem('wfgg_notification_settings_return');
        const lastSettingsOutcome=notificationSettingsOutcomeRead();
        if(lastSettingsOutcome?.status==='external-opened') notificationSettingsOutcomeWrite('returned','document-visible-after-external');`,
'notification settings visibility outcome');

sentinel=replaceOne(sentinel,
`  const VERSION = 'sentinel-train-v13';`,
`  const VERSION = 'sentinel-train-v13.2';`,
'sentinel version');

sentinel=replaceOne(sentinel,
`    const settingsPlan=uiProbe?.notificationSettings;
    const settingsOk=!settingsPlan?.android||(simFailed.every(x=>x.id!=='notification-settings-action')&&String(settingsPlan?.appNotifications||'').includes('browser_fallback_url'));
    items.push(localCheck(
      'train-notification-settings-action',settingsOk?'ok':'error','Bouton Modifier les réglages Android',
      'Lien intent direct depuis le geste utilisateur + retour WfGg si Android refuse',settingsPlan?.android?(settingsOk?\`\${settingsPlan.packageName} · intent + fallback câblés\`:'câblage incomplet'):'non Android',
      'Sentinel ne déclenche pas volontairement l’Intent système : il valide le lien réellement rendu et son fallback sans quitter WfGg.',
      settingsOk?'':'Le bouton Modifier peut rester sans effet ou quitter la page sans aide de secours.'
    ));`,
`    const settingsPlan=uiProbe?.notificationSettings;
    const settingsStructuralOk=!settingsPlan?.android||(simFailed.every(x=>x.id!=='notification-settings-action')&&String(settingsPlan?.appNotifications||'').includes('browser_fallback_url'));
    const settingsOutcome=settingsPlan?.lastOutcome||null;
    const settingsOutcomeStatus=String(settingsOutcome?.status||'');
    let settingsLevel='ok';
    let settingsObserved='non Android';
    let settingsDetail='';
    let settingsCause='';
    if(settingsPlan?.android){
      if(!settingsStructuralOk){
        settingsLevel='error';settingsObserved='câblage incomplet';settingsCause='Le lien Android ou son fallback est absent.';
      }else if(settingsOutcomeStatus==='fallback'){
        settingsLevel='warning';settingsObserved=\`\${settingsPlan.packageName} · dernier essai: Intent refusé → guide manuel\`;
        settingsDetail='Le browser_fallback_url a réellement été utilisé sur cet appareil; le raccourci système n’a donc pas ouvert les réglages.';
        settingsCause='Chrome/Android refuse cette activité système depuis le contexte web. Le guide manuel reste fonctionnel.';
      }else if(settingsOutcomeStatus==='external-opened'||settingsOutcomeStatus==='returned'){
        settingsLevel='ok';settingsObserved=\`\${settingsPlan.packageName} · ouverture externe observée\`;
        settingsDetail='Le document WfGg est devenu masqué après le geste utilisateur, puis le retour a été observé si l’utilisateur est revenu.';
      }else if(settingsOutcomeStatus==='attempted'){
        settingsLevel='info';settingsObserved=\`\${settingsPlan.packageName} · essai lancé, résultat non encore observé\`;
        settingsDetail='Sentinel attend soit une sortie réelle de la page, soit le fallback WfGg.';
      }else{
        settingsLevel='info';settingsObserved=\`\${settingsPlan.packageName} · câblé mais pas encore testé réellement depuis V13.2\`;
        settingsDetail='Un vrai appui utilisateur sur Modifier est nécessaire pour qualifier Android/Chrome.';
      }
    }
    items.push(localCheck(
      'train-notification-settings-action',settingsLevel,'Bouton Modifier les réglages Android',
      'Geste réel → ouverture externe des réglages, sinon fallback WfGg explicitement détecté',settingsObserved,
      settingsDetail||'Sur Android, Sentinel sépare désormais le href théorique du résultat réel du dernier clic utilisateur.',
      settingsCause
    ));`,
'sentinel notification settings outcome control');

sentinel=replaceOne(sentinel,
`    if(bad.has('train-notification-settings-action'))out.push(localRepairCandidateV12({
      id:'repair-notification-settings-action-v13',title:'Rétablir le lien Android vers les réglages notifications',score:98,verdict:'recommended',
      target:'app.v15.js :: notificationSettingsIntentPlan',proposedChange:'Rendre un lien intent: directement cliquable avec APP_NOTIFICATION_SETTINGS et browser_fallback_url same-origin.',simulation:{readonly:true,externalIntentNotLaunched:true},evidence:['Sentinel valide le href rendu sans ouvrir les paramètres système.'],risks:['Chrome peut refuser une activité Android non BROWSABLE ; le fallback WfGg doit toujours rester disponible.'],manualValidation:['Appuyer sur Modifier sur Android puis vérifier le retour guidé si Android refuse.']
    }));`,
`    if(bad.has('train-notification-settings-action'))out.push(localRepairCandidateV12({
      id:'repair-notification-settings-action-v13',title:'Adapter le parcours aux restrictions Android/Chrome',score:96,verdict:'recommended',
      target:'app.v15.js :: notificationSettingsIntentPlan / résultat réel',proposedChange:'Conserver un Intent best-effort conforme à APP_NOTIFICATION_SETTINGS, enregistrer son issue réelle et présenter immédiatement le guide manuel si Chrome le refuse.',simulation:{readonly:true,externalIntentNotLaunched:true,outcomeTracked:true},evidence:['Le dernier geste utilisateur est distingué entre ouverture externe, tentative et browser_fallback_url.'],risks:['Une page web ne peut pas forcer une activité système Android non BROWSABLE.'],manualValidation:['Appuyer sur Modifier puis relancer Sentinel après retour ou fallback.']
    }));`,
'sentinel notification repair');

fs.writeFileSync(appPath,app);
fs.writeFileSync(sentinelPath,sentinel);
const digest=crypto.createHash('sha256').update(fs.readFileSync(appPath)).digest('hex');
fs.writeFileSync(shaPath,`${digest}  app.v15.js\n`);
console.log('WFGG_SENTINEL_NOTIFICATION_OUTCOME_V13_2=PATCHED');
