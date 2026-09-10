import fs from 'node:fs';
import crypto from 'node:crypto';

const APP='frontend/train-native/app.v15.js';
const APP_SHA='frontend/train-native/app.v15.js.sha256';
const PORTAL='frontend/app.js';
const WORKER='frontend/_worker.js';
const PUSH_SW='frontend/train-native/wfgg-push-sw.js';

function replaceOnce(src, oldText, newText, label){
  if(src.includes(newText)) return src;
  if(!src.includes(oldText)) throw new Error(`${label}: anchor not found`);
  return src.replace(oldText,newText);
}

let portal=fs.readFileSync(PORTAL,'utf8');
portal=replaceOnce(portal,
"  const STORAGE_TOKEN = 'wfgg_portal_session';\n",
"  const STORAGE_TOKEN = 'wfgg_portal_session';\n  const SESSION_COOKIE = 'wfgg_portal_session';\n\n  function writeSessionCookie(token) {\n    if (!token) return;\n    document.cookie = `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; Max-Age=2592000; Secure; SameSite=Strict`;\n  }\n\n  function clearSessionCookie() {\n    document.cookie = `${SESSION_COOKIE}=; Path=/; Max-Age=0; Secure; SameSite=Strict`;\n  }\n",
'portal cookie helpers');
portal=replaceOnce(portal,
"  function clearSession() {\n    localStorage.removeItem(STORAGE_TOKEN);\n",
"  function clearSession() {\n    localStorage.removeItem(STORAGE_TOKEN);\n    clearSessionCookie();\n",
'portal logout cookie');
portal=replaceOnce(portal,
"      hydrate(await api('/api/me'));\n      showPortal();\n",
"      hydrate(await api('/api/me'));\n      writeSessionCookie(localStorage.getItem(STORAGE_TOKEN));\n      showPortal();\n",
'portal boot cookie');
portal=replaceOnce(portal,
"      localStorage.setItem(STORAGE_TOKEN, data.session_token);\n      hydrate(data);\n",
"      localStorage.setItem(STORAGE_TOKEN, data.session_token);\n      writeSessionCookie(data.session_token);\n      hydrate(data);\n",
'portal login cookie');
fs.writeFileSync(PORTAL,portal);

let worker=fs.readFileSync(WORKER,'utf8');
const guardHelpers=`\n/* WFGG_PORTAL_ONLY_MODULE_GUARD_V4\n   Les modules sont servis uniquement à une session Portail valide. Le cookie\n   transporte le même jeton déjà stocké côté Portail afin que le Worker puisse\n   valider une navigation directe avant de livrer l'application. */\nfunction portalSessionCookie(request) {\n  const cookie = request.headers.get('Cookie') || '';\n  const match = cookie.match(/(?:^|;\\s*)wfgg_portal_session=([^;]+)/);\n  if (!match) return '';\n  try { return decodeURIComponent(match[1]); } catch { return ''; }\n}\n\nfunction protectedModulePath(pathname) {\n  return pathname === '/train' || pathname.startsWith('/train/') ||\n    pathname === '/guides' || pathname.startsWith('/guides/') ||\n    pathname === '/simulateur' || pathname.startsWith('/simulateur/');\n}\n\nfunction moduleRequestNeedsValidation(request, pathname) {\n  if (!protectedModulePath(pathname)) return false;\n  const dest = request.headers.get('Sec-Fetch-Dest') || '';\n  const accept = request.headers.get('Accept') || '';\n  if (dest === 'document' || /text\\/html/i.test(accept)) return true;\n  const leaf = pathname.split('/').pop() || '';\n  return !/\\.[a-z0-9]{1,8}$/i.test(leaf) || /\\.html?$/i.test(leaf);\n}\n\nasync function portalSessionValid(request) {\n  const token = portalSessionCookie(request);\n  if (!token) return false;\n  try {\n    const response = await fetch(UPSTREAMS.portalApi.origin + '/api/me', {\n      method: 'GET',\n      headers: { 'Authorization': 'Bearer ' + token, 'Accept': 'application/json' }\n    });\n    return response.ok;\n  } catch { return false; }\n}\n\nfunction portalLoginRedirect(request) {\n  const incoming = new URL(request.url);\n  const target = new URL('/', incoming.origin);\n  target.searchParams.set('returnTo', incoming.pathname + incoming.search);\n  return Response.redirect(target.toString(), 302);\n}\n`;
worker=replaceOnce(worker,
"function upstreamRequest(request, targetUrl, options = {}) {",
guardHelpers+"\nfunction upstreamRequest(request, targetUrl, options = {}) {",
'worker guard helpers');
worker=replaceOnce(worker,
"    const url = new URL(request.url);\n\n    try {\n",
"    const url = new URL(request.url);\n\n    if (protectedModulePath(url.pathname)) {\n      const token = portalSessionCookie(request);\n      if (!token) return portalLoginRedirect(request);\n      if (moduleRequestNeedsValidation(request, url.pathname)) {\n        const valid = await portalSessionValid(request);\n        if (!valid) return portalLoginRedirect(request);\n      }\n    }\n\n    try {\n",
'worker protected route enforcement');
worker=worker.replaceAll('wfgg_bridge=v15&wfgg_ui=clean1','wfgg_bridge=v15&wfgg_ui=clean1&wfgg_auth=v4&wfgg_push=v15');
fs.writeFileSync(WORKER,worker);

