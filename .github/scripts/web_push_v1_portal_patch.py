from pathlib import Path

# ---------- native Train runtime ----------
p=Path('frontend/train-native/app.v15.js')
s=p.read_text(encoding='utf-8')

if 'WFGG_WEB_PUSH_CLIENT_V1' not in s:
    anchor='    function renderAlerts() {'
    if anchor not in s: raise SystemExit('renderAlerts anchor missing')
    helper=r'''    /* WFGG_WEB_PUSH_CLIENT_V1
       Web Push standard : Android directement ; iOS/iPadOS depuis la Web App
       ajoutée à l’écran d’accueil. La permission n’est demandée qu’après le
       geste explicite de l’utilisateur. */
    let pushDeviceState={checking:false,local:false,total:0,permission:'default'};
    function pushText(fr,en,it,es){
        const lang=currentLanguage();
        return lang==='en'?en:lang==='it'?it:lang==='es'?es:fr;
    }
    function isAppleMobile(){
        const ua=navigator.userAgent||'';
        return /iPhone|iPad|iPod/i.test(ua)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
    }
    function pushFeatureSupported(){
        return 'serviceWorker' in navigator&&'PushManager' in window&&'Notification' in window;
    }
    function pushPlatform(){return isAppleMobile()?'ios':/Android/i.test(navigator.userAgent||'')?'android':'web';}
    function pushKeyBytes(value){
        const pad='='.repeat((4-value.length%4)%4),b64=(value+pad).replace(/-/g,'+').replace(/_/g,'/');
        const raw=atob(b64),out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out;
    }
    async function ensurePushRegistration(){
        if(!('serviceWorker' in navigator))throw new Error(pushText('Service Worker indisponible','Service Worker unavailable','Service Worker non disponibile','Service Worker no disponible'));
        return navigator.serviceWorker.register('/train/wfgg-push-sw.js',{scope:'/train/'});
    }
    async function localPushSubscription(){
        if(!pushFeatureSupported())return null;
        const reg=await navigator.serviceWorker.getRegistration('/train/');
        return reg?reg.pushManager.getSubscription():null;
    }
    function pushInstallHelp(){
        openModal(`<h2>📲 ${pushText('Activer les notifications sur iPhone / iPad','Enable notifications on iPhone / iPad','Attivare le notifiche su iPhone / iPad','Activar notificaciones en iPhone / iPad')}</h2>
          <div class="warning">${pushText(
            'Sur iOS/iPadOS, ajoute d’abord WfGg à l’écran d’accueil, puis ouvre WfGg depuis son icône et active les rappels.',
            'On iOS/iPadOS, first add WfGg to the Home Screen, then open WfGg from its icon and enable reminders.',
            'Su iOS/iPadOS, aggiungi prima WfGg alla schermata Home, poi aprilo dalla sua icona e attiva i promemoria.',
            'En iOS/iPadOS, primero añade WfGg a la pantalla de inicio, luego ábrelo desde su icono y activa los recordatorios.'
          )}</div>
          <p>${pushText('Safari : bouton Partager → Ajouter à l’écran d’accueil.','Safari: Share → Add to Home Screen.','Safari: Condividi → Aggiungi alla schermata Home.','Safari: Compartir → Añadir a pantalla de inicio.')}</p>
          <button class="btn gold full" onclick="W.closeModal()">OK</button>`);
    }
    async function refreshPushUi(){
        const btn=document.getElementById('pushToggle'),detail=document.getElementById('pushDeviceDetail'),test=document.getElementById('pushTestButton');
        if(!btn||!detail)return;
        pushDeviceState.checking=true;btn.disabled=true;
        try{
            let local=false,total=0,enabled=false;
            if(pushFeatureSupported())local=!!(await localPushSubscription());
            try{
                const status=await api('/api/push/status',{method:'GET'});
                total=Number(status.subscriptions||0);enabled=!!status.enabled;
            }catch(_){}
            pushDeviceState={checking:false,local,total,permission:('Notification' in window?Notification.permission:'unsupported')};
            btn.disabled=false;btn.classList.toggle('on',local);
            if(test)test.classList.toggle('hidden',!local);
            if(isAppleMobile()&&!isStandaloneApp()){
                detail.textContent=pushText('iPhone/iPad : ajoute WfGg à l’écran d’accueil pour activer les notifications.','iPhone/iPad: add WfGg to the Home Screen to enable notifications.','iPhone/iPad: aggiungi WfGg alla schermata Home per attivare le notifiche.','iPhone/iPad: añade WfGg a la pantalla de inicio para activar las notificaciones.');
            }else if(!pushFeatureSupported()){
                detail.textContent=pushText('Ce navigateur ne prend pas en charge les notifications Web Push.','This browser does not support Web Push notifications.','Questo browser non supporta le notifiche Web Push.','Este navegador no admite notificaciones Web Push.');
            }else if(Notification.permission==='denied'){
                detail.textContent=pushText('Notifications bloquées dans les réglages du téléphone/navigateur.','Notifications are blocked in phone/browser settings.','Notifiche bloccate nelle impostazioni del telefono/browser.','Notificaciones bloqueadas en los ajustes del teléfono/navegador.');
            }else if(local){
                detail.textContent=pushText(`Notifications actives sur cet appareil · ${total} appareil(s) abonné(s).`,`Notifications active on this device · ${total} subscribed device(s).`,`Notifiche attive su questo dispositivo · ${total} dispositivo/i registrato/i.`,`Notificaciones activas en este dispositivo · ${total} dispositivo(s) suscrito(s).`);
            }else if(enabled&&total>0){
                detail.textContent=pushText(`Cet appareil n’est pas abonné · ${total} autre(s) appareil(s) actif(s).`,`This device is not subscribed · ${total} other active device(s).`,`Questo dispositivo non è registrato · ${total} altro/i dispositivo/i attivo/i.`,`Este dispositivo no está suscrito · ${total} otro(s) dispositivo(s) activo(s).`);
            }else{
                detail.textContent=pushText('Notifications non activées sur cet appareil.','Notifications are not enabled on this device.','Notifiche non attive su questo dispositivo.','Notificaciones no activadas en este dispositivo.');
            }
        }catch(e){
            pushDeviceState.checking=false;btn.disabled=false;detail.textContent=e.message||String(e);
        }
    }
    async function enablePushNotifications(){
        if(isAppleMobile()&&!isStandaloneApp()){pushInstallHelp();return false;}
        if(!pushFeatureSupported()){toast(pushText('Notifications non prises en charge','Notifications not supported','Notifiche non supportate','Notificaciones no compatibles'));return false;}
        if(Notification.permission==='denied'){toast(pushText('Autorise les notifications dans les réglages du téléphone','Allow notifications in your phone settings','Consenti le notifiche nelle impostazioni del telefono','Permite las notificaciones en los ajustes del teléfono'));return false;}
        const permission=Notification.permission==='granted'?'granted':await Notification.requestPermission();
        if(permission!=='granted'){await refreshPushUi();return false;}
        try{
            const reg=await ensurePushRegistration();
            const key=await api('/api/push/public-key',{method:'GET'});
            let sub=await reg.pushManager.getSubscription();
            if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:pushKeyBytes(key.publicKey)});
            await api('/api/push/subscribe',{method:'POST',body:JSON.stringify({subscription:sub.toJSON(),userAgent:navigator.userAgent||'',platform:pushPlatform()})});
            await syncSnapshot({render:false,quiet:true});
            toast(pushText('Notifications activées','Notifications enabled','Notifiche attivate','Notificaciones activadas'));
            renderHome();renderAlerts();return true;
        }catch(e){toast(e.message||String(e));await refreshPushUi();return false;}
    }
    async function disablePushNotifications(){
        try{
            const sub=await localPushSubscription();
            if(sub){
                await api('/api/push/subscription',{method:'DELETE',body:JSON.stringify({endpoint:sub.endpoint})});
                await sub.unsubscribe();
            }
            await syncSnapshot({render:false,quiet:true});
            toast(pushText('Notifications désactivées sur cet appareil','Notifications disabled on this device','Notifiche disattivate su questo dispositivo','Notificaciones desactivadas en este dispositivo'));
            renderHome();renderAlerts();return true;
        }catch(e){toast(e.message||String(e));await refreshPushUi();return false;}
    }
    async function testLocalPushNotification(){
        if(Notification.permission!=='granted')return toast(pushText('Notifications non autorisées','Notifications not allowed','Notifiche non autorizzate','Notificaciones no autorizadas'));
        try{
            const reg=await ensurePushRegistration();
            await reg.showNotification('WfGg Train · test',{body:pushText('Les notifications fonctionnent sur cet appareil.','Notifications work on this device.','Le notifiche funzionano su questo dispositivo.','Las notificaciones funcionan en este dispositivo.'),icon:'/train/assets/icon-192.png',tag:'wfgg-train-test',data:{url:'/train/'}});
        }catch(e){toast(e.message||String(e));}
    }
'''
    s=s.replace(anchor,helper+anchor,1)

