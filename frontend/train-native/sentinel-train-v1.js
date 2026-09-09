(() => {
  'use strict';

  const VERSION = 'sentinel-train-v13';
  const PORTAL_API = '/portal-api';
  const PORTAL_TOKEN_KEY = 'wfgg_portal_session';
  const TRAIN_STATE_KEY = 'wfgg_train_v13';
  const ROSTER_KEY = 'wfgg_train_roster_cache';
  const BUTTON_ID = 'wfggTrainSentinelButton';
  const OVERLAY_ID = 'wfggTrainSentinelOverlay';
  const STYLE_ID = 'wfggTrainSentinelStyle';
  let accessConfirmed = false;
  let accessRole = '';
  let launchLocked = false;
  let lastReport = null;
  let lastAnchor = null;

  const TEXT = {
    fr: {
      title: 'Sentinel · Train', subtitle: 'Recette et diagnostic du module Train', readonly: 'MODE OBSERVATEUR · Aucune correction automatique',
      run: 'Lancer la recette', rerun: 'Relancer', running: 'Analyse en cours…', copy: 'Copier le rapport', copied: 'Rapport copié', copyFail: 'Copie impossible',
      close: 'Fermer', expected: 'Attendu', observed: 'Observé', details: 'Détail', cause: 'Cause probable', last: 'Dernière analyse',
      ownerOnly: 'Accès OWNER ou SUPERVISEUR uniquement.', noReport: 'Aucun rapport disponible.', noFix: 'Sentinel détecte et explique. Il ne modifie rien automatiquement.'
    },
    en: {
      title: 'Sentinel · Train', subtitle: 'Train module QA and diagnostics', readonly: 'OBSERVER MODE · No automatic fixes',
      run: 'Run checks', rerun: 'Run again', running: 'Running checks…', copy: 'Copy report', copied: 'Report copied', copyFail: 'Copy failed',
      close: 'Close', expected: 'Expected', observed: 'Observed', details: 'Details', cause: 'Likely cause', last: 'Last run',
      ownerOnly: 'OWNER or SUPERVISOR access only.', noReport: 'No report available.', noFix: 'Sentinel detects and explains. It does not change anything automatically.'
    },
    it: {
      title: 'Sentinel · Train', subtitle: 'Collaudo e diagnostica del modulo Train', readonly: 'MODALITÀ OSSERVATORE · Nessuna correzione automatica',
      run: 'Avvia collaudo', rerun: 'Ripeti', running: 'Analisi in corso…', copy: 'Copia rapporto', copied: 'Rapporto copiato', copyFail: 'Copia non riuscita',
      close: 'Chiudi', expected: 'Atteso', observed: 'Osservato', details: 'Dettaglio', cause: 'Causa probabile', last: 'Ultima analisi',
      ownerOnly: 'Accesso solo OWNER o SUPERVISOR.', noReport: 'Nessun rapporto disponibile.', noFix: 'Sentinel rileva e spiega. Non modifica nulla automaticamente.'
    },
    es: {
      title: 'Sentinel · Train', subtitle: 'Pruebas y diagnóstico del módulo Train', readonly: 'MODO OBSERVADOR · Sin correcciones automáticas',
      run: 'Ejecutar pruebas', rerun: 'Repetir', running: 'Analizando…', copy: 'Copiar informe', copied: 'Informe copiado', copyFail: 'No se pudo copiar',
      close: 'Cerrar', expected: 'Esperado', observed: 'Observado', details: 'Detalle', cause: 'Causa probable', last: 'Último análisis',
      ownerOnly: 'Acceso solo OWNER o SUPERVISOR.', noReport: 'No hay informe disponible.', noFix: 'Sentinel detecta y explica. No modifica nada automáticamente.'
    }
  };

  function lang() {
    const raw = String(localStorage.getItem('wfgg_train_lang') || localStorage.getItem('wfgg_portal_language') || document.documentElement.lang || 'fr')
      .trim().toLowerCase().replace('_','-').split('-')[0];
    return TEXT[raw] ? raw : 'fr';
  }
  const t = (key) => TEXT[lang()][key] || TEXT.fr[key] || key;
  const token = () => localStorage.getItem(PORTAL_TOKEN_KEY) || '';
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function readJson(key, fallback = null) {
    try { return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback; } catch (_) { return fallback; }
  }

  function currentPlayer() {
    const state = readJson(TRAIN_STATE_KEY, {}) || {};
    const roster = readJson(ROSTER_KEY, []) || [];
    const id = String(state.currentUserId || '');
    return Array.isArray(roster) ? roster.find((row) => String(row?.id || '') === id) || null : null;
  }

  function pseudoOf(player) {
    return String(player?.pseudo || player?.name || player?.nickname || '').trim();
  }

  function installStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      /* WFGG_SENTINEL_TRAIN_ROUND_LAUNCHER_V1 */
      #${BUTTON_ID}{
        width:38px;height:38px;min-width:38px;border-radius:999px;padding:0;margin-left:2px;
        display:inline-grid;place-items:center;vertical-align:middle;cursor:pointer;position:relative;
        border:1px solid rgba(220,196,255,.34);color:#fff;
        background:radial-gradient(circle at 32% 24%,rgba(255,255,255,.18),transparent 34%),linear-gradient(145deg,#5b4678,#241d34 62%,#171521);
        box-shadow:0 7px 20px rgba(20,12,35,.34),inset 0 1px 0 rgba(255,255,255,.12),0 0 0 1px rgba(113,85,154,.12);
        transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease;
        z-index:3;
      }
      #${BUTTON_ID}:active{transform:scale(.93)}
      #${BUTTON_ID}:focus-visible{outline:none;box-shadow:0 0 0 3px rgba(174,132,231,.28),0 7px 20px rgba(20,12,35,.34)}
      #${BUTTON_ID} .wfgg-sentinel-flask{font-size:18px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))}
      #${BUTTON_ID}::after{content:"";position:absolute;width:7px;height:7px;border-radius:50%;right:-1px;bottom:-1px;background:#81788d;border:2px solid #16131d;box-sizing:content-box}
      #${BUTTON_ID}[data-state="ok"]{border-color:rgba(89,197,139,.55);box-shadow:0 7px 20px rgba(20,12,35,.3),0 0 16px rgba(89,197,139,.13),inset 0 1px 0 rgba(255,255,255,.12)}
      #${BUTTON_ID}[data-state="ok"]::after{background:#59c58b}
      #${BUTTON_ID}[data-state="info"]::after{background:#5fa6eb}
      #${BUTTON_ID}[data-state="warning"]{border-color:rgba(231,180,79,.6)}
      #${BUTTON_ID}[data-state="warning"]::after{background:#e7b44f}
      #${BUTTON_ID}[data-state="error"]{border-color:rgba(239,98,98,.66);box-shadow:0 7px 22px rgba(90,20,30,.25),0 0 18px rgba(239,98,98,.13),inset 0 1px 0 rgba(255,255,255,.12)}
      #${BUTTON_ID}[data-state="error"]::after{background:#ef6262}
      .wfgg-sentinel-name-anchor{display:inline-flex!important;align-items:center!important;gap:8px!important;max-width:100%;white-space:nowrap}

      #${OVERLAY_ID}{position:fixed;inset:0;z-index:2147483300;display:flex;align-items:center;justify-content:center;padding:12px;background:rgba(4,6,12,.73);backdrop-filter:blur(10px)}
      #${OVERLAY_ID}.hidden{display:none!important}
      #${OVERLAY_ID} .wfgg-sentinel-dialog{width:min(880px,calc(100vw - 24px));max-height:min(88dvh,850px);overflow:auto;border-radius:24px;padding:18px;color:#f7f3ed;background:linear-gradient(180deg,#151828,#0e111b 72%);border:1px solid rgba(255,255,255,.12);box-shadow:0 30px 90px rgba(0,0,0,.58)}
      #${OVERLAY_ID} .wfgg-sentinel-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
      #${OVERLAY_ID} .wfgg-sentinel-head h2{margin:3px 0 4px;font-size:1.28rem}#${OVERLAY_ID} .wfgg-sentinel-head p{margin:0;color:#aeb6c5;font-size:.88rem}
      #${OVERLAY_ID} .wfgg-sentinel-kicker{font-size:.68rem;letter-spacing:.1em;color:#d5b96f;font-weight:900}
      #${OVERLAY_ID} .wfgg-sentinel-close{width:40px;height:40px;border-radius:13px;border:1px solid rgba(255,255,255,.14);background:#202638;color:#fff;font-size:1.2rem}
      #${OVERLAY_ID} .wfgg-sentinel-readonly{margin:13px 0 11px;padding:9px 11px;border-radius:12px;border:1px solid rgba(221,190,105,.28);background:rgba(221,190,105,.07);color:#e7cf8d;font-size:.74rem;font-weight:850;letter-spacing:.03em}
      #${OVERLAY_ID} .wfgg-sentinel-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:10px 0}
      #${OVERLAY_ID} .wfgg-sentinel-stat{background:#181e2c;border:1px solid rgba(255,255,255,.08);border-radius:13px;padding:9px;text-align:center}#${OVERLAY_ID} .wfgg-sentinel-stat strong{display:block;font-size:1.24rem}#${OVERLAY_ID} .wfgg-sentinel-stat span{font-size:.68rem;color:#aeb5c3}
      #${OVERLAY_ID} .wfgg-sentinel-actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:12px 0 14px}
      #${OVERLAY_ID} .wfgg-sentinel-action{min-height:43px;border-radius:13px;padding:10px 13px;font-weight:850;cursor:pointer}
      #${OVERLAY_ID} .wfgg-sentinel-run{border:0;background:linear-gradient(180deg,#f1d27b,#cfa342);color:#17130d}
      #${OVERLAY_ID} .wfgg-sentinel-copy{border:1px solid rgba(255,255,255,.14);background:#222939;color:#f7f3ed}
      #${OVERLAY_ID} .wfgg-sentinel-time{font-size:.74rem;color:#929bad}
      #${OVERLAY_ID} .wfgg-sentinel-list{display:flex;flex-direction:column;gap:9px}
      #${OVERLAY_ID} .wfgg-sentinel-check{border:1px solid rgba(255,255,255,.09);background:#151b27;border-radius:15px;padding:12px 13px}
      #${OVERLAY_ID} .wfgg-sentinel-check[data-level="error"]{border-color:rgba(239,98,98,.45);background:rgba(116,31,42,.16)}
      #${OVERLAY_ID} .wfgg-sentinel-check[data-level="warning"]{border-color:rgba(231,180,79,.38);background:rgba(115,84,24,.12)}
      #${OVERLAY_ID} .wfgg-sentinel-check[data-level="info"]{border-color:rgba(95,166,235,.28)}
      #${OVERLAY_ID} .wfgg-sentinel-title{display:flex;gap:8px;align-items:flex-start}#${OVERLAY_ID} .wfgg-sentinel-title strong{display:block;line-height:1.3}#${OVERLAY_ID} .wfgg-sentinel-area{display:block;color:#8e99aa;font-size:.69rem;margin-top:2px}
      #${OVERLAY_ID} .wfgg-sentinel-kv{display:grid;grid-template-columns:82px 1fr;gap:4px 8px;margin-top:9px;font-size:.76rem;line-height:1.42}#${OVERLAY_ID} .wfgg-sentinel-kv b{color:#a1a9b8}#${OVERLAY_ID} .wfgg-sentinel-kv span{word-break:break-word}
      #${OVERLAY_ID} .wfgg-sentinel-cause{margin-top:8px;padding:7px 9px;border-radius:9px;background:rgba(255,255,255,.045);font-size:.75rem;line-height:1.42}
      #${OVERLAY_ID} .wfgg-sentinel-foot{margin:13px 1px 2px;color:#858f9f;font-size:.72rem}
      #${OVERLAY_ID} .wfgg-sentinel-repair-head{margin:17px 0 8px;padding-top:13px;border-top:1px solid rgba(255,255,255,.1);font-weight:900;color:#e4c975}#${OVERLAY_ID} .wfgg-sentinel-repair-card{border:1px solid rgba(118,91,160,.42);background:linear-gradient(180deg,rgba(78,57,108,.22),rgba(21,27,39,.92));border-radius:15px;padding:12px 13px;margin-top:9px}#${OVERLAY_ID} .wfgg-sentinel-repair-card[data-verdict^="recommended"]{border-color:rgba(89,197,139,.5);background:linear-gradient(180deg,rgba(35,101,71,.18),rgba(21,27,39,.94))}#${OVERLAY_ID} .wfgg-sentinel-repair-score{float:right;font-weight:950;color:#f1d27b}#${OVERLAY_ID} .wfgg-sentinel-repair-badge{display:inline-block;margin:6px 0;padding:3px 7px;border-radius:999px;background:rgba(255,255,255,.07);font-size:.67rem;font-weight:900;letter-spacing:.04em}
      @media(max-width:520px){#${BUTTON_ID}{width:36px;height:36px;min-width:36px;margin-left:1px}#${OVERLAY_ID}{padding:9px}#${OVERLAY_ID} .wfgg-sentinel-dialog{width:calc(100vw - 18px);max-height:calc(100dvh - 18px);border-radius:20px;padding:15px 13px}#${OVERLAY_ID} .wfgg-sentinel-summary{grid-template-columns:repeat(2,minmax(0,1fr))}#${OVERLAY_ID} .wfgg-sentinel-copy{flex:1}#${OVERLAY_ID} .wfgg-sentinel-kv{grid-template-columns:72px 1fr}}
    `;
    document.head.appendChild(style);
  }

  async function portalFetch(path) {
    const suffix = String(path || '').replace(/^\/api(?=\/|$)/, '');
    const response = await fetch(PORTAL_API + suffix, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${token()}`, 'Accept': 'application/json' },
      credentials: 'omit', cache: 'no-store'
    });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    return { response, data };
  }

  async function loadPortalSourceMap() {
    try {
      const response = await fetch('/sentinel-source-map-v10.json?sentinel=' + Date.now(), {
        method:'GET', cache:'no-store', credentials:'omit'
      });
      if (!response.ok) return null;
      const data = await response.json();
      return data?.version === 'sentinel-portal-source-map-v10' ? data : null;
    } catch (_) { return null; }
  }

  async function confirmAccess() {
    if (!token()) return false;
    try {
      const { response, data } = await portalFetch('/api/me');
      accessRole = String(data?.system?.role || '');
      accessConfirmed = response.ok && ['OWNER', 'SUPERVISOR'].includes(accessRole);
      return accessConfirmed;
    } catch (_) {
      accessRole = '';
      accessConfirmed = false;
      return false;
    }
  }

  function findNameAnchor() {
    /* WFGG_SENTINEL_NAME_ANCHOR_V5
       La carte Moi est la cible autoritative visuelle. On ne dépend plus de la
       forme du roster local pour retrouver le pseudo avant d'afficher le bouton. */
    const anchor = document.querySelector('#appView:not(.hidden) .hero-card .profile-name h2');
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return null;
    return anchor;
  }

  function syncButtonState() {
    const button = document.getElementById(BUTTON_ID);
    if (!button) return;
    const state = lastReport?.summary?.status || '';
    if (state) button.dataset.state = state; else delete button.dataset.state;
  }

  async function launchFromEvent(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    event?.stopImmediatePropagation?.();
    if (launchLocked) return;
    launchLocked = true;
    try {
      await openPopup();
    } finally {
      setTimeout(() => { launchLocked = false; }, 350);
    }
  }

  function installLaunchCapture() {
    if (window.__WFGG_SENTINEL_LAUNCH_CAPTURE_V7__) return;
    window.__WFGG_SENTINEL_LAUNCH_CAPTURE_V7__ = true;
    const handler = (event) => {
      if (event?.target?.closest?.('#' + BUTTON_ID)) launchFromEvent(event);
    };
    document.addEventListener('pointerup', handler, true);
    document.addEventListener('click', handler, true);
  }

  function injectButton() {
    if (!accessConfirmed) return false;
    const anchor = findNameAnchor();
    if (!anchor) return false;
    let button = document.getElementById(BUTTON_ID);
    if (!button) {
      installStyle();
      button = document.createElement('button');
      button.type = 'button';
      button.id = BUTTON_ID;
      button.innerHTML = '<span class="wfgg-sentinel-flask" aria-hidden="true">🧪</span>';
      button.title = t('title');
      button.setAttribute('aria-label', t('title'));
      button.addEventListener('click', launchFromEvent, true);
    }
    if (lastAnchor !== anchor || button.parentElement !== anchor) {
      anchor.classList.add('wfgg-sentinel-name-anchor');
      anchor.appendChild(button);
      lastAnchor = anchor;
    }
    syncButtonState();
    return true;
  }

  function popup() {
    let root = document.getElementById(OVERLAY_ID);
    if (root) return root;
    installStyle();
    root = document.createElement('div');
    root.id = OVERLAY_ID;
    root.className = 'hidden';
    root.innerHTML = `
      <section class="wfgg-sentinel-dialog" role="dialog" aria-modal="true" aria-labelledby="wfggTrainSentinelTitle">
        <header class="wfgg-sentinel-head"><div><div class="wfgg-sentinel-kicker">WfGg · SENTINEL</div><h2 id="wfggTrainSentinelTitle"></h2><p id="wfggTrainSentinelSubtitle"></p></div><button class="wfgg-sentinel-close" type="button">×</button></header>
        <div class="wfgg-sentinel-readonly" id="wfggTrainSentinelReadonly"></div>
        <div class="wfgg-sentinel-summary" id="wfggTrainSentinelSummary"></div>
        <div class="wfgg-sentinel-actions"><button class="wfgg-sentinel-action wfgg-sentinel-run" id="wfggTrainSentinelRun" type="button"></button><button class="wfgg-sentinel-action wfgg-sentinel-copy" id="wfggTrainSentinelCopy" type="button">📋</button><span class="wfgg-sentinel-time" id="wfggTrainSentinelTime"></span></div>
        <div class="wfgg-sentinel-list" id="wfggTrainSentinelList"></div>
        <div class="wfgg-sentinel-foot" id="wfggTrainSentinelFoot"></div>
      </section>`;
    document.body.appendChild(root);
    root.querySelector('.wfgg-sentinel-close').addEventListener('click', closePopup);
    root.addEventListener('click', (event) => { if (event.target === root) closePopup(); });
    root.querySelector('#wfggTrainSentinelRun').addEventListener('click', runSentinel);
    root.querySelector('#wfggTrainSentinelCopy').addEventListener('click', copyReport);
    translatePopup();
    return root;
  }

  function translatePopup() {
    const root = document.getElementById(OVERLAY_ID);
    if (!root) return;
    root.querySelector('#wfggTrainSentinelTitle').textContent = t('title');
    root.querySelector('#wfggTrainSentinelSubtitle').textContent = t('subtitle');
    root.querySelector('#wfggTrainSentinelReadonly').textContent = `🔒 ${t('readonly')}`;
    root.querySelector('#wfggTrainSentinelRun').textContent = lastReport ? t('rerun') : t('run');
    root.querySelector('#wfggTrainSentinelCopy').textContent = `📋 ${t('copy')}`;
    root.querySelector('#wfggTrainSentinelFoot').textContent = t('noFix');
  }

  async function openPopup() {
    if (!accessConfirmed && !(await confirmAccess())) return;
    const root = popup();
    translatePopup();
    root.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    if (lastReport) renderReport(lastReport); else runSentinel();
  }

  function closePopup() {
    document.getElementById(OVERLAY_ID)?.classList.add('hidden');
    document.body.style.overflow = '';
  }

  function localCheck(id, level, title, expected, observed, detail = '', probableCause = '') {
    return { id, area: 'Train · appareil', level, title, expected, observed, detail, probableCause };
  }

  async function localChecks() {
    const items = [];
    const state = readJson(TRAIN_STATE_KEY, {}) || {};
    const roster = readJson(ROSTER_KEY, []) || [];
    const currentId = String(state.currentUserId || '');
    const rosterHasMe = Array.isArray(roster) && roster.some((row) => String(row?.id || '') === currentId);
    items.push(localCheck('train-local-user', currentId && rosterHasMe ? 'ok' : 'error', 'Identité locale Train', 'currentUserId présent dans le roster', currentId ? `${currentId.slice(0,24)} · roster=${rosterHasMe}` : 'absente', '', currentId && rosterHasMe ? '' : 'Le frontend Train ne dispose pas d’une identité locale cohérente.'));

    let probe = null;
    try { probe = JSON.parse(sessionStorage.getItem('wfgg_train_bridge_probe_v1') || 'null'); } catch (_) {}
    items.push(localCheck('train-portal-bridge-probe', probe?.ok ? 'ok' : 'warning', 'Dernier probe Portail → Train', 'ok=true', probe ? `ok=${Boolean(probe.ok)} · status=${probe.status ?? '—'} · code=${probe.code || '—'}` : 'aucun probe', probe?.bridge ? `bridge=${probe.bridge}` : '', probe?.ok ? '' : 'La dernière ouverture intégrée n’a pas confirmé un snapshot Train valide.'));

    const notificationSupported = 'Notification' in window;
    const permission = notificationSupported ? Notification.permission : 'unsupported';
    items.push(localCheck('train-notification-permission', permission === 'granted' ? 'ok' : (permission === 'default' ? 'warning' : 'error'), 'Autorisation notifications', 'granted', permission, '', permission === 'denied' ? 'Android/iOS ou le navigateur bloque les notifications.' : ''));

    if ('serviceWorker' in navigator) {
      let regs = [];
      try { regs = await navigator.serviceWorker.getRegistrations(); } catch (_) {}
      const reg = regs.find((r) => {
        try { return new URL(r.active?.scriptURL || r.waiting?.scriptURL || '').pathname === '/train/wfgg-push-sw.js'; } catch (_) { return false; }
      });
      items.push(localCheck('train-push-sw', reg?.active ? 'ok' : 'error', 'Service Worker Push Train', '/train/wfgg-push-sw.js actif', reg?.active ? 'actif' : 'absent/inactif', '', reg?.active ? '' : 'Le canal Push ne peut pas afficher les notifications tant que le Service Worker n’est pas actif.'));
      if (reg?.pushManager) {
        let sub = null; try { sub = await reg.pushManager.getSubscription(); } catch (_) {}
        items.push(localCheck('train-push-subscription', sub?.endpoint ? 'ok' : 'error', 'Abonnement Push appareil', 'endpoint présent', sub?.endpoint ? `${String(sub.endpoint).slice(0,72)}…` : 'absent', '', sub?.endpoint ? '' : 'Aucun abonnement Push utilisable sur cet appareil.'));
      }
    }
    /* train-ui-functional-contract-v13
       Premier niveau : inventaire des actions exposées. Le second niveau V13
       exécute ensuite une recette comportementale et géométrique en lecture seule. */
    const uiFunctions = [
      'addCalendar','addAllCalendar','toggleAlerts','testLocalNotification','testLocalPushNotification','testPushReminder','sentinelUiProbe','notificationSettingsIntentPlan',
      'changeWeek','openExchange','publishMarketExchange','cancelMarketExchange','pickMyDateForMarket','executeMarketSwap',
      'markUnavailable','showUnavailableChoice','openUnavailableDayPicker','saveUnavailableDayFromPicker','openUnavailablePeriod','saveUnavailablePeriod','saveUnavailableDay','removeUnavailableRange','removeUnavailable','showUnavailable',
      'toggleRotation','showRotationStatus','openProfileInfo','openSelfProfileEdit','saveSelfProfile','openChangePin','changeMyPin','changeLanguage','setPortalLanguage',
      'saveAdminSettings','saveDay','clearDayOverride','adminToggleRotation','filterMembers','searchMembers','openMemberForm','saveMemberForm','deleteMember','renderRotationOrder','moveRotation','saveRotationRanks','resetMemberPin','downloadGeneratedCodesCsv','clearGeneratedCodes',
      'generateMessage','nextMessage','copyGeneratedMessage','openAdminSection','renderAdminHome','togglePresenceList','refreshAdminPresence',
      'openGameHelp','openGameLink','addGameLinkDraft','removeGameLinkDraft','saveGameLinks',
      'openAdminAnalytics','renderAnalyticsMenu','openAnalyticsSub','renderTrainHistory','setAnalyticsRotationDays','setAnalyticsRotationPool','setAnalyticsRotationSort','setAnalyticsActivitySort','setAnalyticsSettingsFilter','setAnalyticsFilter','setAnalyticsHistorySort','setAnalyticsSearch'
    ];
    const missingUi = uiFunctions.filter((name) => typeof window.W?.[name] !== 'function');
    items.push(localCheck(
      'train-ui-functional-contract', missingUi.length ? 'error' : 'ok',
      'Contrat des fonctionnalités de l’interface',
      `${uiFunctions.length} actions Train exposées`,
      missingUi.length ? `${missingUi.length} manquante(s): ${missingUi.slice(0,12).join(', ')}` : `${uiFunctions.length}/${uiFunctions.length} présentes`,
      'Couvre calendrier, alertes, échanges, indisponibilités, statut, profil/PIN/langue, administration, présence, messages, liens et statistiques.',
      missingUi.length ? 'Une fonction visible dans l’interface n’est plus exposée par app.v15.' : ''
    ));
    /* train-local-notification-handler-v12
       Vérifie le branchement exact du bouton d'affichage local : le HTML appelle
       W.testLocalNotification(), qui doit donc être exporté par app.v15. */
    const localNotificationHandler = typeof window.W?.testLocalNotification === 'function';
    items.push(localCheck(
      'train-local-notification-handler',localNotificationHandler?'ok':'error','Bouton test notification locale',
      'W.testLocalNotification disponible',localNotificationHandler?'câblé':'absent',
      'Ce contrôle distingue le test local Service Worker du test Push serveur.',
      localNotificationHandler?'':'Le bouton de test local appelle une fonction non exposée.'
    ));
    /* WFGG_SENTINEL_UI_SIMULATION_V13 */
    let uiProbe=null;
    try{uiProbe=typeof window.W?.sentinelUiProbe==='function'?await window.W.sentinelUiProbe():null;}catch(error){uiProbe={readonly:true,simFailed:[{id:'probe-runtime',detail:String(error?.message||error)}],graphicFailed:[],simulations:[],graphics:[]};}
    const simTotal=uiProbe?.simulations?.length||0,simFailed=uiProbe?.simFailed||[];
    items.push(localCheck(
      'train-ui-behavior-simulation',uiProbe&&uiProbe.readonly&&simTotal>0&&!simFailed.length?'ok':'error','Simulation réelle des boutons',
      'Clics non destructifs → écran/modale attendu, sans écriture',uiProbe?`${simTotal-simFailed.length}/${simTotal} scénarios conformes · readonly=${Boolean(uiProbe.readonly)}`:'probe absent',
      simFailed.length?simFailed.map(x=>`${x.id}: ${x.detail||'échec'}`).join(' · '):'Profil, navigation Alertes, indisponibilités, rotation et réglages notifications simulés.',
      simFailed.length?'Un bouton existe mais son comportement réel ou sa cible DOM ne correspond plus au contrat.':''
    ));
    const graphicTotal=uiProbe?.graphics?.length||0,graphicFailed=uiProbe?.graphicFailed||[];
    items.push(localCheck(
      'train-ui-graphic-audit',uiProbe&&graphicTotal>0&&!graphicFailed.length?'ok':'error','Analyse graphique des contrôles',
      'Contrôles critiques visibles, dans le viewport, cliquables et non recouverts',uiProbe?`${graphicTotal-graphicFailed.length}/${graphicTotal} éléments conformes`:'probe absent',
      graphicFailed.length?graphicFailed.map(x=>`${x.id}: visible=${x.visible} viewport=${x.inViewport} exposé=${x.exposed} pointer=${x.pointer} ${x.width||0}x${x.height||0}`).join(' · '):'Géométrie contrôlée avec getBoundingClientRect + elementsFromPoint en ignorant uniquement la surcouche Sentinel.',
      graphicFailed.length?'Un contrôle peut être hors écran, masqué, recouvert ou non cliquable sur cet appareil.':''
    ));
    const settingsPlan=uiProbe?.notificationSettings;
    const settingsOk=!settingsPlan?.android||(simFailed.every(x=>x.id!=='notification-settings-action')&&String(settingsPlan?.appNotifications||'').includes('browser_fallback_url'));
    items.push(localCheck(
      'train-notification-settings-action',settingsOk?'ok':'error','Bouton Modifier les réglages Android',
      'Lien intent direct depuis le geste utilisateur + retour WfGg si Android refuse',settingsPlan?.android?(settingsOk?`${settingsPlan.packageName} · intent + fallback câblés`:'câblage incomplet'):'non Android',
      'Sentinel ne déclenche pas volontairement l’Intent système : il valide le lien réellement rendu et son fallback sans quitter WfGg.',
      settingsOk?'':'Le bouton Modifier peut rester sans effet ou quitter la page sans aide de secours.'
    ));
    const calendarRuntime = typeof Blob === 'function' && typeof URL?.createObjectURL === 'function' && typeof window.W?.addCalendar === 'function' && typeof window.W?.addAllCalendar === 'function';
    items.push(localCheck(
      'train-calendar-runtime',calendarRuntime?'ok':'error','Export calendrier téléphone',
      'Blob + URL.createObjectURL + fonctions ICS disponibles',calendarRuntime?'disponible':'incomplet','Test de capacité uniquement; aucun fichier calendrier n’est téléchargé par Sentinel.',
      calendarRuntime?'':'Le navigateur ou le code client ne peut pas produire les fichiers calendrier.'
    ));
    return items;
  }

  /* WFGG_SENTINEL_LOCAL_REPAIR_V12
     Les anomalies exclusivement visibles sur l'appareil reçoivent elles aussi
     des hypothèses de correction. Rien n'est exécuté : ces objets sont des
     recommandations destinées à une deuxième validation humaine. */
  function localRepairCandidateV12(input){
    return {...input,readonly:true,applied:false,source:input.source||null,evidence:input.evidence||[],risks:input.risks||[],manualValidation:input.manualValidation||[]};
  }
  function localRepairCandidatesV12(items,portalSourceMap){
    const out=[];
    const bad=new Map((items||[]).filter(x=>x&&(x.level==='error'||x.level==='warning')).map(x=>[x.id,x]));
    const portalSource=(file,fn)=>({repository:'chachasan090375/WfGg',file,function:fn||null,line:portalSourceMap?.files?.[file]?.functions?.[fn]?.line||null,sourceCommit:portalSourceMap?.sourceCommit||null});
    if(bad.has('train-local-notification-handler'))out.push(localRepairCandidateV12({
      id:'repair-local-notification-export-v12',title:'Rétablir le câblage du test notification locale',score:97,verdict:'recommended',
      target:'frontend/train-native/app.v15.js :: window.W',proposedChange:'Exporter testLocalNotification dans window.W sans remplacer le test Push serveur.',
      simulation:{handlerPresent:typeof window.W?.testLocalNotification==='function',expectedAfterPatch:true},
      evidence:['Le bouton appelle W.testLocalNotification().','Le contrôle local vérifie directement cet export.'],risks:['Ne pas aliaser vers le test Push serveur : les deux tests ont des rôles différents.'],
      manualValidation:['Relancer Sentinel.','Appuyer manuellement sur Tester l’affichage local.'],source:portalSource('frontend/train-native/app.v15.js','testLocalNotification')
    }));
    if(bad.has('train-push-sw'))out.push(localRepairCandidateV12({
      id:'repair-push-sw-register-v12',title:'Réenregistrer le Service Worker Push Train',score:94,verdict:'recommended-manual',
      target:'/train/wfgg-push-sw.js',proposedChange:'Réenregistrer le Service Worker Push sous le scope /train/ puis vérifier son état active.',
      simulation:{serviceWorkerSupported:'serviceWorker' in navigator},evidence:['Le canal Push local est absent ou inactif.'],risks:['Ne pas supprimer la session Portail ni les autres Service Workers du site.'],manualValidation:['Vérifier active puis relancer Sentinel.']
    }));
    if(bad.has('train-push-subscription'))out.push(localRepairCandidateV12({
      id:'repair-local-push-subscribe-v12',title:'Recréer l’abonnement Push de cet appareil',score:95,verdict:'recommended-manual',
      target:'PushManager + /api/push/subscribe',proposedChange:'Créer un abonnement avec la clé VAPID serveur courante puis l’enregistrer côté Train.',
      simulation:{permission:('Notification' in window)?Notification.permission:'unsupported'},evidence:['Aucun endpoint Push local utilisable.'],risks:['Une autorisation refusée par le navigateur bloque cette correction.'],manualValidation:['Vérifier ensuite l’abonnement serveur et envoyer explicitement un Push de test.']
    }));
    if(bad.has('train-notification-permission'))out.push(localRepairCandidateV12({
      id:'repair-notification-permission-v12',title:'Autoriser les notifications pour WfGg',score:93,verdict:'recommended-manual',
      target:'Réglages navigateur / Android',proposedChange:'Autoriser les notifications pour wfgg.pages.dev puis refaire l’abonnement Push.',
      simulation:{permission:('Notification' in window)?Notification.permission:'unsupported'},evidence:['La permission système/navigateur n’est pas granted.'],risks:['Sentinel ne peut pas changer une permission système.'],manualValidation:['Revenir dans Train puis relancer Sentinel.']
    }));
    if(bad.has('train-ui-functional-contract'))out.push(localRepairCandidateV12({
      id:'repair-ui-export-contract-v12',title:'Rétablir les actions Train manquantes dans window.W',score:90,verdict:'recommended-manual',
      target:'frontend/train-native/app.v15.js :: window.W',proposedChange:'Réexporter uniquement les fonctions signalées manquantes, sans modifier leur logique métier.',
      simulation:{contractCheck:'typeof window.W[name] === function'},evidence:['Une action visible n’est plus exposée par le runtime.'],risks:['Une fonction réellement supprimée ne doit pas être recréée par simple alias.'],manualValidation:['Comparer la liste des fonctions manquantes avec leurs handlers réels.'],source:portalSource('frontend/train-native/app.v15.js','window.W')
    }));
    if(bad.has('train-ui-behavior-simulation'))out.push(localRepairCandidateV12({
      id:'repair-ui-behavior-v13',title:'Réparer le comportement réel du contrôle défaillant',score:96,verdict:'recommended',
      target:'frontend/train-native/app.v15.js :: handler + DOM cible',proposedChange:'Corriger le handler ou la cible DOM signalée par la simulation, sans modifier les règles métier.',simulation:{readonly:true,probe:'sentinelUiProbe'},evidence:['Le contrôle existe mais le clic simulé n’aboutit pas au résultat visuel attendu.'],risks:['Ne jamais déclencher une mutation réelle depuis Sentinel.'],manualValidation:['Relancer Sentinel V13 puis refaire le clic manuel concerné.']
    }));
    if(bad.has('train-ui-graphic-audit'))out.push(localRepairCandidateV12({
      id:'repair-ui-graphic-v13',title:'Corriger la géométrie ou la couche qui masque le contrôle',score:94,verdict:'recommended',
      target:'frontend/train-native/styles.css / DOM Train',proposedChange:'Corriger visibilité, viewport, pointer-events, z-index ou dimensions uniquement pour les éléments signalés.',simulation:{readonly:true,geometry:'getBoundingClientRect + elementsFromPoint'},evidence:['Le contrôle n’est pas réellement atteignable sur cet appareil.'],risks:['Tester mobile et desktop avant de modifier un z-index global.'],manualValidation:['Relancer Sentinel sur le même téléphone.']
    }));
    if(bad.has('train-notification-settings-action'))out.push(localRepairCandidateV12({
      id:'repair-notification-settings-action-v13',title:'Rétablir le lien Android vers les réglages notifications',score:98,verdict:'recommended',
      target:'app.v15.js :: notificationSettingsIntentPlan',proposedChange:'Rendre un lien intent: directement cliquable avec APP_NOTIFICATION_SETTINGS et browser_fallback_url same-origin.',simulation:{readonly:true,externalIntentNotLaunched:true},evidence:['Sentinel valide le href rendu sans ouvrir les paramètres système.'],risks:['Chrome peut refuser une activité Android non BROWSABLE ; le fallback WfGg doit toujours rester disponible.'],manualValidation:['Appuyer sur Modifier sur Android puis vérifier le retour guidé si Android refuse.']
    }));
    if(bad.has('train-calendar-runtime'))out.push(localRepairCandidateV12({
      id:'repair-calendar-runtime-v12',title:'Rétablir le runtime d’export calendrier',score:78,verdict:'alternative',
      target:'app.v15.js :: addCalendar/addAllCalendar',proposedChange:'Vérifier Blob, URL.createObjectURL et les deux handlers ICS avant de toucher au format calendrier.',
      simulation:{blob:typeof Blob==='function',objectUrl:typeof URL?.createObjectURL==='function',addCalendar:typeof window.W?.addCalendar==='function',addAllCalendar:typeof window.W?.addAllCalendar==='function'},
      evidence:['Sentinel peut isoler le maillon runtime absent.'],risks:['Le problème peut venir du navigateur plutôt que du code.'],manualValidation:['Tester un export ICS manuel après correction.']
    }));
    return out;
  }

  async function runSentinel() {
    const root = popup();
    const run = root.querySelector('#wfggTrainSentinelRun');
    const list = root.querySelector('#wfggTrainSentinelList');
    run.disabled = true;
    run.textContent = t('running');
    list.innerHTML = `<div style="padding:18px;text-align:center;color:#9da6b5">⏳ ${esc(t('running'))}</div>`;
    try {
      const [serverResult, local, portalSourceMap] = await Promise.all([portalFetch('/api/sentinel/run'), localChecks(), loadPortalSourceMap()]);
      const { response, data } = serverResult;
      if (response.status === 403) { accessConfirmed = false; accessRole = ''; throw new Error(t('ownerOnly')); }
      if (!response.ok && !Array.isArray(data?.checks)) throw new Error(`${data?.error || 'Sentinel server error'} · HTTP ${response.status}`);
      const serverChecks=Array.isArray(data?.checks) ? data.checks : [];
      const liveSnapshotOk=serverChecks.some(item=>item?.id==='train-snapshot'&&item?.level==='ok');
      const staleProbe=local.find(item=>item?.id==='train-portal-bridge-probe');
      if(liveSnapshotOk&&staleProbe&&staleProbe.level==='warning'){
        const oldObserved=staleProbe.observed;
        staleProbe.level='ok';
        staleProbe.title='Probe Portail → Train (historique résolu)';
        staleProbe.expected='Le snapshot courant doit être valide';
        staleProbe.observed='Snapshot courant HTTP 200 · ancien probe: '+oldObserved;
        staleProbe.detail='L’ancien échec est conservé comme trace locale mais il n’est plus une anomalie active.';
        staleProbe.probableCause='';
      }
      if(portalSourceMap){
        local.push({
          id:'sentinel-source-build',area:'Sentinel · sources',level:'ok',title:'Index des sources Portail',
          expected:'Build courant localisable',
          observed:'commit '+String(portalSourceMap.sourceCommit||'').slice(0,12)+' · '+Object.keys(portalSourceMap.files||{}).length+' fichier(s) indexé(s)',
          detail:'Sentinel peut rattacher ses diagnostics Portail aux lignes du build déployé.',probableCause:''
        });
      }
      const checks = [...serverChecks, ...local];
      const backendCandidates=Array.isArray(data?.repairPlan?.candidates)?data.repairPlan.candidates:[];
      const localCandidates=localRepairCandidatesV12(local,portalSourceMap);
      const repairCandidates=[...backendCandidates,...localCandidates].sort((a,b)=>Number(b?.score||0)-Number(a?.score||0)||String(a?.id||'').localeCompare(String(b?.id||'')));
      const repairRecommended=repairCandidates.find(x=>x?.verdict==='recommended'||x?.verdict==='recommended-manual')||null;
      const repairPlan={
        version:'sentinel-repair-plan-v12',readonly:true,applied:false,
        server:data?.repairPlan||null,candidates:repairCandidates,recommended:repairRecommended
      };
      const counts = { ok:0, info:0, warning:0, error:0 };
      checks.forEach((item) => { counts[item.level] = (counts[item.level] || 0) + 1; });
      const status = counts.error ? 'error' : counts.warning ? 'warning' : counts.info ? 'info' : 'ok';
      lastReport = { ...data, checks, repairPlan, portalSourceMap, summary:{ status, counts, total:checks.length }, finishedAt:data?.finishedAt || new Date().toISOString(), source:'train' };
      renderReport(lastReport);
    } catch (error) {
      list.innerHTML = `<article class="wfgg-sentinel-check" data-level="error"><div class="wfgg-sentinel-title"><span>🔴</span><div><strong>Sentinel</strong><span class="wfgg-sentinel-area">Train</span></div></div><div class="wfgg-sentinel-cause">${esc(error?.message || error)}</div></article>`;
    } finally {
      run.disabled = false;
      run.textContent = lastReport ? t('rerun') : t('run');
    }
  }

  function icon(level) { return level === 'error' ? '🔴' : level === 'warning' ? '🟠' : level === 'info' ? '🔵' : '🟢'; }

  function renderReport(report) {
    const root = popup();
    translatePopup();
    const counts = report?.summary?.counts || {ok:0,info:0,warning:0,error:0};
    const labels = {ok:'Conforme',info:'Information',warning:'Anomalie',error:'Erreur'};
    root.querySelector('#wfggTrainSentinelSummary').innerHTML = ['ok','info','warning','error'].map((key) => `<div class="wfgg-sentinel-stat"><strong>${Number(counts[key] || 0)}</strong><span>${esc(labels[key])}</span></div>`).join('');
    const when = report?.finishedAt ? new Date(report.finishedAt) : new Date();
    root.querySelector('#wfggTrainSentinelTime').textContent = `${t('last')} · ${when.toLocaleString()}`;
    const order = {error:0,warning:1,info:2,ok:3};
    const checks = [...(report?.checks || [])].sort((a,b) => (order[a.level] ?? 9) - (order[b.level] ?? 9));
    root.querySelector('#wfggTrainSentinelList').innerHTML = checks.map((item) => `
      <article class="wfgg-sentinel-check" data-level="${esc(item.level || 'info')}">
        <div class="wfgg-sentinel-title"><span>${icon(item.level)}</span><div><strong>${esc(item.title || item.id || 'Contrôle')}</strong><span class="wfgg-sentinel-area">${esc(item.area || 'Sentinel')} · ${esc(item.id || '')}</span></div></div>
        <div class="wfgg-sentinel-kv"><b>${esc(t('expected'))}</b><span>${esc(item.expected || '—')}</span><b>${esc(t('observed'))}</b><span>${esc(item.observed || '—')}</span>${item.detail ? `<b>${esc(t('details'))}</b><span>${esc(item.detail)}</span>` : ''}${item.source ? `<b>Source</b><span>${esc([item.source.repository,item.source.file+(item.source.line?':'+item.source.line:''),item.source.function?'fonction '+item.source.function:'',item.source.sourceCommit?'commit '+String(item.source.sourceCommit).slice(0,12):''].filter(Boolean).join(' · '))}</span>` : ''}${item.stack ? `<b>Pile</b><span>${esc(item.stack)}</span>` : ''}</div>
        ${item.probableCause ? `<div class="wfgg-sentinel-cause"><b>${esc(t('cause'))} :</b> ${esc(item.probableCause)}</div>` : ''}
      </article>`).join('');
    renderRepairPlanV12(report);
    syncButtonState();
  }

  function repairVerdictLabelV12(value){
    return value==='recommended'?'RECOMMANDÉ':value==='recommended-manual'?'RECOMMANDÉ · VALIDATION MANUELLE':value==='alternative'?'ALTERNATIVE':value==='manual-review'?'REVUE MANUELLE':'REJETÉ';
  }
  function repairJsonV12(value){try{return JSON.stringify(value)}catch(_){return String(value??'—')}}
  function renderRepairPlanV12(report){
    const list=popup().querySelector('#wfggTrainSentinelList');
    const repairs=Array.isArray(report?.repairPlan?.candidates)?report.repairPlan.candidates:[];
    if(!repairs.length)return;
    const cards=repairs.slice(0,8).map(item=>`<article class="wfgg-sentinel-repair-card" data-verdict="${esc(item.verdict||'')}"><span class="wfgg-sentinel-repair-score">${Number(item.score||0)}/100</span><strong>${esc(item.title||item.id||'Correctif')}</strong><br><span class="wfgg-sentinel-repair-badge">${esc(repairVerdictLabelV12(item.verdict))}</span><div class="wfgg-sentinel-kv"><b>Cible</b><span>${esc(item.target||'—')}</span><b>Proposition</b><span>${esc(item.proposedChange||'—')}</span><b>Simulation</b><span>${esc(repairJsonV12(item.simulation))}</span>${item.risks?.length?`<b>Risques</b><span>${esc(item.risks.join(' · '))}</span>`:''}${item.manualValidation?.length?`<b>Validation</b><span>${esc(item.manualValidation.join(' · '))}</span>`:''}</div>${item.source?`<div class="wfgg-sentinel-cause"><b>Source :</b> ${esc([item.source.repository,item.source.file+(item.source.line?':'+item.source.line:''),item.source.function?'fonction '+item.source.function:''].filter(Boolean).join(' · '))}</div>`:''}</article>`).join('');
    list.insertAdjacentHTML('beforeend',`<div class="wfgg-sentinel-repair-head">🧭 CORRECTIFS SIMULÉS (${repairs.length}) · AUCUN CORRECTIF APPLIQUÉ</div>${cards}`);
  }

  function reportText() {
    if (!lastReport) return `WFGG_SENTINEL_REPORT_V6\n${t('noReport')}`;
    const lines = [
      'WFGG_SENTINEL_REPORT_V6',
      'WfGg · Sentinel · Train',
      `Copié le: ${new Date().toISOString()}`,
      `Analyse: ${lastReport.finishedAt || '—'}`,
      `URL: ${location.href}`,
      `User-Agent: ${navigator.userAgent}`,
      `Statut global: ${lastReport.summary?.status || '—'}`,
      `Résumé: ok=${lastReport.summary?.counts?.ok || 0}; info=${lastReport.summary?.counts?.info || 0}; warning=${lastReport.summary?.counts?.warning || 0}; error=${lastReport.summary?.counts?.error || 0}`,
      `Build Portail: ${lastReport.portalSourceMap?.sourceCommit || '—'} · Sentinel ${VERSION}`,
      '',
      `CONTRÔLES (${lastReport.checks?.length || 0})`
    ];
    for (const item of (lastReport.checks || [])) {
      lines.push('', `[${String(item.level || 'info').toUpperCase()}] ${item.title || item.id || 'Contrôle'}`);
      if (item.area || item.id) lines.push(`Zone: ${item.area || 'Sentinel'} · ${item.id || ''}`);
      lines.push(`Attendu: ${item.expected || '—'}`);
      lines.push(`Observé: ${item.observed || '—'}`);
      if (item.detail) lines.push(`Détail: ${item.detail}`);
      if (item.source) lines.push('Source: '+[item.source.repository,item.source.file+(item.source.line?':'+item.source.line:''),item.source.function?'fonction '+item.source.function:'',item.source.sourceCommit?'commit '+String(item.source.sourceCommit).slice(0,12):''].filter(Boolean).join(' · '));
      if (item.stack) lines.push('Pile: '+String(item.stack).replace(/\n/g,' | '));
      if (item.probableCause) lines.push(`Cause probable: ${item.probableCause}`);
    }
    const repairs=Array.isArray(lastReport.repairPlan?.candidates)?lastReport.repairPlan.candidates:[];
    lines.push('', `CORRECTIFS SIMULÉS (${repairs.length})`);
    for(const item of repairs){
      lines.push('', `[${repairVerdictLabelV12(item.verdict)}] ${item.title||item.id||'Correctif'} · score=${Number(item.score||0)}/100`);
      if(item.target)lines.push(`Cible: ${item.target}`);
      if(item.proposedChange)lines.push(`Correctif proposé: ${item.proposedChange}`);
      if(item.simulation)lines.push(`Simulation: ${repairJsonV12(item.simulation)}`);
      if(item.evidence?.length)lines.push(`Preuves: ${item.evidence.join(' | ')}`);
      if(item.risks?.length)lines.push(`Risques: ${item.risks.join(' | ')}`);
      if(item.manualValidation?.length)lines.push(`Validation manuelle: ${item.manualValidation.join(' | ')}`);
      if(item.source)lines.push('Source correctif: '+[item.source.repository,item.source.file+(item.source.line?':'+item.source.line:''),item.source.function?'fonction '+item.source.function:'',item.source.sourceCommit?'commit '+String(item.source.sourceCommit).slice(0,12):''].filter(Boolean).join(' · '));
      lines.push('Appliqué: NON');
    }
    lines.push('', 'MODE: OBSERVATEUR / LECTURE SEULE', 'AUCUN CORRECTIF APPLIQUÉ PAR SENTINEL. Toute proposition nécessite une deuxième validation manuelle.');
    return lines.join('\n');
  }

  async function writeClipboard(text) {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      try { await navigator.clipboard.writeText(text); return true; } catch (_) {}
    }
    const area = document.createElement('textarea'); area.value = text; area.setAttribute('readonly',''); area.style.cssText='position:fixed;opacity:0;pointer-events:none'; document.body.appendChild(area); area.select(); area.setSelectionRange(0,area.value.length);
    let ok = false; try { ok = document.execCommand('copy'); } catch (_) {} area.remove(); return ok;
  }

  async function copyReport() {
    const button = popup().querySelector('#wfggTrainSentinelCopy');
    const ok = await writeClipboard(reportText());
    button.textContent = ok ? `✅ ${t('copied')}` : `❌ ${t('copyFail')}`;
    setTimeout(() => { button.textContent = `📋 ${t('copy')}`; }, 2000);
  }

  async function init() {
    installStyle();
    installLaunchCapture();
    /* WFGG_SENTINEL_ACCESS_RETRY_V7
       OWNER et SUPERVISOR sont validés côté serveur. Le lanceur reste absent
       pour tous les autres profils, quel que soit leur rang d'alliance. */
    let accessTry = 0;
    while (accessTry < 10 && !(await confirmAccess())) {
      accessTry += 1;
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    if (!accessConfirmed) {
      console.warn('WFGG_SENTINEL_ACCESS_V7=NOT_CONFIRMED');
      return;
    }
    console.info('WFGG_SENTINEL_ACCESS_V7=CONFIRMED role=' + accessRole);
    let tries = 0;
    const timer = setInterval(() => { tries += 1; if (injectButton() || tries > 140) clearInterval(timer); }, 120);
    const observer = new MutationObserver(() => { if (accessConfirmed) injectButton(); });
    observer.observe(document.documentElement,{childList:true,subtree:true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true}); else init();
})();
