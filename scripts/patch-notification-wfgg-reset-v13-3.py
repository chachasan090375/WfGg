from pathlib import Path
import hashlib

APP=Path('frontend/train-native/app.v15.js')
SENT=Path('frontend/train-native/sentinel-train-v1.js')

def once(text, old, new, label):
    n=text.count(old)
    if n!=1:
        raise SystemExit(f'{label}: expected 1 occurrence, got {n}')
    return text.replace(old,new,1)

app=APP.read_text(encoding='utf-8')

app=once(app,
"    let pushDeviceState={checking:false,local:false,total:0,permission:'default'};\n",
"    let pushDeviceState={checking:false,local:false,total:0,permission:'default'};\n"
"    /* WFGG_LOCAL_NOTIFICATION_OUTCOME_V13_3\n"
"       Preuve appareil explicitement confirmée par l'utilisateur : le Web peut\n"
"       prouver qu'une notification a été créée, mais pas qu'Android l'a rendue visible. */\n"
"    const LOCAL_NOTIFICATION_OUTCOME_KEY='wfgg_local_notification_outcome_v13_3';\n"
"    function localNotificationOutcomeRead(){\n"
"        try{return JSON.parse(localStorage.getItem(LOCAL_NOTIFICATION_OUTCOME_KEY)||'null')||null;}catch(_){return null;}\n"
"    }\n"
"    function localNotificationOutcomeWrite(status,detail=''){\n"
"        try{\n"
"            const value={status:String(status||''),detail:String(detail||''),at:new Date().toISOString()};\n"
"            localStorage.setItem(LOCAL_NOTIFICATION_OUTCOME_KEY,JSON.stringify(value));\n"
"            return value;\n"
"        }catch(_){return null;}\n"
"    }\n",
'insert local outcome helpers')