# Replace alerts renderer with device-aware UI.
start=s.index('    function renderAlerts() {')
end=s.index('    function rotationEquityHtml()',start)
new_render=r'''    function renderAlerts() {
        const el = document.getElementById('alertsScreen'), m = user();
        if (!el || !m) return;
        el.innerHTML = `<div class="section-title"><h2>🔔 Alertes & calendrier</h2></div>
  <div class="alert-card"><div class="toggle-row"><div><h3>${pushText('Notifications téléphone','Phone notifications','Notifiche telefono','Notificaciones del teléfono')}</h3><p>${pushText(`J-1 à ${state.settings.trainTime}, puis 30 minutes avant le départ.`,`1 day before at ${state.settings.trainTime}, then 30 minutes before departure.`,`1 giorno prima alle ${state.settings.trainTime}, poi 30 minuti prima della partenza.`,`1 día antes a las ${state.settings.trainTime}, y 30 minutos antes de la salida.`)}</p></div><button id="pushToggle" class="toggle" disabled onclick="W.toggleAlerts()"><i></i></button></div><div id="pushDeviceDetail" class="warning">${pushText('Vérification de cet appareil…','Checking this device…','Verifica del dispositivo…','Comprobando este dispositivo…')}</div><button id="pushTestButton" class="btn outline full hidden" onclick="W.testLocalPushNotification()">🔔 ${pushText('Tester une notification','Test a notification','Prova una notifica','Probar una notificación')}</button></div>
  <div class="alert-card"><h3>📅 ${pushText('Calendrier (optionnel)','Calendar (optional)','Calendario (opzionale)','Calendario (opcional)')}</h3><p>${pushText('Tu peux aussi ajouter tes prochains passages au calendrier du téléphone.','You can also add your upcoming turns to the phone calendar.','Puoi anche aggiungere i prossimi turni al calendario del telefono.','También puedes añadir tus próximos turnos al calendario del teléfono.')}</p><button class="btn gold full" onclick="W.addAllCalendar()">Ajouter mes passages au calendrier</button></div>
  <div class="alert-card"><h3>🕗 Heure du train</h3><p>Heure actuelle : <strong>${state.settings.trainTime}</strong>. Elle est modifiable par les R4/R5.</p></div>`;
        queueMicrotask(()=>refreshPushUi());
    }
'''
s=s[:start]+new_render+s[end:]

