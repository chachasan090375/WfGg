from pathlib import Path
import hashlib,re

path=Path('frontend/train-native/app.v15.js')
s=path.read_text(encoding='utf-8')

# Make the group of test buttons follow the real local subscription state.
s=s.replace("const btn=document.getElementById('pushToggle'),detail=document.getElementById('pushDeviceDetail'),test=document.getElementById('pushTestButton');",
            "const btn=document.getElementById('pushToggle'),detail=document.getElementById('pushDeviceDetail'),test=document.getElementById('pushTestButtons')||document.getElementById('pushTestButton');")

m=re.search(r"    async function testLocalPushNotification\(\)\{.*?\n    \}\n    function renderAlerts\(\) \{.*?\n    \}\n    function rotationEquityHtml\(\) \{",s,re.S)
if not m:
    if 'WFGG_PUSH_REMINDER_TEST_UI_V2' in s:
        raise SystemExit(0)
    raise SystemExit('push test/renderAlerts block not found')

new="""    /* WFGG_PUSH_REMINDER_TEST_UI_V2
       Trois tests immédiats : générique, J-1 et Jour J -30 min. Les deux
       derniers reprennent le prochain passage réel mais ne consomment jamais
       le vrai rappel planifié. */
    async function testPushReminder(kind='generic'){
        if(Notification.permission!=='granted')return toast(pushText('Notifications non autorisées','Notifications not allowed','Notifiche non autorizzate','Notificaciones no autorizzadas'));
        try{
            const r=await api('/api/push/test',{method:'POST',body:JSON.stringify({kind})});
            const label=kind==='day_before'?'J-1':kind==='day_of'?'30 min':'test';
            const when=r.assignment?.date?` · ${fmtShort(parseISO(r.assignment.date))}`:'';
            toast(pushText(`Notification ${label} envoyée${when}`,`Notification ${label} sent${when}`,`Notifica ${label} inviata${when}`,`Notificación ${label} enviada${when}`));
        }catch(e){toast(e.message||String(e));}
    }
    async function testLocalPushNotification(){return testPushReminder('generic');}
    function iosPushGuidanceHtml(){
        if(!isAppleMobile())return '';
        if(!isStandaloneApp()){
            return `<div class="alert-card ios-push-guidance"><h3>🍎 ${pushText('iPhone / iPad','iPhone / iPad','iPhone / iPad','iPhone / iPad')}</h3><div class="warning">${pushText(
              'Pour recevoir les notifications sur iOS, ouvre WfGg dans Safari, touche Partager → Ajouter à l’écran d’accueil, puis lance WfGg depuis cette nouvelle icône. Reviens ensuite ici et active les notifications.',
              'To receive notifications on iOS, open WfGg in Safari, tap Share → Add to Home Screen, then launch WfGg from the new icon. Return here and enable notifications.',
              'Per ricevere le notifiche su iOS, apri WfGg in Safari, tocca Condividi → Aggiungi alla schermata Home, poi avvia WfGg dalla nuova icona. Torna qui e attiva le notifiche.',
              'Para recibir notificaciones en iOS, abre WfGg en Safari, pulsa Compartir → Añadir a pantalla de inicio y abre WfGg desde el nuevo icono. Luego vuelve aquí y activa las notificaciones.'
            )}</div></div>`;
        }
        if(!pushFeatureSupported()){
            return `<div class="alert-card ios-push-guidance"><h3>🍎 iPhone / iPad</h3><div class="warning">${pushText('Cette version d’iOS ou ce navigateur ne permet pas encore les notifications Web Push pour WfGg.','This iOS version or browser does not yet support Web Push for WfGg.','Questa versione di iOS o questo browser non supporta ancora Web Push per WfGg.','Esta versión de iOS o navegador todavía no admite Web Push para WfGg.')}</div></div>`;
        }
        return `<div class="alert-card ios-push-guidance"><h3>🍎 iPhone / iPad</h3><p>✅ ${pushText('WfGg est ouvert comme application depuis l’écran d’accueil. Tu peux activer les notifications ci-dessous.','WfGg is running as a Home Screen app. You can enable notifications below.','WfGg è aperto come app dalla schermata Home. Puoi attivare le notifiche qui sotto.','WfGg está abierto como app desde la pantalla de inicio. Puedes activar las notificaciones abajo.')}</p></div>`;
    }
    function renderAlerts() {
        const el = document.getElementById('alertsScreen'), m = user();
        if (!el || !m) return;
        el.innerHTML = `<div class="section-title"><h2>🔔 Alertes & calendrier</h2></div>
  ${iosPushGuidanceHtml()}
  <div class="alert-card"><div class="toggle-row"><div><h3>${pushText('Notifications téléphone','Phone notifications','Notifiche telefono','Notificaciones del teléfono')}</h3><p>${pushText(`J-1 à ${state.settings.trainTime}, puis 30 minutes avant le départ.`,`1 day before at ${state.settings.trainTime}, then 30 minutes before departure.`,`1 giorno prima alle ${state.settings.trainTime}, poi 30 minuti prima della partenza.`,`1 día antes a las ${state.settings.trainTime}, y 30 minutos antes de la salida.`)}</p></div><button id="pushToggle" class="toggle" disabled onclick="W.toggleAlerts()"><i></i></button></div><div id="pushDeviceDetail" class="warning">${pushText('Vérification de cet appareil…','Checking this device…','Verifica del dispositivo…','Comprobando este dispositivo…')}</div><div id="pushTestButtons" class="hidden"><button id="pushTestButton" class="btn outline full" onclick="W.testPushReminder('generic')">🔔 ${pushText('Tester une notification','Test a notification','Prova una notifica','Probar una notificación')}</button><div class="actions" style="margin-top:8px"><button class="btn outline" onclick="W.testPushReminder('day_before')">🧪 ${pushText('Tester le rappel J-1','Test the day-before reminder','Prova il promemoria J-1','Probar el recordatorio J-1')}</button><button class="btn outline" onclick="W.testPushReminder('day_of')">🧪 ${pushText('Tester le rappel 30 min','Test the 30-min reminder','Prova il promemoria 30 min','Probar el recordatorio 30 min')}</button></div><p class="language-note">${pushText('Ces deux tests utilisent ton prochain passage réel mais n’annulent ni ne consomment les vrais rappels programmés.','These two tests use your real next assignment but do not cancel or consume the scheduled reminders.','Questi due test usano il tuo prossimo turno reale ma non annullano né consumano i promemoria programmati.','Estas dos pruebas usan tu próximo turno real pero no cancelan ni consumen los recordatorios programados.')}</p></div></div>
  <div class="alert-card"><h3>📅 ${pushText('Calendrier (optionnel)','Calendar (optional)','Calendario (opzionale)','Calendario (opcional)')}</h3><p>${pushText('Tu peux aussi ajouter tes prochains passages au calendrier du téléphone.','You can also add your upcoming turns to the phone calendar.','Puoi anche aggiungere i prossimi turni al calendario del telefono.','También puedes añadir tus próximos turnos al calendario del teléfono.')}</p><button class="btn gold full" onclick="W.addAllCalendar()">Ajouter mes passages au calendrier</button></div>
  <div class="alert-card"><h3>🕗 Heure du train</h3><p>Heure actuelle : <strong>${state.settings.trainTime}</strong>. Elle est modifiable par les R4/R5.</p></div>`;
        queueMicrotask(()=>refreshPushUi());
    }
    function rotationEquityHtml() {"""
s=s[:m.start()]+new+s[m.end():]
s=s.replace('addCalendar, addAllCalendar, toggleAlerts, testLocalPushNotification, changeWeek,',
            'addCalendar, addAllCalendar, toggleAlerts, testLocalPushNotification, testPushReminder, changeWeek,')
path.write_text(s,encoding='utf-8')

digest=hashlib.sha256(path.read_bytes()).hexdigest()
Path('frontend/train-native/app.v15.js.sha256').write_text(f'{digest}  frontend/train-native/app.v15.js\n',encoding='utf-8')