reset_block=r'''    /* WFGG_NOTIFICATION_WFGG_RESET_V13_3
       Réinitialisation strictement limitée à WfGg sur cet appareil : abonnement
       Push serveur/local + Service Worker Train. Une page Web ne peut pas révoquer
       elle-même la permission Android/Chrome ; cette étape reste volontairement
       explicite dans le parcours utilisateur. */
    function promptLocalNotificationVisibilityCheck(){
        openModal(`<h2>🔔 ${pushText('As-tu vu la notification ?','Did you see the notification?','Hai visto la notifica?','¿Has visto la notificación?')}</h2><p>${pushText('WfGg a bien demandé au navigateur de créer la notification. Dis-nous maintenant si elle est réellement apparue sur le téléphone.','WfGg successfully asked the browser to create the notification. Tell us whether it actually appeared on the phone.','WfGg ha chiesto correttamente al browser di creare la notifica. Indica se è realmente apparsa sul telefono.','WfGg pidió correctamente al navegador crear la notificación. Indica si realmente apareció en el teléfono.')}</p><div class="actions"><button id="wfggLocalVisibleYes" class="btn success">✅ ${pushText('Oui, je l’ai vue','Yes, I saw it','Sì, l’ho vista','Sí, la vi')}</button><button id="wfggLocalVisibleNo" class="btn danger">❌ ${pushText('Non, rien n’est apparu','No, nothing appeared','No, non è apparso nulla','No, no apareció nada')}</button></div>`);
        queueMicrotask(()=>{
            document.getElementById('wfggLocalVisibleYes')?.addEventListener('click',()=>{
                localNotificationOutcomeWrite('visible-confirmed','user-confirmed-visible');
                closeModal();
                toast(pushText('Affichage local confirmé ✅','Local display confirmed ✅','Visualizzazione locale confermata ✅','Visualización local confirmada ✅'));
            });
            document.getElementById('wfggLocalVisibleNo')?.addEventListener('click',()=>{
                localNotificationOutcomeWrite('created-not-visible','user-confirmed-not-visible');
                promptAndroidNotificationDisplayFix();
            });
        });
    }
    function promptWfggNotificationReset(){
        openModal(`<h2>♻️ ${pushText('Réinitialiser uniquement les notifications WfGg','Reset only WfGg notifications','Reimposta solo le notifiche WfGg','Restablecer solo las notificaciones WfGg')}</h2><div class="warning">${pushText('Cette opération supprime uniquement l’abonnement Push de WfGg sur ce téléphone et le Service Worker Train. Elle ne modifie aucune autre notification de Chrome ni aucun autre site.','This only removes the WfGg Push subscription on this phone and the Train Service Worker. It does not change any other Chrome notification or site.','Questa operazione rimuove solo l’abbonamento Push WfGg su questo telefono e il Service Worker Train. Non modifica altre notifiche o siti di Chrome.','Esta operación solo elimina la suscripción Push de WfGg en este teléfono y el Service Worker de Train. No modifica ninguna otra notificación ni sitio de Chrome.')}</div><p>${pushText('Après le nettoyage, Chrome devra recréer la permission et la catégorie Android de wfgg.pages.dev.','After cleanup, Chrome must recreate the permission and Android category for wfgg.pages.dev.','Dopo la pulizia, Chrome dovrà ricreare l’autorizzazione e la categoria Android di wfgg.pages.dev.','Después de la limpieza, Chrome deberá recrear el permiso y la categoría Android de wfgg.pages.dev.')}</p><div class="actions"><button id="wfggNotifDoReset" class="btn danger">♻️ ${pushText('Réinitialiser WfGg','Reset WfGg','Reimposta WfGg','Restablecer WfGg')}</button><button id="wfggNotifResetCancel" class="btn outline">${pushText('Annuler','Cancel','Annulla','Cancelar')}</button></div>`);
        queueMicrotask(()=>{
            document.getElementById('wfggNotifDoReset')?.addEventListener('click',resetWfggNotifications);
            document.getElementById('wfggNotifResetCancel')?.addEventListener('click',closeModal);
        });
    }
    async function resetWfggNotifications(){
        try{
            const sub=await localPushSubscription();
            if(sub){
                try{await api('/api/push/subscription',{method:'DELETE',body:JSON.stringify({endpoint:sub.endpoint})});}catch(_){}
                try{await sub.unsubscribe();}catch(_){}
            }
            const reg=await navigator.serviceWorker.getRegistration('/train/');
            if(reg){try{await reg.unregister();}catch(_){}}
            localNotificationOutcomeWrite('reset-pending','subscription-unsubscribed;train-sw-unregistered');
            notificationSettingsOutcomeWrite('reset-pending','wfgg-only-reset');
            await syncSnapshot({render:false,quiet:true}).catch(()=>false);
            closeModal();
            openModal(`<h2>♻️ ${pushText('Nettoyage WfGg terminé','WfGg cleanup complete','Pulizia WfGg completata','Limpieza de WfGg completada')}</h2><div class="warning">${pushText('WfGg a supprimé son abonnement Push et son Service Worker sur ce téléphone. Pour forcer Chrome à recréer la catégorie Android, ouvre les Autorisations de wfgg.pages.dev et touche « Réinitialiser les autorisations », puis reviens ici.','WfGg removed its Push subscription and Service Worker on this phone. To force Chrome to recreate the Android category, open permissions for wfgg.pages.dev and tap “Reset permissions”, then come back here.','WfGg ha rimosso l’abbonamento Push e il Service Worker su questo telefono. Per forzare Chrome a ricreare la categoria Android, apri le autorizzazioni di wfgg.pages.dev e tocca “Reimposta autorizzazioni”, poi torna qui.','WfGg eliminó su suscripción Push y Service Worker en este teléfono. Para forzar a Chrome a recrear la categoría Android, abre los permisos de wfgg.pages.dev y pulsa “Restablecer permisos”, luego vuelve aquí.')}</div><p>${pushText('Ensuite appuie sur Réactiver. WfGg redemandera la permission, recréera l’abonnement et lancera immédiatement un test local.','Then tap Reactivate. WfGg will request permission again, recreate the subscription and immediately run a local test.','Poi tocca Riattiva. WfGg richiederà di nuovo l’autorizzazione, ricreerà l’abbonamento e avvierà subito un test locale.','Luego pulsa Reactivar. WfGg volverá a pedir permiso, recreará la suscripción y lanzará inmediatamente una prueba local.')}</p><div class="actions"><button id="wfggNotifRearm" class="btn gold">🔔 ${pushText('Réactiver','Reactivate','Riattiva','Reactivar')}</button><button id="wfggNotifResetClose" class="btn outline">${pushText('Fermer','Close','Chiudi','Cerrar')}</button></div>`);
            queueMicrotask(()=>{
                document.getElementById('wfggNotifRearm')?.addEventListener('click',()=>reactivateWfggNotifications(false));
                document.getElementById('wfggNotifResetClose')?.addEventListener('click',closeModal);
            });
            return true;
        }catch(e){toast(e.message||String(e));return false;}
    }
    async function reactivateWfggNotifications(force=false){
        if(!pushFeatureSupported())return false;
        if(Notification.permission==='granted'&&!force){
            openModal(`<h2>🔔 ${pushText('Chrome indique encore « Autorisé »','Chrome still says “Allowed”','Chrome indica ancora “Consentito”','Chrome todavía indica “Permitido”')}</h2><div class="warning">${pushText('Pour recréer réellement la catégorie Android WfGg, utilise d’abord « Réinitialiser les autorisations » dans la fiche wfgg.pages.dev. Si tu viens de le faire et que Chrome affiche encore Autorisé, tu peux tenter la recréation quand même.','To truly recreate the WfGg Android category, first use “Reset permissions” on the wfgg.pages.dev site card. If you just did that and Chrome still says Allowed, you can try recreating anyway.','Per ricreare davvero la categoria Android WfGg, usa prima “Reimposta autorizzazioni” nella scheda wfgg.pages.dev. Se lo hai appena fatto e Chrome mostra ancora Consentito, puoi comunque tentare la ricreazione.','Para recrear realmente la categoría Android de WfGg, usa primero “Restablecer permisos” en la ficha de wfgg.pages.dev. Si acabas de hacerlo y Chrome sigue indicando Permitido, puedes intentar recrearla igualmente.')}</div><div class="actions"><button id="wfggNotifRecheckReset" class="btn gold">🔄 ${pushText('Revérifier','Check again','Ricontrolla','Volver a comprobar')}</button><button id="wfggNotifForceRearm" class="btn outline">${pushText('Réactiver quand même','Reactivate anyway','Riattiva comunque','Reactivar igualmente')}</button></div>`);
            queueMicrotask(()=>{
                document.getElementById('wfggNotifRecheckReset')?.addEventListener('click',()=>reactivateWfggNotifications(false));
                document.getElementById('wfggNotifForceRearm')?.addEventListener('click',()=>reactivateWfggNotifications(true));
            });
            return false;
        }
        closeModal();
        const ok=await enablePushNotifications();
        if(ok){
            localNotificationOutcomeWrite('rearmed','push-subscription-recreated');
            setTimeout(()=>testLocalNotification(),800);
        }
        return ok;
    }

'''
app=once(app,
"    /* WFGG_PUSH_LOCAL_DISPLAY_DIAGNOSTIC_V1\n",
reset_block+"    /* WFGG_PUSH_LOCAL_DISPLAY_DIAGNOSTIC_V1\n",
'insert reset flow')