# Replace legacy flag-only toggle.
old="""    async function toggleAlerts() {\n        const id = user().id, next = !state.alertsEnabled[id];\n        await mutate('/api/me/preferences', { method: 'PUT', body: JSON.stringify({ alertsEnabled: next }) }, next ? 'Alertes activées' : 'Alertes désactivées');\n    }\n"""
new="""    async function toggleAlerts() {\n        if(pushDeviceState.checking)return;\n        if(pushDeviceState.local)return disablePushNotifications();\n        return enablePushNotifications();\n    }\n"""
if old not in s: raise SystemExit('legacy toggleAlerts not found')
s=s.replace(old,new,1)

# Keep the dedicated Push SW up to date whenever Train starts.
marker='        /* WFGG_TRAIN_PROXY_NO_SERVICE_WORKER_V1 */'
if marker not in s: raise SystemExit('service worker marker missing')
s=s.replace(marker,"""        /* WFGG_WEB_PUSH_SW_REGISTER_V1 */\n        if ('serviceWorker' in navigator) {\n            navigator.serviceWorker.register('/train/wfgg-push-sw.js',{scope:'/train/'}).catch(()=>{});\n        }""",1)

# Expose local notification test to the inline UI button.
export_old='addCalendar, addAllCalendar, toggleAlerts, changeWeek'
export_new='addCalendar, addAllCalendar, toggleAlerts, testLocalPushNotification, changeWeek'
if export_new not in s:
    if export_old not in s: raise SystemExit('window.W export anchor missing')
    s=s.replace(export_old,export_new,1)

