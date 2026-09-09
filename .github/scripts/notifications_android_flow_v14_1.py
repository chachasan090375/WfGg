from pathlib import Path
import re

APP = Path('frontend/train-native/app.v15.js')
SENTINEL = Path('frontend/train-native/sentinel-train-v1.js')
WORKER = Path('frontend/_worker.js')


def replace_once(text, old, new, label):
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise SystemExit(f'{label}: anchor not found')


# --- Train UI: make Android/Chrome settings the primary recovery path ---
a = APP.read_text(encoding='utf-8')

prompt_pattern = re.compile(
    r"    function promptAndroidNotificationDisplayFix\(\)\{.*?\n    \}\n    document\.addEventListener\('visibilitychange'",
    re.S,
)
prompt_replacement = r'''    /* WFGG_NOTIFICATION_ANDROID_GUIDED_FIX_V14_1
       When showNotification() succeeds but Android does not display it, do not
       propose a WfGg reset first. Open Chrome notification settings from the
       user's gesture, then recheck automatically when WfGg becomes visible again.
       Android still requires the user to change the system channel/category. */
    function promptAndroidNotificationDisplayFix(){
        const modify=notificationSettingsModifyMarkup(notificationSettingsText('Ouvrir les réglages Chrome','Open Chrome settings','Apri impostazioni Chrome','Abrir ajustes de Chrome'));
        openModal(`<h2>🔔 ${notificationSettingsText('Affichage Android bloqué','Android display blocked','Visualizzazione Android bloccata','Visualización Android bloqueada')}</h2><div class="warning">${notificationSettingsText('Chrome a créé la notification, mais Android ne l’a pas affichée. La chaîne WfGg est correcte jusqu’au système.','Chrome created the notification, but Android did not display it. The WfGg chain is correct up to the system layer.','Chrome ha creato la notifica, ma Android non l’ha visualizzata. La catena WfGg è corretta fino al sistema.','Chrome creó la notificación, pero Android no la mostró. La cadena WfGg es correcta hasta el sistema.')}</div><p>${notificationSettingsText('WfGg va ouvrir directement les notifications de Chrome. Si nécessaire, active Catégories de notification → Sites. En revenant dans WfGg, le test local sera relancé automatiquement.','WfGg will open Chrome notifications directly. If needed, enable Notification categories → Sites. When you return to WfGg, the local test will run automatically.','WfGg aprirà direttamente le notifiche di Chrome. Se necessario, attiva Categorie di notifica → Siti. Tornando in WfGg, il test locale ripartirà automaticamente.','WfGg abrirá directamente las notificaciones de Chrome. Si es necesario, activa Categorías de notificación → Sitios. Al volver a WfGg, la prueba local se repetirá automáticamente.')}</p><div class="actions">${modify}<button id="wfggNotifLater" class="btn outline">${notificationSettingsText('Pas maintenant','Not now','Non ora','Ahora no')}</button></div>`);
        queueMicrotask(()=>{
            wireNotificationSettingsModify();
            document.getElementById('wfggNotifLater')?.addEventListener('click',closeModal);
        });
    }
    document.addEventListener('visibilitychange' '''

m = prompt_pattern.search(a)
if m:
    a = a[:m.start()] + prompt_replacement + a[m.end():]
elif 'WFGG_NOTIFICATION_ANDROID_GUIDED_FIX_V14_1' not in a:
    raise SystemExit('promptAndroidNotificationDisplayFix block not found')

old_return = """                toast(notificationSettingsText('Réglages repris. Nouveau test d’affichage…','Settings resumed. Testing display again…','Impostazioni riprese. Nuovo test di visualizzazione…','Ajustes retomados. Nueva prueba de visualización…'));
                testLocalNotification();
"""
new_return = """                notificationSettingsOutcomeWrite('auto-recheck','returned-from-android-settings');
                toast(notificationSettingsText('Réglages repris. Nouveau test d’affichage…','Settings resumed. Testing display again…','Impostazioni riprese. Nuovo test di visualizzazione…','Ajustes retomados. Nueva prueba de visualización…'));
                await testLocalNotification();
"""
a = replace_once(a, old_return, new_return, 'automatic local recheck')

