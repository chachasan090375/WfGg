from pathlib import Path
import hashlib
import re

APP = Path('frontend/train-native/app.v15.js')
WORKER = Path('frontend/_worker.js')
CHECKSUM = Path('frontend/train-native/app.v15.js.sha256')

app = APP.read_text(encoding='utf-8')

new_render = r'''    /* WFGG_TRAIN_ALERTS_USER_UI_CLEAN_V1
       L'écran utilisateur ne contient plus les boutons de diagnostic Push/local.
       Les fonctions techniques restent exposées à Sentinel, en lecture/diagnostic. */
    function renderAlerts() {
        const el = document.getElementById('alertsScreen'), m = user();
        if (!el || !m) return;
        el.innerHTML = `<div class="section-title"><h2>🔔 Alertes & calendrier</h2></div>
  ${iosPushGuidanceHtml()}
  <div class="alert-card"><div class="toggle-row"><div><h3>${pushText('Notifications téléphone','Phone notifications','Notifiche telefono','Notificaciones del teléfono')}</h3><p>${pushText(`J-1 à ${state.settings.trainTime}, puis 30 minutes avant le départ.`,`1 day before at ${state.settings.trainTime}, then 30 minutes before departure.`,`1 giorno prima alle ${state.settings.trainTime}, poi 30 minuti prima della partenza.`,`1 día antes a las ${state.settings.trainTime}, y 30 minutos antes de la salida.`)}</p></div><button id="pushToggle" class="toggle" disabled onclick="W.toggleAlerts()"><i></i></button></div><div id="pushDeviceDetail" class="warning">${pushText('Vérification de cet appareil…','Checking this device…','Verifica del dispositivo…','Comprobando este dispositivo…')}</div><p class="language-note">${pushText('Les rappels sont envoyés automatiquement selon ton planning lorsque les notifications sont activées.','Reminders are sent automatically from your schedule when notifications are enabled.','I promemoria vengono inviati automaticamente in base al calendario quando le notifiche sono attive.','Los recordatorios se envían automáticamente según tu calendario cuando las notificaciones están activadas.')}</p></div>
  <div class="alert-card"><h3>📅 ${pushText('Calendrier (optionnel)','Calendar (optional)','Calendario (opzionale)','Calendario (opcional)')}</h3><p>${pushText('Tu peux aussi ajouter tes prochains passages au calendrier du téléphone.','You can also add your upcoming turns to the phone calendar.','Puoi anche aggiungere i prossimi turni al calendario del telefono.','También puedes añadir tus próximos turnos al calendario del teléfono.')}</p><button class="btn gold full" onclick="W.addAllCalendar()">Ajouter mes passages au calendrier</button></div>
  <div class="alert-card"><h3>🕗 Heure du train</h3><p>Heure actuelle : <strong>${state.settings.trainTime}</strong>. Elle est modifiable par les R4/R5.</p></div>`;
        queueMicrotask(()=>refreshPushUi());
    }'''

pattern = re.compile(r"    function renderAlerts\(\) \{.*?        queueMicrotask\(\(\)=>refreshPushUi\(\)\);\n    \}", re.S)
app, count = pattern.subn(new_render, app, count=1)
if count != 1:
    raise SystemExit(f'renderAlerts replacement count={count}')

old_decl = "        const btn=document.getElementById('pushToggle'),detail=document.getElementById('pushDeviceDetail'),test=document.getElementById('pushTestButtons')||document.getElementById('pushTestButton');"
new_decl = "        const btn=document.getElementById('pushToggle'),detail=document.getElementById('pushDeviceDetail');"
if old_decl not in app:
    raise SystemExit('refreshPushUi declaration not found')
app = app.replace(old_decl, new_decl, 1)

old_test_line = "            if(test)test.classList.toggle('hidden',!local);\n"
if old_test_line not in app:
    raise SystemExit('push test visibility line not found')
app = app.replace(old_test_line, '', 1)

# Safety: diagnostic capabilities remain for Sentinel, but no test/reset buttons remain in renderAlerts.
for required in ['async function testPushReminder', 'async function testLocalNotification', 'promptWfggNotificationReset', 'sentinelUiProbe', 'testLocalNotification, testLocalPushNotification, testPushReminder']:
    if required not in app:
        raise SystemExit(f'missing diagnostic capability: {required}')

render_block = new_render
for forbidden in ['pushTestButtons', 'pushTestButton', 'W.testPushReminder', 'W.testLocalNotification', 'W.promptWfggNotificationReset', 'Tester l’envoi Push serveur', 'Tester l’affichage local']:
    if forbidden in render_block:
        raise SystemExit(f'user UI still contains diagnostic control: {forbidden}')

APP.write_text(app, encoding='utf-8')
sha = hashlib.sha256(APP.read_bytes()).hexdigest()
CHECKSUM.write_text(f'{sha}  app.v15.js\n', encoding='utf-8')

worker = WORKER.read_text(encoding='utf-8')
old = "'wfgg_bridge=v15';"
new = "'wfgg_bridge=v15&wfgg_ui=clean1';"
occ = worker.count(old)
if occ < 2:
    raise SystemExit(f'expected at least two cache-bust literals, got {occ}')
worker = worker.replace(old, new)
WORKER.write_text(worker, encoding='utf-8')

print('WFGG_TRAIN_ALERTS_USER_UI_CLEAN_V1=APPLIED')
print('sha256='+sha)