old_visible="""            const visible=await reg.getNotifications({tag});\n            if(visible.length){\n                const android=/Android/i.test(navigator.userAgent||'');\n                if(android){\n                    promptAndroidNotificationDisplayFix();\n                }else{\n                    toast(pushText('La notification a été créée par le navigateur mais n’est pas visible à l’écran','The browser created the notification but it is not visible on screen','La notifica è stata creata dal browser ma non è visibile','El navegador creó la notificación pero no es visible en pantalla'));\n                }\n            }else{\n                toast(pushText('Le navigateur n’a pas conservé la notification locale : Service Worker/permission à contrôler','The browser did not keep the local notification: check Service Worker/permission','Il browser non ha mantenuto la notifica locale: controllare Service Worker/autorizzazione','El navegador no conservó la notificación local: revisa Service Worker/permisos'));\n            }\n"""
new_visible="""            const visible=await reg.getNotifications({tag});\n            if(visible.length){\n                localNotificationOutcomeWrite('created','service-worker-showNotification');\n                setTimeout(()=>promptLocalNotificationVisibilityCheck(),900);\n            }else{\n                localNotificationOutcomeWrite('not-created','getNotifications=0');\n                toast(pushText('Le navigateur n’a pas conservé la notification locale : Service Worker/permission à contrôler','The browser did not keep the local notification: check Service Worker/permission','Il browser non ha mantenuto la notifica locale: controllare Service Worker/autorizzazione','El navegador no conservó la notificación local: revisa Service Worker/permisos'));\n            }\n"""
app=once(app,old_visible,new_visible,'replace local display decision')

