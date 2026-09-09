(() => {
  'use strict';

  const VERSION = 'sentinel-owner-v1';
  const STORAGE_TOKEN = 'wfgg_portal_session';
  const STORAGE_LANG = 'wfgg_portal_language';
  let ownerConfirmed = false;
  let lastReport = null;

  const TEXT = {
    fr: {
      menu: 'Sentinel', title: 'Sentinel · Recette & diagnostic', subtitle: 'Contrôle qualité WfGg réservé au propriétaire.',
      readonly: 'MODE OBSERVATEUR · Aucune correction automatique', run: 'Lancer la recette', rerun: 'Relancer', running: 'Analyse en cours…',
      close: 'Fermer', total: 'contrôles', ok: 'Conforme', info: 'Information', warning: 'Anomalie', error: 'Erreur bloquante',
      expected: 'Attendu', observed: 'Observé', cause: 'Cause probable', details: 'Détail', last: 'Dernière analyse',
      serverError: 'Sentinel n’a pas pu terminer la recette serveur.', ownerOnly: 'Accès OWNER uniquement.', localArea: 'Téléphone / navigateur',
      noFix: 'Sentinel détecte et explique. Il ne modifie ni le planning, ni les joueurs, ni les rotations.'
    },
    en: {
      menu: 'Sentinel', title: 'Sentinel · QA & diagnostics', subtitle: 'WfGg quality control reserved for the owner.',
      readonly: 'OBSERVER MODE · No automatic fixes', run: 'Run checks', rerun: 'Run again', running: 'Running checks…',
      close: 'Close', total: 'checks', ok: 'Compliant', info: 'Information', warning: 'Anomaly', error: 'Blocking error',
      expected: 'Expected', observed: 'Observed', cause: 'Likely cause', details: 'Details', last: 'Last run',
      serverError: 'Sentinel could not complete the server checks.', ownerOnly: 'OWNER access only.', localArea: 'Phone / browser',
      noFix: 'Sentinel detects and explains. It does not change the schedule, players or rotations.'
    },
    it: {
      menu: 'Sentinel', title: 'Sentinel · Collaudo e diagnostica', subtitle: 'Controllo qualità WfGg riservato al proprietario.',
      readonly: 'MODALITÀ OSSERVATORE · Nessuna correzione automatica', run: 'Avvia collaudo', rerun: 'Ripeti', running: 'Analisi in corso…',
      close: 'Chiudi', total: 'controlli', ok: 'Conforme', info: 'Informazione', warning: 'Anomalia', error: 'Errore bloccante',
      expected: 'Atteso', observed: 'Osservato', cause: 'Causa probabile', details: 'Dettaglio', last: 'Ultima analisi',
      serverError: 'Sentinel non ha potuto completare il collaudo server.', ownerOnly: 'Accesso solo OWNER.', localArea: 'Telefono / browser',
      noFix: 'Sentinel rileva e spiega. Non modifica pianificazione, giocatori o rotazioni.'
    },
    es: {
      menu: 'Sentinel', title: 'Sentinel · Pruebas y diagnóstico', subtitle: 'Control de calidad WfGg reservado al propietario.',
      readonly: 'MODO OBSERVADOR · Sin correcciones automáticas', run: 'Ejecutar pruebas', rerun: 'Repetir', running: 'Analizando…',
      close: 'Cerrar', total: 'controles', ok: 'Correcto', info: 'Información', warning: 'Anomalía', error: 'Error bloqueante',
      expected: 'Esperado', observed: 'Observado', cause: 'Causa probable', details: 'Detalle', last: 'Último análisis',
      serverError: 'Sentinel no pudo completar las pruebas del servidor.', ownerOnly: 'Acceso solo OWNER.', localArea: 'Teléfono / navegador',
      noFix: 'Sentinel detecta y explica. No modifica la planificación, los jugadores ni las rotaciones.'
    }
  };

  function lang() {
    const raw = String(localStorage.getItem(STORAGE_LANG) || document.documentElement.lang || 'fr').toLowerCase().split('-')[0];
    return TEXT[raw] ? raw : 'fr';
  }
  const t = (key) => TEXT[lang()][key] || TEXT.fr[key] || key;
  const token = () => localStorage.getItem(STORAGE_TOKEN) || '';
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));

  function style() {
    if (document.getElementById('wfggSentinelStyle')) return;
    const el = document.createElement('style');
    el.id = 'wfggSentinelStyle';
    el.textContent = `
      #wfggSentinelMenu{width:100%;display:flex;align-items:center;gap:.7rem}
      #wfggSentinelMenu .sentinel-dot{width:.62rem;height:.62rem;border-radius:50%;background:#7a6d52;box-shadow:0 0 0 3px rgba(212,181,102,.12)}
      #wfggSentinelMenu[data-state="ok"] .sentinel-dot{background:#59c58b}
      #wfggSentinelMenu[data-state="warning"] .sentinel-dot{background:#e7b44f}
      #wfggSentinelMenu[data-state="error"] .sentinel-dot{background:#ef6262}
      #wfggSentinelOverlay{position:fixed;inset:0;z-index:2147483000;background:rgba(5,7,12,.82);backdrop-filter:blur(14px);display:flex;align-items:stretch;justify-content:center;padding:0}
      #wfggSentinelOverlay.wfgg-hidden{display:none}
      .wfgg-sentinel-panel{width:min(920px,100%);height:100%;overflow:auto;background:linear-gradient(180deg,#121725,#0d1019 70%);color:#f6f2e8;padding:calc(18px + env(safe-area-inset-top)) 16px calc(28px + env(safe-area-inset-bottom));box-sizing:border-box}
      .wfgg-sentinel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}
      .wfgg-sentinel-head h2{font-size:1.38rem;line-height:1.2;margin:.15rem 0 .35rem}.wfgg-sentinel-head p{margin:0;color:#b7bdc9;font-size:.92rem}
      .wfgg-sentinel-close{border:1px solid rgba(255,255,255,.16);background:#1c2231;color:#fff;width:42px;height:42px;border-radius:14px;font-size:1.35rem}
      .wfgg-sentinel-readonly{border:1px solid rgba(221,190,105,.33);background:rgba(221,190,105,.08);color:#e8cf88;border-radius:14px;padding:10px 12px;font-size:.78rem;font-weight:800;letter-spacing:.035em;margin-bottom:14px}
      .wfgg-sentinel-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:12px 0}
      .wfgg-sentinel-stat{border:1px solid rgba(255,255,255,.1);background:#171d2a;border-radius:14px;padding:10px;text-align:center}.wfgg-sentinel-stat strong{display:block;font-size:1.35rem}.wfgg-sentinel-stat span{font-size:.72rem;color:#aeb5c3}
      .wfgg-sentinel-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0 16px}
      .wfgg-sentinel-run{border:0;background:linear-gradient(180deg,#f5d67a,#d5a83f);color:#151515;font-weight:900;border-radius:14px;padding:12px 16px;min-height:46px}.wfgg-sentinel-run:disabled{opacity:.55}
      .wfgg-sentinel-time{font-size:.78rem;color:#929bad}
      .wfgg-sentinel-list{display:flex;flex-direction:column;gap:10px}
      .wfgg-sentinel-check{border:1px solid rgba(255,255,255,.09);background:#151b27;border-radius:16px;padding:13px 14px}
      .wfgg-sentinel-check[data-level="error"]{border-color:rgba(239,98,98,.48);background:rgba(116,31,42,.18)}
      .wfgg-sentinel-check[data-level="warning"]{border-color:rgba(231,180,79,.42);background:rgba(115,84,24,.14)}
      .wfgg-sentinel-check[data-level="info"]{border-color:rgba(95,166,235,.32)}
      .wfgg-sentinel-check[data-level="ok"]{border-color:rgba(89,197,139,.25)}
      .wfgg-sentinel-title{display:flex;align-items:flex-start;gap:9px}.wfgg-sentinel-icon{font-size:1rem;line-height:1.45}.wfgg-sentinel-title strong{display:block;line-height:1.3}.wfgg-sentinel-area{display:block;color:#8d98aa;font-size:.72rem;margin-top:2px}
      .wfgg-sentinel-kv{display:grid;grid-template-columns:85px 1fr;gap:5px 8px;margin-top:10px;font-size:.79rem;line-height:1.45}.wfgg-sentinel-kv b{color:#9fa8b7;font-weight:700}.wfgg-sentinel-kv span{word-break:break-word}
      .wfgg-sentinel-cause{margin-top:9px;padding:8px 10px;background:rgba(255,255,255,.045);border-radius:10px;font-size:.78rem;line-height:1.45}
      .wfgg-sentinel-empty{padding:24px 14px;text-align:center;color:#9aa3b2}
      .wfgg-sentinel-foot{margin:16px 0 4px;color:#8892a2;font-size:.76rem;line-height:1.45}
      @media(max-width:520px){.wfgg-sentinel-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.wfgg-sentinel-kv{grid-template-columns:74px 1fr}}
    `;
    document.head.appendChild(el);
  }

  function overlay() {
    let root = document.getElementById('wfggSentinelOverlay');
    if (root) return root;
    style();
    root = document.createElement('div');
    root.id = 'wfggSentinelOverlay';
    root.className = 'wfgg-hidden';
    root.innerHTML = `
      <section class="wfgg-sentinel-panel" role="dialog" aria-modal="true" aria-labelledby="wfggSentinelTitle">
        <header class="wfgg-sentinel-head">
          <div><div style="font-size:.72rem;color:#d9bd70;font-weight:800;letter-spacing:.08em">WfGg · SENTINEL</div><h2 id="wfggSentinelTitle"></h2><p id="wfggSentinelSubtitle"></p></div>
          <button class="wfgg-sentinel-close" type="button" aria-label="Close">×</button>
        </header>
        <div class="wfgg-sentinel-readonly" id="wfggSentinelReadonly"></div>
        <div class="wfgg-sentinel-summary" id="wfggSentinelSummary"></div>
        <div class="wfgg-sentinel-actions"><button class="wfgg-sentinel-run" type="button" id="wfggSentinelRun"></button><span class="wfgg-sentinel-time" id="wfggSentinelTime"></span></div>
        <div class="wfgg-sentinel-list" id="wfggSentinelList"><div class="wfgg-sentinel-empty">—</div></div>
        <div class="wfgg-sentinel-foot" id="wfggSentinelFoot"></div>
      </section>`;
    document.body.appendChild(root);
    root.querySelector('.wfgg-sentinel-close').addEventListener('click', closePanel);
    root.addEventListener('click', (event) => { if (event.target === root) closePanel(); });
    root.querySelector('#wfggSentinelRun').addEventListener('click', runSentinel);
    translatePanel();
    return root;
  }

  function translatePanel() {
    const root = document.getElementById('wfggSentinelOverlay');
    if (!root) return;
    root.querySelector('#wfggSentinelTitle').textContent = t('title');
    root.querySelector('#wfggSentinelSubtitle').textContent = t('subtitle');
    root.querySelector('#wfggSentinelReadonly').textContent = `🔒 ${t('readonly')}`;
    root.querySelector('#wfggSentinelFoot').textContent = t('noFix');
    root.querySelector('#wfggSentinelRun').textContent = lastReport ? t('rerun') : t('run');
  }

  function injectMenu() {
    if (!ownerConfirmed || document.getElementById('wfggSentinelMenu')) return;
    const menu = document.getElementById('profileMenu');
    if (!menu) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.id = 'wfggSentinelMenu';
    button.innerHTML = `<span>🧪</span><span>${esc(t('menu'))}</span><span class="sentinel-dot" aria-hidden="true"></span>`;
    const logout = menu.querySelector('[data-action="logout"]');
    menu.insertBefore(button, logout || null);
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      menu.classList.add('hidden');
      openPanel();
    });
  }

  async function confirmOwner() {
    const value = token();
    if (!value) return false;
    try {
      const response = await fetch('/api/me', {
        headers: { 'Authorization': `Bearer ${value}`, 'Accept': 'application/json' },
        cache: 'no-store'
      });
      if (!response.ok) return false;
      const data = await response.json();
      ownerConfirmed = data?.system?.role === 'OWNER';
      if (ownerConfirmed) injectMenu();
      return ownerConfirmed;
    } catch (_) {
      return false;
    }
  }

  function openPanel() {
    if (!ownerConfirmed) return;
    const root = overlay();
    translatePanel();
    root.classList.remove('wfgg-hidden');
    document.body.style.overflow = 'hidden';
    if (!lastReport) runSentinel(); else renderReport(lastReport);
  }

  function closePanel() {
    document.getElementById('wfggSentinelOverlay')?.classList.add('wfgg-hidden');
    document.body.style.overflow = '';
  }

  function localCheck(id, level, title, expected, observed, detail = '', probableCause = '') {
    return { id, area: t('localArea'), level, title, expected, observed, detail, probableCause };
  }

  async function deviceChecks() {
    const items = [];
    items.push(localCheck(
      'local-secure-context',
      window.isSecureContext ? 'ok' : 'error',
      'Contexte HTTPS sécurisé', 'isSecureContext = true', String(Boolean(window.isSecureContext)), '',
      window.isSecureContext ? '' : 'Les Service Workers et Web Push nécessitent HTTPS.'
    ));

    const notificationSupported = 'Notification' in window;
    const permission = notificationSupported ? Notification.permission : 'unsupported';
    items.push(localCheck(
      'local-notification-permission',
      !notificationSupported ? 'error' : (permission === 'granted' ? 'ok' : (permission === 'default' ? 'warning' : 'error')),
      'Autorisation des notifications', 'granted', permission, '',
      permission === 'denied' ? 'Les notifications sont bloquées dans le navigateur ou dans Android/iOS.' : (permission === 'default' ? 'L’utilisateur n’a pas encore accordé l’autorisation.' : '')
    ));

    if (!('serviceWorker' in navigator)) {
      items.push(localCheck('local-service-worker', 'error', 'Service Worker', 'Pris en charge', 'Non pris en charge', '', 'Ce navigateur ne peut pas recevoir de Web Push.'));
      return items;
    }

    let registrations = [];
    try { registrations = await navigator.serviceWorker.getRegistrations(); } catch (_) {}
    const trainRegistrations = registrations.filter((registration) => {
      try { return new URL(registration.scope).pathname.startsWith('/train/'); } catch (_) { return false; }
    });
    const pushRegistration = trainRegistrations.find((registration) => {
      const script = registration.active?.scriptURL || registration.waiting?.scriptURL || registration.installing?.scriptURL || '';
      try { return new URL(script).pathname === '/train/wfgg-push-sw.js'; } catch (_) { return false; }
    });

    items.push(localCheck(
      'local-push-sw-registration',
      pushRegistration?.active ? 'ok' : 'error',
      'Service Worker Push actif sur cet appareil',
      '/train/wfgg-push-sw.js actif',
      pushRegistration ? `${pushRegistration.active ? 'actif' : 'présent mais non actif'} · ${pushRegistration.scope}` : `${trainRegistrations.length} registration(s) Train, aucune WfGg Push`,
      '',
      pushRegistration?.active ? '' : 'Le fichier peut être correct sur le serveur mais ne pas être enregistré/actif dans Chrome ou Safari.'
    ));

    if (pushRegistration?.pushManager) {
      let subscription = null;
      try { subscription = await pushRegistration.pushManager.getSubscription(); } catch (_) {}
      items.push(localCheck(
        'local-push-subscription',
        subscription?.endpoint ? 'ok' : 'error',
        'Abonnement Push de cet appareil',
        'Un endpoint Push actif',
        subscription?.endpoint ? `Présent · ${String(subscription.endpoint).slice(0, 72)}…` : 'Aucun abonnement',
        '',
        subscription?.endpoint ? '' : 'Le téléphone ne possède pas d’abonnement Push utilisable, même si le bouton de rappel est activé.'
      ));
    }

    let trainState = null;
    try { trainState = JSON.parse(localStorage.getItem('wfgg_train_v13') || 'null'); } catch (_) {}
    items.push(localCheck(
      'local-train-state',
      trainState?.currentUserId ? 'ok' : 'warning',
      'État local Train',
      'currentUserId présent',
      trainState?.currentUserId ? `Utilisateur ${String(trainState.currentUserId).slice(0, 24)}` : 'Aucun utilisateur Train initialisé localement',
      '',
      trainState?.currentUserId ? '' : 'Peut expliquer un écran de démarrage bloqué même lorsque le snapshot serveur est valide.'
    ));

    return items;
  }

  async function runSentinel() {
    if (!ownerConfirmed) return;
    const root = overlay();
    const run = root.querySelector('#wfggSentinelRun');
    const list = root.querySelector('#wfggSentinelList');
    run.disabled = true;
    run.textContent = t('running');
    list.innerHTML = `<div class="wfgg-sentinel-empty">⏳ ${esc(t('running'))}</div>`;

    try {
      const [serverResponse, local] = await Promise.all([
        fetch('/api/sentinel/run', {
          method: 'GET',
          headers: { 'Authorization': `Bearer ${token()}`, 'Accept': 'application/json' },
          cache: 'no-store'
        }),
        deviceChecks()
      ]);
      let server = null;
      try { server = await serverResponse.json(); } catch (_) {}
      if (serverResponse.status === 403) {
        ownerConfirmed = false;
        throw new Error(t('ownerOnly'));
      }
      if (!serverResponse.ok && !server?.checks) {
        throw new Error(`${server?.error || t('serverError')} · HTTP ${serverResponse.status}`);
      }
      const checks = [...(server?.checks || []), ...local];
      const counts = { ok:0, info:0, warning:0, error:0 };
      checks.forEach((item) => { counts[item.level] = (counts[item.level] || 0) + 1; });
      const overall = counts.error ? 'error' : (counts.warning ? 'warning' : (counts.info ? 'info' : 'ok'));
      lastReport = {
        ...server,
        checks,
        summary: { status: overall, counts, total: checks.length },
        finishedAt: server?.finishedAt || new Date().toISOString()
      };
      renderReport(lastReport);
    } catch (error) {
      list.innerHTML = `<article class="wfgg-sentinel-check" data-level="error"><div class="wfgg-sentinel-title"><span class="wfgg-sentinel-icon">🔴</span><div><strong>${esc(t('serverError'))}</strong><span class="wfgg-sentinel-area">Sentinel</span></div></div><div class="wfgg-sentinel-cause">${esc(error?.message || error)}</div></article>`;
    } finally {
      run.disabled = false;
      run.textContent = lastReport ? t('rerun') : t('run');
    }
  }

  function levelIcon(level) {
    return level === 'error' ? '🔴' : level === 'warning' ? '🟠' : level === 'info' ? '🔵' : '🟢';
  }

  function renderReport(report) {
    const root = overlay();
    translatePanel();
    const counts = report?.summary?.counts || { ok:0, info:0, warning:0, error:0 };
    root.querySelector('#wfggSentinelSummary').innerHTML = [
      ['ok', t('ok')], ['info', t('info')], ['warning', t('warning')], ['error', t('error')]
    ].map(([key,label]) => `<div class="wfgg-sentinel-stat"><strong>${Number(counts[key] || 0)}</strong><span>${esc(label)}</span></div>`).join('');
    const time = report?.finishedAt ? new Date(report.finishedAt) : new Date();
    root.querySelector('#wfggSentinelTime').textContent = `${t('last')} · ${time.toLocaleString()}`;

    const priority = { error:0, warning:1, info:2, ok:3 };
    const checks = [...(report?.checks || [])].sort((a,b) => (priority[a.level] ?? 9) - (priority[b.level] ?? 9));
    root.querySelector('#wfggSentinelList').innerHTML = checks.length ? checks.map((item) => `
      <article class="wfgg-sentinel-check" data-level="${esc(item.level)}">
        <div class="wfgg-sentinel-title"><span class="wfgg-sentinel-icon">${levelIcon(item.level)}</span><div><strong>${esc(item.title)}</strong><span class="wfgg-sentinel-area">${esc(item.area || 'Sentinel')} · ${esc(item.id || '')}</span></div></div>
        <div class="wfgg-sentinel-kv">
          <b>${esc(t('expected'))}</b><span>${esc(item.expected || '—')}</span>
          <b>${esc(t('observed'))}</b><span>${esc(item.observed || '—')}</span>
          ${item.detail ? `<b>${esc(t('details'))}</b><span>${esc(item.detail)}</span>` : ''}
        </div>
        ${item.probableCause ? `<div class="wfgg-sentinel-cause"><b>${esc(t('cause'))} :</b> ${esc(item.probableCause)}</div>` : ''}
      </article>`).join('') : `<div class="wfgg-sentinel-empty">0 ${esc(t('total'))}</div>`;

    const button = document.getElementById('wfggSentinelMenu');
    if (button) button.dataset.state = report?.summary?.status || 'ok';
  }

  function init() {
    style();
    const tryOwner = () => {
      if (!token()) return;
      confirmOwner().then(() => injectMenu());
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryOwner, { once:true });
    else tryOwner();
    window.addEventListener('storage', (event) => {
      if (event.key === STORAGE_TOKEN) {
        ownerConfirmed = false;
        document.getElementById('wfggSentinelMenu')?.remove();
        if (event.newValue) tryOwner();
      }
      if (event.key === STORAGE_LANG) translatePanel();
    });
    setTimeout(() => { if (token() && !ownerConfirmed) tryOwner(); }, 900);
    setTimeout(() => { if (ownerConfirmed) injectMenu(); }, 1600);
  }

  init();
})();
