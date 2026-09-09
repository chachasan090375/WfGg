from pathlib import Path
p=Path('frontend/train-native/app.v15.js')
s=p.read_text(encoding='utf-8')
if 'WFGG_WEB_PUSH_REAL_TEST_V1' not in s:
    old="""    async function testLocalPushNotification(){
        if(Notification.permission!=='granted')return toast(pushText('Notifications non autorisées','Notifications not allowed','Notifiche non autorizzate','Notificaciones no autorizadas'));
        try{
            const reg=await ensurePushRegistration();
            await reg.showNotification('WfGg Train · test',{body:pushText('Les notifications fonctionnent sur cet appareil.','Notifications work on this device.','Le notifiche funzionano su questo dispositivo.','Las notificaciones funcionan en este dispositivo.'),icon:'/train/assets/icon-192.png',tag:'wfgg-train-test',data:{url:'/train/'}});
        }catch(e){toast(e.message||String(e));}
    }
"""
    new="""    /* WFGG_WEB_PUSH_REAL_TEST_V1
       Le bouton Test utilise le même chemin serveur/VAPID que les vrais rappels,
       pas une notification locale : il valide donc toute la chaîne de bout en bout. */
    async function testLocalPushNotification(){
        if(Notification.permission!=='granted')return toast(pushText('Notifications non autorisées','Notifications not allowed','Notifiche non autorizzate','Notificaciones no autorizadas'));
        try{
            const r=await api('/api/push/test',{method:'POST',body:'{}'});
            toast(pushText(`Notification de test envoyée (${r.sent||1})`,`Test notification sent (${r.sent||1})`,`Notifica di prova inviata (${r.sent||1})`,`Notificación de prueba enviada (${r.sent||1})`));
        }catch(e){toast(e.message||String(e));}
    }
"""
    if old not in s: raise SystemExit('local push test function not found')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('Portal real push test wired')