old_prompt="""        openModal(`<h2>🔔 ${notificationSettingsText('Diagnostic notifications','Notification diagnostics','Diagnostica notifiche','Diagnóstico de notificaciones')}</h2><div class=\"warning\">${notificationSettingsText('Chrome a bien créé la notification, mais Android ne l’affiche pas. Le blocage est dans les réglages de notifications du téléphone/Chrome.','Chrome created the notification, but Android is not displaying it. The block is in the phone/Chrome notification settings.','Chrome ha creato la notifica, ma Android non la visualizza. Il blocco è nelle impostazioni notifiche del telefono/Chrome.','Chrome creó la notificación, pero Android no la muestra. El bloqueo está en los ajustes de notificaciones del teléfono/Chrome.')}</div><p>${notificationSettingsText('Voulez-vous ouvrir directement les réglages de notifications de Chrome ?','Do you want to open Chrome notification settings now?','Vuoi aprire direttamente le impostazioni notifiche di Chrome?','¿Quieres abrir directamente los ajustes de notificaciones de Chrome?')}</p><div class=\"actions\">${modify}<button id=\"wfggNotifLater\" class=\"btn outline\">${notificationSettingsText('Pas maintenant','Not now','Non ora','Ahora no')}</button></div>`);\n        queueMicrotask(()=>{\n            wireNotificationSettingsModify();\n            document.getElementById('wfggNotifLater')?.addEventListener('click',closeModal);\n        });\n"""
new_prompt="""        openModal(`<h2>🔔 ${notificationSettingsText('Diagnostic notifications','Notification diagnostics','Diagnostica notifiche','Diagnóstico de notificaciones')}</h2><div class=\"warning\">${notificationSettingsText('Chrome a bien créé la notification, mais tu confirmes qu’Android ne l’a pas affichée.','Chrome created the notification, but you confirmed Android did not display it.','Chrome ha creato la notifica, ma hai confermato che Android non l’ha visualizzata.','Chrome creó la notificación, pero confirmaste que Android no la mostró.')}</div><p>${notificationSettingsText('Tu peux tenter les réglages Chrome, ou réinitialiser uniquement le canal WfGg sans toucher aux autres sites.','You can try Chrome settings, or reset only the WfGg channel without touching other sites.','Puoi provare le impostazioni di Chrome o reimpostare solo il canale WfGg senza toccare gli altri siti.','Puedes probar los ajustes de Chrome o restablecer solo el canal WfGg sin tocar otros sitios.')}</p><div class=\"actions\">${modify}<button id=\"wfggNotifResetOnly\" class=\"btn outline\">♻️ ${notificationSettingsText('Réinitialiser WfGg','Reset WfGg','Reimposta WfGg','Restablecer WfGg')}</button><button id=\"wfggNotifLater\" class=\"btn outline\">${notificationSettingsText('Pas maintenant','Not now','Non ora','Ahora no')}</button></div>`);\n        queueMicrotask(()=>{\n            wireNotificationSettingsModify();\n            document.getElementById('wfggNotifResetOnly')?.addEventListener('click',promptWfggNotificationReset);\n            document.getElementById('wfggNotifLater')?.addEventListener('click',closeModal);\n        });\n"""
app=once(app,old_prompt,new_prompt,'enhance android diagnostic modal')

old_buttons="""<button class=\"btn outline full\" style=\"margin-top:8px\" onclick=\"W.testLocalNotification()\">📱 ${pushText('Tester l’affichage local sur ce téléphone','Test local display on this phone','Prova visualizzazione locale sul telefono','Probar visualización local en este teléfono')}</button><div class=\"actions\" style=\"margin-top:8px\"><button class=\"btn outline\" onclick=\"W.testPushReminder('day_before')\">🧪 ${pushText('Tester le rappel J-1','Test the day-before reminder','Prova il promemoria J-1','Probar el recordatorio J-1')}</button><button class=\"btn outline\" onclick=\"W.testPushReminder('day_of')\">🧪 ${pushText('Tester le rappel 30 min','Test the 30-min reminder','Prova il promemoria 30 min','Probar el recordatorio 30 min')}</button></div><p class=\"language-note\">${pushText('Ces deux tests utilisent ton prochain passage réel mais n’annulent ni ne consomment les vrais rappels programmés.','These two tests use your real next assignment but do not cancel or consume the scheduled reminders.','Questi due test usano il tuo prossimo turno reale ma non annullano né consumano i promemoria programmati.','Estas dos pruebas usan tu próximo turno real pero no cancelan ni consumen los recordatorios programados.')}</p>"""
new_buttons="""<button class=\"btn outline full\" style=\"margin-top:8px\" onclick=\"W.testLocalNotification()\">📱 ${pushText('Tester l’affichage local sur ce téléphone','Test local display on this phone','Prova visualizzazione locale sul telefono','Probar visualización local en este teléfono')}</button><div class=\"actions\" style=\"margin-top:8px\"><button class=\"btn outline\" onclick=\"W.testPushReminder('day_before')\">🧪 ${pushText('Tester le rappel J-1','Test the day-before reminder','Prova il promemoria J-1','Probar el recordatorio J-1')}</button><button class=\"btn outline\" onclick=\"W.testPushReminder('day_of')\">🧪 ${pushText('Tester le rappel 30 min','Test the 30-min reminder','Prova il promemoria 30 min','Probar el recordatorio 30 min')}</button></div><button id=\"wfggNotifResetWfgg\" class=\"btn outline full\" style=\"margin-top:8px\" onclick=\"W.promptWfggNotificationReset()\">♻️ ${pushText('Réinitialiser uniquement les notifications WfGg','Reset only WfGg notifications','Reimposta solo le notifiche WfGg','Restablecer solo las notificaciones WfGg')}</button><p class=\"language-note\">${pushText('Les tests J-1 et 30 min sont immédiats et synthétiques : ils n’utilisent pas le calendrier et ne consomment aucun vrai rappel.','The day-before and 30-min tests are immediate and synthetic: they do not use the calendar and consume no real reminder.','I test J-1 e 30 min sono immediati e sintetici: non usano il calendario e non consumano alcun vero promemoria.','Las pruebas J-1 y 30 min son inmediatas y sintéticas: no usan el calendario ni consumen ningún recordatorio real.')}</p>"""
app=once(app,old_buttons,new_buttons,'add reset button and update test note')

