(() => {
  'use strict';

  const BUTTON_ID = 'wfggSentinelCopyReport';
  const STYLE_ID = 'wfggSentinelCopyReportStyle';
  const OVERLAY_ID = 'wfggSentinelOverlay';

  function installStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      #${BUTTON_ID}{
        border:1px solid rgba(255,255,255,.15);
        background:linear-gradient(180deg,#252d3d,#1a202d);
        color:#f6f2e8;
        font-weight:800;
        border-radius:14px;
        min-height:46px;
        padding:12px 15px;
        cursor:pointer;
        box-shadow:inset 0 1px 0 rgba(255,255,255,.04);
      }
      #${BUTTON_ID}:active{transform:scale(.98)}
      #${BUTTON_ID}[data-state="copied"]{border-color:rgba(89,197,139,.46);color:#bff0d3}
      #${BUTTON_ID}[data-state="error"]{border-color:rgba(239,98,98,.5);color:#ffc5c5}
      @media(max-width:520px){#${BUTTON_ID}{width:100%}}
    `;
    document.head.appendChild(style);
  }

  function clean(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function levelName(card) {
    const level = String(card?.dataset?.level || 'info').toUpperCase();
    return level === 'ERROR' ? 'ERREUR' : level === 'WARNING' ? 'ANOMALIE' : level === 'OK' ? 'CONFORME' : 'INFO';
  }

  function buildReportText() {
    const root = document.getElementById(OVERLAY_ID);
    if (!root) return 'WFGG_SENTINEL_REPORT_V1\nAucun rapport Sentinel affiché.';

    const lines = [
      'WFGG_SENTINEL_REPORT_V1',
      'WfGg · Sentinel · Rapport de diagnostic',
      `Copié le: ${new Date().toISOString()}`,
      `Page: ${location.href}`,
      `Navigateur: ${navigator.userAgent}`,
      `Mode standalone: ${String(window.matchMedia?.('(display-mode: standalone)')?.matches || navigator.standalone === true)}`
    ];

    const last = clean(root.querySelector('#wfggSentinelTime')?.textContent);
    if (last) lines.push(`Analyse: ${last}`);

    const stats = [...root.querySelectorAll('.wfgg-sentinel-stat')].map((node) => {
      const value = clean(node.querySelector('strong')?.textContent);
      const label = clean(node.querySelector('span')?.textContent);
      return label ? `${label}: ${value || '0'}` : '';
    }).filter(Boolean);

    lines.push('', 'RÉSUMÉ');
    if (stats.length) stats.forEach((item) => lines.push(`- ${item}`));
    else lines.push('- Résumé indisponible');

    const cards = [...root.querySelectorAll('.wfgg-sentinel-check')];
    lines.push('', `CONTRÔLES (${cards.length})`);

    if (!cards.length) {
      lines.push('- Aucun contrôle rendu dans le rapport.');
    } else {
      cards.forEach((card, index) => {
        const title = clean(card.querySelector('.wfgg-sentinel-title strong')?.textContent) || `Contrôle ${index + 1}`;
        const area = clean(card.querySelector('.wfgg-sentinel-area')?.textContent);
        lines.push('', `[${levelName(card)}] ${title}`);
        if (area) lines.push(`Zone: ${area}`);

        const kv = card.querySelector('.wfgg-sentinel-kv');
        if (kv) {
          const children = [...kv.children];
          for (let i = 0; i < children.length; i += 2) {
            const key = clean(children[i]?.textContent);
            const value = clean(children[i + 1]?.textContent);
            if (key || value) lines.push(`${key || 'Valeur'}: ${value || '—'}`);
          }
        }

        const cause = clean(card.querySelector('.wfgg-sentinel-cause')?.textContent);
        if (cause) lines.push(cause);
      });
    }

    lines.push('', 'MODE: OBSERVATEUR / LECTURE SEULE', 'Aucune correction automatique effectuée par Sentinel.');
    return lines.join('\n');
  }

  async function copyText(text) {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_) {}
    }

    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    area.style.pointerEvents = 'none';
    document.body.appendChild(area);
    area.select();
    area.setSelectionRange(0, area.value.length);
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (_) {}
    area.remove();
    return ok;
  }

  function setButtonState(button, state, text) {
    button.dataset.state = state || '';
    button.textContent = text;
    clearTimeout(button.__wfggResetTimer);
    button.__wfggResetTimer = setTimeout(() => {
      button.dataset.state = '';
      button.textContent = '📋 Copier le rapport';
    }, 2200);
  }

  async function onCopy(button) {
    const text = buildReportText();
    const ok = await copyText(text);
    if (ok) setButtonState(button, 'copied', '✅ Rapport copié');
    else setButtonState(button, 'error', '❌ Copie impossible');
  }

  function injectButton() {
    if (document.getElementById(BUTTON_ID)) return true;
    const root = document.getElementById(OVERLAY_ID);
    const actions = root?.querySelector('.wfgg-sentinel-actions');
    if (!actions) return false;

    installStyle();
    const button = document.createElement('button');
    button.type = 'button';
    button.id = BUTTON_ID;
    button.textContent = '📋 Copier le rapport';
    button.title = 'Copier un rapport Sentinel prêt à coller dans ChatGPT';
    button.setAttribute('aria-label', 'Copier le rapport Sentinel');
    button.addEventListener('click', () => onCopy(button));

    const time = actions.querySelector('#wfggSentinelTime');
    actions.insertBefore(button, time || null);
    return true;
  }

  function init() {
    installStyle();
    injectButton();
    const observer = new MutationObserver(() => injectButton());
    observer.observe(document.documentElement, { childList:true, subtree:true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once:true });
  else init();
})();
