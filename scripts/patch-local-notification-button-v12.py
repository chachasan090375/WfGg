from pathlib import Path

APP=Path('frontend/train-native/app.v15.js')
SENTINEL=Path('frontend/train-native/sentinel-train-v1.js')
EDGE=Path('frontend/_worker.js')
app=APP.read_text(encoding='utf-8')
sentinel=SENTINEL.read_text(encoding='utf-8')
edge=EDGE.read_text(encoding='utf-8')

def replace_once(text,old,new,label):
    if old not in text:
        raise SystemExit(f'PATCH_MISSING {label}')
    return text.replace(old,new,1)

if 'testLocalNotification, testLocalPushNotification' not in app:
    app=replace_once(
        app,
        'addCalendar, addAllCalendar, toggleAlerts, testLocalPushNotification, testPushReminder,',
        'addCalendar, addAllCalendar, toggleAlerts, testLocalNotification, testLocalPushNotification, testPushReminder,',
        'window.W local notification export'
    )

if "'testLocalNotification','testLocalPushNotification','testPushReminder'" not in sentinel:
    sentinel=replace_once(
        sentinel,
        "'addCalendar','addAllCalendar','toggleAlerts','testLocalPushNotification','testPushReminder',",
        "'addCalendar','addAllCalendar','toggleAlerts','testLocalNotification','testLocalPushNotification','testPushReminder',",
        'Sentinel UI notification contract'
    )

if 'train-local-notification-handler-v12' not in sentinel:
    marker="""    const calendarRuntime = typeof Blob === 'function' && typeof URL?.createObjectURL === 'function' && typeof window.W?.addCalendar === 'function' && typeof window.W?.addAllCalendar === 'function';"""
    insertion="""    /* train-local-notification-handler-v12
       Vérifie le branchement exact du bouton d'affichage local : le HTML appelle
       W.testLocalNotification(), qui doit donc être exporté par app.v15. */
    const localNotificationHandler = typeof window.W?.testLocalNotification === 'function';
    items.push(localCheck(
      'train-local-notification-handler',localNotificationHandler?'ok':'error','Bouton test notification locale',
      'W.testLocalNotification disponible',localNotificationHandler?'câblé':'absent',
      'Ce contrôle distingue le test local Service Worker du test Push serveur.',
      localNotificationHandler?'':'Le bouton de test local appelle une fonction non exposée.'
    ));
    const calendarRuntime = typeof Blob === 'function' && typeof URL?.createObjectURL === 'function' && typeof window.W?.addCalendar === 'function' && typeof window.W?.addAllCalendar === 'function';"""
    sentinel=replace_once(sentinel,marker,insertion,'Sentinel local notification check')

edge=edge.replace("script.src='/train/sentinel-train-v1.js?v=011';","script.src='/train/sentinel-train-v1.js?v=012';")
edge=edge.replace('wfgg_bridge=v14','wfgg_bridge=v15')

APP.write_text(app,encoding='utf-8')
SENTINEL.write_text(sentinel,encoding='utf-8')
EDGE.write_text(edge,encoding='utf-8')
print('WFGG_LOCAL_NOTIFICATION_BUTTON_V12=PATCHED')