p.write_text(s,encoding='utf-8')

# ---------- Portal Worker ----------
p=Path('frontend/_worker.js')
w=p.read_text(encoding='utf-8')

# Preserve the new push SW while removing the legacy cache SW.
legacy="""              .filter(registration=>{\n                try{\n                  return new URL(registration.scope).pathname.startsWith('/train/');\n                }catch(_){return false;}\n              })\n              .map(registration=>registration.unregister())"""
fixed="""              .filter(registration=>{\n                try{\n                  const scopePath=new URL(registration.scope).pathname;\n                  const script=registration.active?.scriptURL||registration.waiting?.scriptURL||registration.installing?.scriptURL||'';\n                  const scriptPath=script?new URL(script).pathname:'';\n                  return scopePath.startsWith('/train/') && scriptPath!=='/train/wfgg-push-sw.js';\n                }catch(_){return false;}\n              })\n              .map(registration=>registration.unregister())"""
if 'WFGG_WEB_PUSH_SW_PRESERVE_V1' not in w:
    if legacy not in w: raise SystemExit('legacy SW reset filter missing')
    w=w.replace(legacy,"              /* WFGG_WEB_PUSH_SW_PRESERVE_V1 */\n"+fixed,1)

# Serve push SW + manifest from the Portal origin.
route_anchor="""  /* WFGG_TRAIN_NATIVE_APP_V15_SHADOW\n     Première étape de consolidation : sur la branche native v15, app.js est\n     servi depuis une capture vérifiée du bridge v14 réellement déployé."""
if 'WFGG_TRAIN_PUSH_STATIC_V1' not in w:
    if route_anchor not in w: raise SystemExit('routeTrain native anchor missing')
    static_block="""  /* WFGG_TRAIN_PUSH_STATIC_V1\n     Le Service Worker Push doit être servi par wfgg.pages.dev sous /train/\n     pour posséder exactement le même origin et le bon scope sur Android/iOS. */\n  if (suffix === '/wfgg-push-sw.js' || suffix === '/manifest.webmanifest') {\n    const assetUrl = new URL(request.url);\n    assetUrl.pathname = '/train-native' + suffix;\n    assetUrl.search = '';\n    const assetResponse = await env.ASSETS.fetch(new Request(assetUrl.toString(), {method:'GET',headers:request.headers}));\n    if (assetResponse.ok) {\n      const headers = new Headers(assetResponse.headers);\n      headers.set('Cache-Control', suffix.endsWith('.js') ? 'no-store' : 'public, max-age=300');\n      if (suffix.endsWith('.js')) headers.set('Content-Type','application/javascript; charset=utf-8');\n      if (suffix.endsWith('.webmanifest')) headers.set('Content-Type','application/manifest+json; charset=utf-8');\n      return new Response(assetResponse.body,{status:assetResponse.status,statusText:assetResponse.statusText,headers});\n    }\n  }\n\n"""
    w=w.replace(route_anchor,static_block+route_anchor,1)

# Inject manifest + iOS standalone metadata into Train HTML only.
head_old="""        let html = languageBridgeScript(options.routeName || route.prefix.slice(1));\n        if (options.baseHref) {"""
head_new="""        let html = languageBridgeScript(options.routeName || route.prefix.slice(1));\n        if (options.routeName === 'train') {\n          html = '<link rel=\"manifest\" href=\"/train/manifest.webmanifest\"><meta name=\"apple-mobile-web-app-capable\" content=\"yes\"><meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\"><meta name=\"theme-color\" content=\"#00182b\">' + html;\n        }\n        if (options.baseHref) {"""
if 'manifest.webmanifest' not in w:
    if head_old not in w: raise SystemExit('HTML head injection anchor missing')
    w=w.replace(head_old,head_new,1)

p.write_text(w,encoding='utf-8')
print('Web Push v1 Portal patch applied')
