from pathlib import Path
import hashlib

app=Path('frontend/train-native/app.v15.js')
s=app.read_text(encoding='utf-8')
old="""    async function testLocalNotification(){
        if(Notification.permission!=='granted')return toast(pushText('Notifications non autorisées','Notifications not allowed','Notifiche non autorizzate','Notificaciones no autorizadas'));
        try{
            const reg=await ensurePushRegistration();
            await navigator.serviceWorker.ready;
            await reg.showNotification('WfGg Train · test local',{
                body:pushText('Si tu vois ce message, l’affichage des notifications fonctionne sur ce téléphone.','If you see this message, notification display works on this phone.','Se vedi questo messaggio, la visualizzazione delle notifiche funziona su questo telefono.','Si ves este mensaje, la visualización de notificaciones funciona en este teléfono.'),
                icon:'/train/assets/icon-192.png',tag:`wfgg-local-test-${Date.now()}`,data:{url:'/train/'}
            });
            toast(pushText('Test local demandé au téléphone','Local display test requested','Test locale richiesto al telefono','Prueba local solicitada al teléfono'));
        }catch(e){toast(e.message||String(e));}
    }
"""
new="""    /* WFGG_PUSH_LOCAL_DISPLAY_DIAGNOSTIC_V2 */
    async function testLocalNotification(){
        if(!('Notification' in window))return toast(pushText('Notifications non prises en charge','Notifications not supported','Notifiche non supportate','Notificaciones no compatibles'));
        if(Notification.permission!=='granted')return toast(pushText(`Notifications non autorisées (${Notification.permission})`,`Notifications not allowed (${Notification.permission})`,`Notifiche non autorizzate (${Notification.permission})`,`Notificaciones no autorizadas (${Notification.permission})`));
        try{
            const reg=await ensurePushRegistration();
            await navigator.serviceWorker.ready;
            const worker=reg.active||reg.waiting||reg.installing;
            if(!worker)throw new Error(pushText('Service Worker non actif','Service Worker not active','Service Worker non attivo','Service Worker no activo'));
            const tag=`wfgg-local-test-${Date.now()}`;
            let ack=null;
            if(reg.active){
                ack=await new Promise(resolve=>{
                    const channel=new MessageChannel();
                    const timer=setTimeout(()=>resolve({ok:false,error:'timeout'}),2500);
                    channel.port1.onmessage=e=>{clearTimeout(timer);resolve(e.data||{ok:false});};
                    reg.active.postMessage({type:'WFGG_LOCAL_NOTIFICATION_TEST',tag,url:'/train/'},[channel.port2]);
                });
            }
            if(!ack?.ok){
                await reg.showNotification('WfGg Train · test local',{
                    body:pushText('Si tu vois ce message, l’affichage des notifications fonctionne sur ce téléphone.','If you see this message, notification display works on this phone.','Se vedi questo messaggio, la visualizzazione delle notifiche funziona su questo telefono.','Si ves este mensaje, la visualización de notificaciones funciona en este teléfono.'),
                    icon:'/train/assets/icon-192.png',tag,data:{url:'/train/'}
                });
            }
            await new Promise(r=>setTimeout(r,350));
            const visible=await reg.getNotifications({tag});
            if(visible.length){
                const android=/Android/i.test(navigator.userAgent||'');
                if(android){
                    openModal(`<h2>🔔 Diagnostic notifications</h2><div class=\"warning\">${pushText('Chrome a bien créé la notification, mais Android ne l’affiche pas. Le blocage est donc dans les réglages de notifications du téléphone/Chrome.','Chrome created the notification, but Android is not displaying it. The block is therefore in the phone/Chrome notification settings.','Chrome ha creato la notifica, ma Android non la visualizza. Il blocco è quindi nelle impostazioni notifiche del telefono/Chrome.','Chrome creó la notificación, pero Android no la muestra. El bloqueo está en los ajustes de notificaciones del teléfono/Chrome.')}</div><p>${pushText('À vérifier : Paramètres Android → Applications → Chrome → Notifications, puis dans Chrome → Paramètres → Paramètres des sites → Notifications → wfgg.pages.dev.','Check: Android Settings → Apps → Chrome → Notifications, then Chrome → Settings → Site settings → Notifications → wfgg.pages.dev.','Controlla: Impostazioni Android → App → Chrome → Notifiche, poi Chrome → Impostazioni → Impostazioni sito → Notifiche → wfgg.pages.dev.','Comprueba: Ajustes Android → Aplicaciones → Chrome → Notificaciones, luego Chrome → Ajustes → Configuración de sitios → Notificaciones → wfgg.pages.dev.')}</p><button class=\"btn gold full\" onclick=\"W.closeModal()\">OK</button>`);
                }else{
                    toast(pushText('La notification a été créée par le navigateur mais n’est pas visible à l’écran','The browser created the notification but it is not visible on screen','La notifica è stata creata dal browser ma non è visibile','El navegador creó la notificación pero no es visible en pantalla'));
                }
            }else{
                toast(pushText('Le navigateur n’a pas conservé la notification locale : Service Worker/permission à contrôler','The browser did not keep the local notification: check Service Worker/permission','Il browser non ha mantenuto la notifica locale: controllare Service Worker/autorizzazione','El navegador no conservó la notificación local: revisa Service Worker/permisos'));
            }
        }catch(e){toast(e.message||String(e));}
    }
"""
if old not in s:
    raise SystemExit('local notification block not found')
s=s.replace(old,new,1)
app.write_text(s,encoding='utf-8')
Path('frontend/train-native/app.v15.js.sha256').write_text(f"{hashlib.sha256(app.read_bytes()).hexdigest()}  frontend/train-native/app.v15.js\n",encoding='utf-8')

sw=Path('frontend/train-native/wfgg-push-sw.js')
w=sw.read_text(encoding='utf-8')
marker='/* WFGG_PUSH_SW_LOCAL_DIAGNOSTIC_V2 */'
if marker not in w:
    w += """

/* WFGG_PUSH_SW_LOCAL_DIAGNOSTIC_V2 */
self.addEventListener('message', event => {
  if (event.data?.type !== 'WFGG_LOCAL_NOTIFICATION_TEST') return;
  const tag = event.data?.tag || `wfgg-local-test-${Date.now()}`;
  const promise = self.registration.showNotification('WfGg Train · test local', {
    body: 'Si tu vois ce message, l’affichage des notifications fonctionne sur ce téléphone.',
    icon: '/train/assets/icon-192.png',
    tag,
    data: { url: event.data?.url || '/train/' }
  }).then(async () => {
    const shown = await self.registration.getNotifications({tag});
    event.ports?.[0]?.postMessage({ok:true,count:shown.length});
  }).catch(error => {
    event.ports?.[0]?.postMessage({ok:false,error:String(error?.message||error)});
  });
  event.waitUntil(promise);
});
"""
    sw.write_text(w,encoding='utf-8')

print('patched local notification diagnostics v2')