old_export="""addCalendar, addAllCalendar, toggleAlerts, testLocalNotification, testLocalPushNotification, testPushReminder, sentinelUiProbe, notificationSettingsIntentPlan, changeWeek"""
new_export="""addCalendar, addAllCalendar, toggleAlerts, testLocalNotification, testLocalPushNotification, testPushReminder, promptWfggNotificationReset, resetWfggNotifications, reactivateWfggNotifications, sentinelUiProbe, notificationSettingsIntentPlan, changeWeek"""
app=once(app,old_export,new_export,'export reset actions')

# Extend the observer-only UI probe: click only the safe reset-prompt button, never the destructive confirmation.
old_probe="""            graphics.push(await sentinelUiGeometry(localPushBtn,'local-notification-test-button',{waitMs:3000,conditional:true}));\n\n            promptAndroidNotificationDisplayFix();await sentinelUiTick();\n"""
new_probe="""            graphics.push(await sentinelUiGeometry(localPushBtn,'local-notification-test-button',{waitMs:3000,conditional:true}));\n            const resetWfggBtn=document.getElementById('wfggNotifResetWfgg');\n            graphics.push(await sentinelUiGeometry(resetWfggBtn,'notification-wfgg-reset-button',{waitMs:3000,conditional:true}));\n            resetWfggBtn?.click();await sentinelUiTick();\n            pushSim('notification-wfgg-reset-prompt',!modal?.classList.contains('hidden')&&!!document.getElementById('wfggNotifDoReset'),'clic → confirmation réinitialisation WfGg, sans exécution');\n            closeModal();\n\n            promptAndroidNotificationDisplayFix();await sentinelUiTick();\n"""
app=once(app,old_probe,new_probe,'extend ui probe')

APP.write_text(app,encoding='utf-8')

sent=SENT.read_text(encoding='utf-8')
sent=once(sent,"  const VERSION = 'sentinel-train-v13.2';","  const VERSION = 'sentinel-train-v13.3';",'sentinel version')

old_ui="""      'addCalendar','addAllCalendar','toggleAlerts','testLocalNotification','testLocalPushNotification','testPushReminder','sentinelUiProbe','notificationSettingsIntentPlan',\n"""
new_ui="""      'addCalendar','addAllCalendar','toggleAlerts','testLocalNotification','testLocalPushNotification','testPushReminder','promptWfggNotificationReset','resetWfggNotifications','reactivateWfggNotifications','sentinelUiProbe','notificationSettingsIntentPlan',\n"""
sent=once(sent,old_ui,new_ui,'sentinel ui function inventory')