let app=fs.readFileSync(APP,'utf8');
const bootPattern=/        \/\* WFGG_PORTAL_DIRECT_TRAIN_BOOTSTRAP_V2[\s\S]*?        \} else \{\n          showPortal\(\);\n        \}/;
if(!bootPattern.test(app)) throw new Error('Train bootstrap V2 block not found');
const bootReplacement=`        /* WFGG_PORTAL_ONLY_TRAIN_BOOT_V4\n           Un cache Train local ne constitue jamais une authentification. Sous\n           /train/, le snapshot Portail doit être revalidé à chaque ouverture. */\n        if (location.pathname === '/train' || location.pathname.startsWith('/train/')) {\n          try {\n            const refreshed = await syncSnapshot({ render: false, quiet: true });\n            const ready = !!(refreshed && state.currentUserId && user());\n            if (!ready) throw new Error('snapshot_without_identity');\n            console.info('WFGG_PORTAL_ONLY_TRAIN_BOOT_V4=READY');\n            bootApp();\n          } catch (e) {\n            console.error('WFGG_PORTAL_ONLY_TRAIN_BOOT_V4=REJECTED', String(e && e.message || e));\n            state.currentUserId = null;\n            saveState();\n            const returnTo = encodeURIComponent(location.pathname + location.search);\n            location.replace('/?returnTo=' + returnTo);\n          }\n        } else {\n          showPortal();\n        }`;
app=app.replace(bootPattern,bootReplacement);

