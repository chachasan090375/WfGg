from pathlib import Path
import hashlib

p=Path('frontend/train-native/app.v15.js')
s=p.read_text(encoding='utf-8')

old="""            const r=await api('/api/push/test',{method:'POST',body:JSON.stringify({kind})});\n            const label=kind==='day_before'?'J-1':kind==='day_of'?'30 min':'test';\n            const when=r.assignment?.date?` · ${fmtShort(parseISO(r.assignment.date))}`:'';\n            toast(pushText(`Notification ${label} envoyée${when}`,`Notification ${label} sent${when}`,`Notifica ${label} inviata${when}`,`Notificación ${label} enviada${when}`));\n"""
new="""            const r=await api('/api/push/test',{method:'POST',body:JSON.stringify({kind})});\n            const label=kind==='day_before'?'J-1':kind==='day_of'?'30 min':'test';\n            const when=r.assignment?.date?` · ${fmtShort(parseISO(r.assignment.date))}`:'';\n            const provider=(r.delivery||[]).map(x=>x.status).filter(Boolean).join(',');\n            const http=provider?` · HTTP ${provider}`:'';\n            toast(pushText(`Envoi ${label} accepté par le service Push${when}${http}`,`Push ${label} accepted by the service${when}${http}`,`Invio ${label} accettato dal servizio Push${when}${http}`,`Envío ${label} aceptado por el servicio Push${when}${http}`));\n"""
if old not in s:
    raise SystemExit('push toast block not found')
s=s.replace(old,new,1)

old="""    async function testLocalPushNotification(){return testPushReminder('generic');}\n"""
new="""    async function testLocalPushNotification(){return testPushReminder('generic');}\n    /* WFGG_PUSH_LOCAL_DISPLAY_DIAGNOSTIC_V1\n       Teste uniquement l'affichage Android/iOS via le Service Worker, sans réseau Push.\n       Si ce test local apparaît mais pas le test serveur, le problème est le transport Push.\n       S'il n'apparaît pas non plus, le blocage est sur l'appareil/navigateur/autorisation. */\n    async function testLocalNotification(){\n        if(Notification.permission!=='granted')return toast(pushText('Notifications non autorisées','Notifications not allowed','Notifiche non autorizzate','Notificaciones no autorizadas'));\n        try{\n            const reg=await ensurePushRegistration();\n            await navigator.serviceWorker.ready;\n            await reg.showNotification('WfGg Train · test local',{\n                body:pushText('Si tu vois ce message, l’affichage des notifications fonctionne sur ce téléphone.','If you see this message, notification display works on this phone.','Se vedi questo messaggio, la visualizzazione delle notifiche funziona su questo telefono.','Si ves este mensaje, la visualización de notificaciones funciona en este teléfono.'),\n                icon:'/train/assets/icon-192.png',tag:`wfgg-local-test-${Date.now()}`,data:{url:'/train/'}\n            });\n            toast(pushText('Test local demandé au téléphone','Local display test requested','Test locale richiesto al telefono','Prueba local solicitada al teléfono'));\n        }catch(e){toast(e.message||String(e));}\n    }\n"""
if old not in s:
    raise SystemExit('local test function anchor not found')
s=s.replace(old,new,1)

old="""<div id=\"pushTestButtons\" class=\"hidden\"><button id=\"pushTestButton\" class=\"btn outline full\" onclick=\"W.testPushReminder('generic')\">🔔 ${pushText('Tester une notification','Test a notification','Prova una notifica','Probar una notificación')}</button><div class=\"actions\" style=\"margin-top:8px\"><button class=\"btn outline\" onclick=\"W.testPushReminder('day_before')\">🧪 ${pushText('Tester le rappel J-1','Test the day-before reminder','Prova il promemoria J-1','Probar el recordatorio J-1')}</button>"""
new="""<div id=\"pushTestButtons\" class=\"hidden\"><button id=\"pushTestButton\" class=\"btn outline full\" onclick=\"W.testPushReminder('generic')\">🔔 ${pushText('Tester l’envoi Push serveur','Test server Push','Prova Push server','Probar Push del servidor')}</button><button class=\"btn outline full\" style=\"margin-top:8px\" onclick=\"W.testLocalNotification()\">📱 ${pushText('Tester l’affichage local sur ce téléphone','Test local display on this phone','Prova visualizzazione locale sul telefono','Probar visualización local en este teléfono')}</button><div class=\"actions\" style=\"margin-top:8px\"><button class=\"btn outline\" onclick=\"W.testPushReminder('day_before')\">🧪 ${pushText('Tester le rappel J-1','Test the day-before reminder','Prova il promemoria J-1','Probar el recordatorio J-1')}</button>"""
if old not in s:
    raise SystemExit('push buttons block not found')
s=s.replace(old,new,1)

s=s.replace('addCalendar, addAllCalendar, toggleAlerts, testLocalPushNotification, changeWeek,',
            'addCalendar, addAllCalendar, toggleAlerts, testLocalPushNotification, testLocalNotification, testPushReminder, changeWeek,',1)

p.write_text(s,encoding='utf-8')
h=hashlib.sha256(p.read_bytes()).hexdigest()
Path('frontend/train-native/app.v15.js.sha256').write_text(f'{h}  frontend/train-native/app.v15.js\n',encoding='utf-8')
print('patched app and checksum',h)