path_replacements = {
    'Chemin manuel : Paramètres Android → Applications → Chrome → Notifications.': 'Chemin : Paramètres Android → Applications → Chrome → Notifications → Catégories de notification → Sites.',
    'Manual path: Android Settings → Apps → Chrome → Notifications.': 'Path: Android Settings → Apps → Chrome → Notifications → Notification categories → Sites.',
    'Percorso manuale: Impostazioni Android → App → Chrome → Notifiche.': 'Percorso: Impostazioni Android → App → Chrome → Notifiche → Categorie di notifica → Siti.',
    'Ruta manual: Ajustes Android → Aplicaciones → Chrome → Notificaciones.': 'Ruta: Ajustes Android → Aplicaciones → Chrome → Notificaciones → Categorías de notificación → Sitios.',
}
for old, new in path_replacements.items():
    if old in a:
        a = a.replace(old, new, 1)
    elif new not in a:
        raise SystemExit(f'fallback path anchor not found: {old}')

APP.write_text(a, encoding='utf-8')

# --- Sentinel: guide blocked Android users to Chrome settings, not reset first ---
s = SENTINEL.read_text(encoding='utf-8')
s = replace_once(s, "const VERSION = 'sentinel-train-v14.0';", "const VERSION = 'sentinel-train-v14.1';", 'Sentinel version')
s = s.replace(
    "Couche de présentation Android/Chrome : notifications de Chrome ou catégorie/site wfgg.pages.dev bloquée, silencieuse ou supprimée par le système. Backend, VAPID et algorithme Train exclus pour ce défaut d’affichage local.",
    "Couche de présentation Android/Chrome : la catégorie Android de Chrome « Sites » (ou les notifications Chrome) est bloquée, silencieuse ou supprimée par le système. Backend, VAPID et algorithme Train exclus pour ce défaut d’affichage local.",
    1,
)

repair_pattern = re.compile(
    r"    if\(bad\.has\('train-local-notification-visual-outcome'\)\)out\.push\(localRepairCandidateV12\(\{\n"
    r"      id:'repair-local-notification-reset-v13-3'.*?\n"
    r"    \}\)\);",
    re.S,
)
repair_replacement = """    if(bad.has('train-local-notification-visual-outcome'))out.push(localRepairCandidateV12({
      id:'repair-local-notification-android-settings-v14-1',title:'Ouvrir les notifications Android de Chrome puis retester automatiquement',score:99,verdict:'recommended-manual',
      target:'app.v15.js :: notificationSettingsIntentPlan / visibilitychange',proposedChange:'Ouvrir directement APP_NOTIFICATION_SETTINGS pour Chrome depuis le geste utilisateur. Si Android masque encore la notification, l’utilisateur active la catégorie « Sites »; au retour, WfGg relance automatiquement le test local. Ne réinitialiser abonnement Push/Service Worker qu’en dépannage avancé.',simulation:{readonly:true,externalIntentNotLaunched:true,automaticRecheck:true,wfggResetNotPrimary:true},evidence:['showNotification() réussit et getNotifications() retrouve la notification; l’échec est donc après Chrome, dans la présentation Android.'],risks:['Android interdit au Web de modifier silencieusement un canal/catégorie système; le dernier changement doit être fait par l’utilisateur.'],manualValidation:['Appuyer sur Modifier/Ouvrir les réglages Chrome.','Activer la catégorie Sites si elle est bloquée.','Revenir dans WfGg : le test local se relance automatiquement.']
    }));"""
if repair_pattern.search(s):
    s = repair_pattern.sub(repair_replacement, s, count=1)
elif 'repair-local-notification-android-settings-v14-1' not in s:
    raise SystemExit('Sentinel notification repair block not found')

if 'sentinel-train-v14.1' not in s or 'repair-local-notification-android-settings-v14-1' not in s:
    raise SystemExit('Sentinel v14.1 verification failed')
SENTINEL.write_text(s, encoding='utf-8')

# --- Cache-bust Sentinel asset ---
w = WORKER.read_text(encoding='utf-8')
w = replace_once(w, "script.src='/train/sentinel-train-v1.js?v=014';", "script.src='/train/sentinel-train-v1.js?v=0141';", 'Sentinel loader cache-bust')
WORKER.write_text(w, encoding='utf-8')

print('notifications Android flow v14.1 patched')