const enablePattern=/    async function enablePushNotifications\(\)\{[\s\S]*?\n    \}\n    async function disablePushNotifications\(\)\{/;
if(!enablePattern.test(app)) throw new Error('enablePushNotifications block not found');
const enableReplacement=`    /* WFGG_PUSH_TRANSACTIONAL_ONBOARDING_V15\n       Aucun abonnement Push serveur n'est créé avant confirmation de l'affichage\n       réel sur cet appareil. Un abandon laisse l'interrupteur gris. */\n    const PUSH_ONBOARDING_PENDING_KEY='wfgg_push_onboarding_pending_v15';\n\n    async function askPushOnboardingVisible(reg){\n        const tag='wfgg-push-onboarding-'+Date.now();\n        await reg.showNotification('WfGg Train',{\n            body:pushText('Notification de confirmation WfGg.','WfGg confirmation notification.','Notifica di conferma WfGg.','Notificación de confirmación WfGg.'),\n            icon:'/assets/wfgg-logo-premium-transparent-v2.png',\n            badge:'/assets/wfgg-logo-mini.svg',\n            tag,\n            data:{url:'/train/'}\n        });\n        await new Promise(r=>setTimeout(r,350));\n        const created=await reg.getNotifications({tag});\n        if(!created.length)return false;\n        return new Promise(resolve=>{\n            openModal(\`<h2>🔔 \${pushText('As-tu reçu la notification WfGg ?','Did you receive the WfGg notification?','Hai ricevuto la notifica WfGg?','¿Has recibido la notificación WfGg?')}</h2><p>\${pushText('Nous ne créerons l’abonnement Push qu’après ta confirmation.','We will create the Push subscription only after your confirmation.','Creeremo l’abbonamento Push solo dopo la tua conferma.','Solo crearemos la suscripción Push después de tu confirmación.')}</p><div class="actions"><button id="wfggPushOnboardingYes" class="btn success">✅ \${pushText('Oui','Yes','Sì','Sí')}</button><button id="wfggPushOnboardingNo" class="btn danger">❌ \${pushText('Non','No','No','No')}</button></div>\`);\n            queueMicrotask(()=>{\n                document.getElementById('wfggPushOnboardingYes')?.addEventListener('click',()=>{created.forEach(n=>n.close());closeModal();resolve(true);});\n                document.getElementById('wfggPushOnboardingNo')?.addEventListener('click',()=>{created.forEach(n=>n.close());closeModal();resolve(false);});\n            });\n        });\n    }\n\n    function cancelPushOnboarding(){\n        sessionStorage.removeItem(PUSH_ONBOARDING_PENDING_KEY);\n        closeModal();\n        refreshPushUi().catch(()=>{});\n    }\n\n    function promptPushOnboardingSettings(){\n        sessionStorage.setItem(PUSH_ONBOARDING_PENDING_KEY,'1');\n        const modify=notificationSettingsModifyMarkup(notificationSettingsText('Modifier les réglages','Change settings','Modifica impostazioni','Cambiar ajustes'));\n        openModal(\`<h2>🔔 \${pushText('Autoriser l’affichage des notifications','Allow notification display','Consenti la visualizzazione delle notifiche','Permitir la visualización de notificaciones')}</h2><p>\${pushText('La notification de confirmation n’est pas apparue. Tu peux corriger les réglages du téléphone maintenant. Si tu ne le souhaites pas, les notifications resteront désactivées.','The confirmation notification did not appear. You can fix the phone settings now. If you do not want to, notifications will remain disabled.','La notifica di conferma non è apparsa. Puoi correggere ora le impostazioni del telefono. Se non vuoi, le notifiche resteranno disattivate.','La notificación de confirmación no apareció. Puedes corregir ahora los ajustes del teléfono. Si no quieres, las notificaciones seguirán desactivadas.')}</p><div class="actions">\${modify}<button id="wfggPushOnboardingCancel" class="btn outline">\${pushText('Pas maintenant','Not now','Non ora','Ahora no')}</button></div>\`);\n        queueMicrotask(()=>{\n            wireNotificationSettingsModify();\n            document.getElementById('wfggPushOnboardingCancel')?.addEventListener('click',cancelPushOnboarding);\n        });\n    }\n\n    async function finalizePushSubscription(reg){\n        const key=await api('/api/push/public-key',{method:'GET'});\n        let sub=await reg.pushManager.getSubscription();\n        if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:pushKeyBytes(key.publicKey)});\n        await api('/api/push/subscribe',{method:'POST',body:JSON.stringify({subscription:sub.toJSON(),userAgent:navigator.userAgent||'',platform:pushPlatform()})});\n        sessionStorage.removeItem(PUSH_ONBOARDING_PENDING_KEY);\n        await syncSnapshot({render:false,quiet:true});\n        toast(pushText('Notifications activées','Notifications enabled','Notifiche attivate','Notificaciones activadas'));\n        renderHome();renderAlerts();\n        return true;\n    }\n\n    async function continuePushOnboardingAfterSettings(){\n        if(Notification.permission!=='granted'){cancelPushOnboarding();return false;}\n        try{\n            const reg=await ensurePushRegistration();\n            const visible=await askPushOnboardingVisible(reg);\n            if(!visible){promptPushOnboardingSettings();return false;}\n            return await finalizePushSubscription(reg);\n        }catch(e){toast(e.message||String(e));cancelPushOnboarding();return false;}\n    }\n\n    async function enablePushNotifications(){\n        if(isAppleMobile()&&!isStandaloneApp()){pushInstallHelp();return false;}\n        if(!pushFeatureSupported()){toast(pushText('Notifications non prises en charge','Notifications not supported','Notifiche non supportate','Notificaciones no compatibles'));return false;}\n        if(Notification.permission==='denied'){promptPushOnboardingSettings();await refreshPushUi();return false;}\n        const permission=Notification.permission==='granted'?'granted':await Notification.requestPermission();\n        if(permission!=='granted'){sessionStorage.removeItem(PUSH_ONBOARDING_PENDING_KEY);await refreshPushUi();return false;}\n        try{\n            const reg=await ensurePushRegistration();\n            const visible=await askPushOnboardingVisible(reg);\n            if(!visible){promptPushOnboardingSettings();await refreshPushUi();return false;}\n            return await finalizePushSubscription(reg);\n        }catch(e){toast(e.message||String(e));cancelPushOnboarding();return false;}\n    }\n    async function disablePushNotifications(){`;
app=app.replace(enablePattern,enableReplacement);

const returnAnchor="                notificationSettingsOutcomeWrite('auto-recheck','returned-from-android-settings');\n                toast(notificationSettingsText('Réglages repris. Nouveau test d’affichage…','Settings resumed. Testing display again…','Impostazioni riprese. Nuovo test di visualizzazione…','Ajustes retomados. Nueva prueba de visualización…'));\n                await testLocalNotification();";
const returnReplacement="                notificationSettingsOutcomeWrite('auto-recheck','returned-from-android-settings');\n                if(sessionStorage.getItem(PUSH_ONBOARDING_PENDING_KEY)==='1'){\n                    toast(notificationSettingsText('Réglages repris. Vérification de l’affichage…','Settings resumed. Checking display…','Impostazioni riprese. Verifica visualizzazione…','Ajustes retomados. Comprobando visualización…'));\n                    await continuePushOnboardingAfterSettings();\n                }else{\n                    toast(notificationSettingsText('Réglages repris. Nouveau test d’affichage…','Settings resumed. Testing display again…','Impostazioni riprese. Nuovo test di visualizzazione…','Ajustes retomados. Nueva prueba de visualización…'));\n                    await testLocalNotification();\n                }";
app=replaceOnce(app,returnAnchor,returnReplacement,'settings return onboarding');
fs.writeFileSync(APP,app);
const digest=crypto.createHash('sha256').update(fs.readFileSync(APP)).digest('hex');
fs.writeFileSync(APP_SHA,`${digest}  app.v15.js\n`);

let sw=fs.readFileSync(PUSH_SW,'utf8');
sw=sw.replaceAll("icon: '/train/assets/icon-192.png',","icon: '/assets/wfgg-logo-premium-transparent-v2.png',\n    badge: '/assets/wfgg-logo-mini.svg',");
if(!sw.includes("badge: '/assets/wfgg-logo-mini.svg'")) throw new Error('Push badge not applied');
fs.writeFileSync(PUSH_SW,sw);

console.log('WFGG_PORTAL_ONLY_MODULE_GUARD_V4=PATCHED');
console.log('WFGG_PUSH_TRANSACTIONAL_ONBOARDING_V15=PATCHED');
console.log('WFGG_PUSH_WFGG_BADGE_V1=PATCHED');
