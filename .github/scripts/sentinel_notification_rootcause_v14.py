from pathlib import Path

sentinel = Path('frontend/train-native/sentinel-train-v1.js')
s = sentinel.read_text(encoding='utf-8')

s = s.replace("const VERSION = 'sentinel-train-v13.3';", "const VERSION = 'sentinel-train-v14.0';", 1)

anchor = """    items.push(localCheck(
      'train-local-notification-visual-outcome',localVisualLevel,'Affichage réel de la notification locale',
      'Service Worker crée la notification ET l’utilisateur confirme sa visibilité',localVisualObserved,
      localVisualDetail,localVisualCause
    ));
"""

block = r"""

    /* WFGG_SENTINEL_NOTIFICATION_ROOT_CAUSE_V14
       Transforme les preuves techniques déjà collectées en un verdict de couche fautive.
       Limite volontaire : le Web ne peut pas lire les canaux/catégories privés d'Android.
       Si Chrome a créé la notification mais que l'utilisateur confirme qu'elle n'est pas
       visible, la chaîne Web est validée et la cause est classée dans la présentation OS. */
    let rcReg=null,rcSub=null;
    if('serviceWorker' in navigator){
      try{
        const rcRegs=await navigator.serviceWorker.getRegistrations();
        rcReg=rcRegs.find((r)=>{
          try{return new URL(r.active?.scriptURL||r.waiting?.scriptURL||'').pathname==='/train/wfgg-push-sw.js';}catch(_){return false;}
        })||null;
      }catch(_){}
      if(rcReg?.pushManager){
        try{rcSub=await rcReg.pushManager.getSubscription();}catch(_){}
      }
    }

    let rootCode='DIAGNOSTIC_INCOMPLETE';
    let rootLevel='info';
    let rootTitle='🧭 VERDICT CAUSE RACINE · Notifications';
    let rootObserved='Diagnostic incomplet';
    let rootDetail='Sentinel n’a pas encore assez de preuves pour isoler la couche fautive.';
    let rootCause='';
    let rootConfidence='moyenne';

    if(!notificationSupported){
      rootCode='WEB_NOTIFICATIONS_UNSUPPORTED';
      rootLevel='error';
      rootObserved='API Notifications absente';
      rootDetail='Ce navigateur ne fournit pas l’API Notifications nécessaire à WfGg.';
      rootCause='Navigateur/appareil incompatible avec les notifications Web.';
      rootConfidence='élevée';
    }else if(permission!=='granted'){
      rootCode=permission==='denied'?'WEB_PERMISSION_DENIED':'WEB_PERMISSION_NOT_GRANTED';
      rootLevel=permission==='denied'?'error':'warning';
      rootObserved=`Permission navigateur = ${permission}`;
      rootDetail='La chaîne s’arrête avant toute tentative d’affichage.';
      rootCause=permission==='denied'?'Permission notifications refusée pour wfgg.pages.dev.':'Permission notifications pas encore accordée.';
      rootConfidence='élevée';
    }else if(!rcReg?.active){
      rootCode='TRAIN_PUSH_SERVICE_WORKER_INACTIVE';
      rootLevel='error';
      rootObserved='Permission accordée · Service Worker Push Train absent/inactif';
      rootDetail='Le navigateur autorise les notifications, mais aucun Service Worker WfGg actif ne peut les créer.';
      rootCause='Enregistrement/activation du Service Worker /train/wfgg-push-sw.js.';
      rootConfidence='élevée';
    }else if(localVisualStatus==='not-created'){
      rootCode='SHOW_NOTIFICATION_NOT_CREATED';
      rootLevel='error';
      rootObserved='Permission accordée · Service Worker actif · getNotifications() = 0';
      rootDetail='Le test local échoue avant la remise de la notification à Android.';
      rootCause='Échec showNotification()/Service Worker côté navigateur.';
      rootConfidence='élevée';
    }else if(localVisualStatus==='created-not-visible'){
      rootCode=/Android/i.test(navigator.userAgent||'')?'ANDROID_CHROME_PRESENTATION_BLOCKED':'OS_NOTIFICATION_PRESENTATION_BLOCKED';
      rootLevel='error';
      rootObserved=`Permission=granted · SW=actif · notification créée=oui · affichage système=NON · abonnement Push=${rcSub?.endpoint?'présent':'absent'}`;
      rootDetail='Sentinel a la preuve que Chrome/Service Worker a créé la notification et que le navigateur la retrouve. Le défaut se produit donc APRÈS showNotification(), dans la couche qui présente la notification à l’écran.';
      rootCause=/Android/i.test(navigator.userAgent||'')?'Couche de présentation Android/Chrome : notifications de Chrome ou catégorie/site wfgg.pages.dev bloquée, silencieuse ou supprimée par le système. Backend, VAPID et algorithme Train exclus pour ce défaut d’affichage local.':'Couche de présentation des notifications du système/navigateur.';
      rootConfidence='très élevée';
    }else if(localVisualStatus==='visible-confirmed'){
      if(!rcSub?.endpoint){
        rootCode='PUSH_SUBSCRIPTION_MISSING';
        rootLevel='error';
        rootObserved='Affichage local confirmé · abonnement Push absent';
        rootDetail='Le téléphone sait afficher les notifications mais ne possède pas d’endpoint Push utilisable.';
        rootCause='Abonnement Push de cet appareil absent/non recréé.';
        rootConfidence='élevée';
      }else{
        rootCode='LOCAL_NOTIFICATION_CHAIN_OK';
        rootLevel='ok';
        rootObserved='Permission=granted · SW=actif · notification locale visible · abonnement Push présent';
        rootDetail='Toute la chaîne locale est saine. Si un Push serveur précis manque encore, l’investigation doit commencer côté transport/envoi serveur, pas côté affichage téléphone.';
        rootCause='Aucune anomalie locale détectée.';
        rootConfidence='élevée';
      }
    }else if(localVisualStatus==='created'){
      rootCode='WEB_CHAIN_OK_VISIBILITY_UNCONFIRMED';
      rootLevel='info';
      rootObserved='Permission=granted · SW=actif · notification créée · visibilité non confirmée';
      rootDetail='Le navigateur a franchi showNotification() et conserve la notification. Seule la visibilité réelle système n’a pas encore été qualifiée.';
      rootCause='La chaîne Web est validée jusqu’à la remise au système.';
      rootConfidence='élevée sur la chaîne Web';
    }else if(localVisualStatus==='reset-pending'||localVisualStatus==='rearmed'){
      rootCode='NOTIFICATION_RESET_IN_PROGRESS';
      rootLevel='info';
      rootObserved=`État de remise à zéro = ${localVisualStatus}`;
      rootDetail='Sentinel attend le prochain résultat du test local après recréation.';
      rootCause='Diagnostic en cours de réarmement.';
      rootConfidence='élevée';
    }else{
      rootCode=rcSub?.endpoint?'TECHNICAL_CHAIN_READY_NO_VISUAL_RESULT':'PUSH_SUBSCRIPTION_MISSING_OR_UNTESTED';
      rootLevel=rcSub?.endpoint?'info':'warning';
      rootObserved=`Permission=granted · SW=actif · abonnement Push=${rcSub?.endpoint?'présent':'absent'} · résultat visuel=${localVisualStatus||'inconnu'}`;
      rootDetail='Sentinel possède l’état technique mais aucun résultat visuel exploitable du dernier test local.';
      rootCause=rcSub?.endpoint?'Exécuter une seule fois le test local pour qualifier la dernière couche système.':'Abonnement Push absent ou test de réactivation non terminé.';
      rootConfidence='moyenne';
    }

    const rootItem=localCheck(
      'train-notification-root-cause',rootLevel,rootTitle,
      'Un code de cause racine unique et une couche fautive isolée',
      `${rootCode} · confiance=${rootConfidence}`,
      `${rootObserved} · Dernier résultat local=${localVisualStatus||'aucun'}${localVisual?.at?` · ${localVisual.at}`:''}. ${rootDetail}`,
      rootCause
    );
    rootItem.area='Train · notifications · CAUSE RACINE';
    rootItem.rootCauseCode=rootCode;
    rootItem.confidence=rootConfidence;
    items.unshift(rootItem);
"""

marker = 'WFGG_SENTINEL_NOTIFICATION_ROOT_CAUSE_V14'
if marker not in s:
    if anchor not in s:
        raise SystemExit('sentinel visual outcome anchor not found')
    s = s.replace(anchor, anchor + block, 1)

if "sentinel-train-v14.0" not in s or marker not in s:
    raise SystemExit('sentinel v14 patch verification failed')
sentinel.write_text(s, encoding='utf-8')

worker = Path('frontend/_worker.js')
w = worker.read_text(encoding='utf-8')
old = "script.src='/train/sentinel-train-v1.js?v=013';"
new = "script.src='/train/sentinel-train-v1.js?v=014';"
if old in w:
    w = w.replace(old, new, 1)
elif new not in w:
    raise SystemExit('sentinel loader cache-bust anchor not found')
worker.write_text(w, encoding='utf-8')

print('sentinel notification root-cause v14 patched')