visual_check=r'''    /* WFGG_SENTINEL_LOCAL_NOTIFICATION_VISUAL_V13_3
       Le navigateur sait uniquement prouver showNotification/getNotifications.
       La visibilité réelle Android est donc qualifiée par confirmation utilisateur. */
    const localVisual=readJson('wfgg_local_notification_outcome_v13_3',null);
    const localVisualStatus=String(localVisual?.status||'');
    let localVisualLevel='info',localVisualObserved='aucun test visuel confirmé',localVisualDetail='Lance le test local puis confirme si la notification est réellement apparue.';
    let localVisualCause='';
    if(localVisualStatus==='visible-confirmed'){
      localVisualLevel='ok';localVisualObserved='Chrome: notification créée ✅ · affichage Android confirmé ✅';
      localVisualDetail='La visibilité réelle a été confirmée manuellement après un showNotification du Service Worker.';
    }else if(localVisualStatus==='created-not-visible'){
      localVisualLevel='warning';localVisualObserved='Chrome: autorisé ✅ · Service Worker: notification créée ✅ · Android: non visible ❌';
      localVisualDetail='Le navigateur conserve la notification, mais l’utilisateur confirme qu’aucun affichage n’apparaît sur le téléphone.';
      localVisualCause='Canal/catégorie Android Chrome du site possiblement bloqué malgré Notification.permission=granted.';
    }else if(localVisualStatus==='not-created'){
      localVisualLevel='error';localVisualObserved='Service Worker: notification locale non conservée';
      localVisualDetail='getNotifications({tag}) ne retrouve pas le test local.';
      localVisualCause='Service Worker ou permission navigateur à contrôler.';
    }else if(localVisualStatus==='reset-pending'){
      localVisualLevel='info';localVisualObserved='Réinitialisation WfGg en attente de réactivation';
      localVisualDetail='Abonnement Push et Service Worker Train ont été nettoyés; la permission/catégorie du site doit être recréée.';
    }else if(localVisualStatus==='rearmed'){
      localVisualLevel='info';localVisualObserved='Canal WfGg recréé · nouveau test visuel attendu';
      localVisualDetail='L’abonnement a été recréé; confirme le prochain test local.';
    }else if(localVisualStatus==='created'){
      localVisualLevel='info';localVisualObserved='Notification créée · confirmation visuelle en attente';
      localVisualDetail='WfGg attend la réponse Oui/Non du test d’affichage.';
    }
    items.push(localCheck(
      'train-local-notification-visual-outcome',localVisualLevel,'Affichage réel de la notification locale',
      'Service Worker crée la notification ET l’utilisateur confirme sa visibilité',localVisualObserved,
      localVisualDetail,localVisualCause
    ));
'''
sent=once(sent,"    /* WFGG_SENTINEL_UI_SIMULATION_V13 */\n",visual_check+"    /* WFGG_SENTINEL_UI_SIMULATION_V13 */\n",'insert visual outcome check')

# Fallback d'ouverture Settings est une limitation navigateur avec guide fonctionnel: INFO, pas WARNING.
sent=once(sent,
"        settingsLevel='warning';settingsObserved=`${settingsPlan.packageName} · dernier essai: Intent refusé → guide manuel`;",
"        settingsLevel='info';settingsObserved=`${settingsPlan.packageName} · dernier essai: Intent refusé → guide manuel`;",
'settings fallback severity')

repair=r'''    if(bad.has('train-local-notification-visual-outcome'))out.push(localRepairCandidateV12({
      id:'repair-local-notification-reset-v13-3',title:'Recréer uniquement le canal WfGg sur cet appareil',score:98,verdict:'recommended-manual',
      target:'app.v15.js :: promptWfggNotificationReset / resetWfggNotifications',proposedChange:'Supprimer uniquement l’abonnement Push WfGg et le Service Worker Train, réinitialiser l’autorisation du site dans Chrome, puis recréer l’abonnement et relancer le test local.',simulation:{readonly:true,wfggOnly:true,otherChromeSitesUntouched:true},evidence:['La notification est créée par le Service Worker mais l’utilisateur confirme qu’Android ne l’affiche pas.'],risks:['La page Web ne peut pas révoquer elle-même la permission Android/Chrome; une action utilisateur sur Réinitialiser les autorisations reste nécessaire.'],manualValidation:['Réinitialiser uniquement WfGg.','Réactiver.','Confirmer Oui si le test local devient visible.']
    }));
'''
sent=once(sent,"    if(bad.has('train-calendar-runtime'))out.push(localRepairCandidateV12({\n",repair+"    if(bad.has('train-calendar-runtime'))out.push(localRepairCandidateV12({\n",'insert visual repair candidate')

SENT.write_text(sent,encoding='utf-8')

# checksum app.v15.js
h=hashlib.sha256(APP.read_bytes()).hexdigest()
Path('frontend/train-native/app.v15.js.sha256').write_text(f'{h}  app.v15.js\n',encoding='utf-8')
print('patched app.v15.js + sentinel v13.3')
