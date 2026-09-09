(() => {
  'use strict';

  const LEGACY_MENU_ID = 'wfggSentinelMenu';
  const LAUNCHER_ID = 'wfggSentinelLauncher';
  const STYLE_ID = 'wfggSentinelLauncherStyle';
  const NAME_ID = 'heroName';

  function installStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      /* WFGG_SENTINEL_LAUNCHER_POPUP_V2 */
      #${LEGACY_MENU_ID}{display:none!important}
      .wfgg-sentinel-name-row{display:flex!important;align-items:center!important;gap:10px!important;flex-wrap:wrap!important}
      #${LAUNCHER_ID}{
        appearance:none;border:1px solid rgba(232,207,136,.42);outline:none;
        display:inline-flex;align-items:center;gap:7px;min-height:34px;
        padding:6px 10px 6px 9px;border-radius:999px;cursor:pointer;
        color:#f7edcc;background:
          linear-gradient(180deg,rgba(50,43,71,.92),rgba(26,25,42,.94));
        box-shadow:0 8px 24px rgba(0,0,0,.24),inset 0 1px 0 rgba(255,255,255,.06);
        font:800 12px/1 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
        letter-spacing:.015em;vertical-align:middle;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease;
      }
      #${LAUNCHER_ID}:active{transform:scale(.97)}
      #${LAUNCHER_ID}:focus-visible{box-shadow:0 0 0 3px rgba(217,189,112,.24),0 8px 24px rgba(0,0,0,.24)}
      #${LAUNCHER_ID} .sentinel-flask{font-size:15px;line-height:1}
      #${LAUNCHER_ID} .sentinel-label{white-space:nowrap}
      #${LAUNCHER_ID} .sentinel-dot{width:8px;height:8px;border-radius:50%;background:#7a6d52;box-shadow:0 0 0 3px rgba(212,181,102,.11)}
      #${LAUNCHER_ID}[data-state="ok"]{border-color:rgba(89,197,139,.42)}
      #${LAUNCHER_ID}[data-state="ok"] .sentinel-dot{background:#59c58b}
      #${LAUNCHER_ID}[data-state="info"] .sentinel-dot{background:#5fa6eb}
      #${LAUNCHER_ID}[data-state="warning"]{border-color:rgba(231,180,79,.58)}
      #${LAUNCHER_ID}[data-state="warning"] .sentinel-dot{background:#e7b44f}
      #${LAUNCHER_ID}[data-state="error"]{border-color:rgba(239,98,98,.62);box-shadow:0 8px 26px rgba(90,20,30,.26),inset 0 1px 0 rgba(255,255,255,.06)}
      #${LAUNCHER_ID}[data-state="error"] .sentinel-dot{background:#ef6262}

      /* Sentinel reste un vrai pop-up : fond assombri + carte flottante, jamais une page plein écran. */
      #wfggSentinelOverlay{
        align-items:center!important;justify-content:center!important;
        padding:clamp(12px,3vw,28px)!important;
        background:rgba(5,7,12,.72)!important;
      }
      #wfggSentinelOverlay .wfgg-sentinel-panel{
        width:min(900px,calc(100vw - 24px))!important;
        height:auto!important;
        max-height:min(86dvh,860px)!important;
        overflow:auto!important;
        border-radius:24px!important;
        border:1px solid rgba(255,255,255,.12)!important;
        box-shadow:0 30px 90px rgba(0,0,0,.58)!important;
        padding:20px 18px 22px!important;
      }
      @media(max-width:620px){
        #${LAUNCHER_ID}{min-height:32px;padding:5px 9px;font-size:11px}
        #${LAUNCHER_ID} .sentinel-label{display:none}
        #${LAUNCHER_ID} .sentinel-flask{font-size:16px}
        #wfggSentinelOverlay{padding:10px!important}
        #wfggSentinelOverlay .wfgg-sentinel-panel{
          width:calc(100vw - 20px)!important;
          max-height:calc(100dvh - 20px)!important;
          border-radius:20px!important;
          padding:16px 14px 18px!important;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function syncState(legacy, launcher) {
    const state = legacy?.dataset?.state || '';
    if (state) launcher.dataset.state = state;
    else delete launcher.dataset.state;
  }

  function injectLauncher() {
    const legacy = document.getElementById(LEGACY_MENU_ID);
    if (!legacy) return false; // le bouton historique n'existe que pour OWNER

    installStyle();
    legacy.style.display = 'none';

    let launcher = document.getElementById(LAUNCHER_ID);
    if (!launcher) {
      const name = document.getElementById(NAME_ID);
      const heading = name?.closest('h2') || name?.parentElement;
      if (!heading) return false;

      heading.classList.add('wfgg-sentinel-name-row');
      launcher = document.createElement('button');
      launcher.type = 'button';
      launcher.id = LAUNCHER_ID;
      launcher.setAttribute('aria-label', 'Ouvrir Sentinel');
      launcher.title = 'Sentinel · Recette & diagnostic';
      launcher.innerHTML = '<span class="sentinel-flask" aria-hidden="true">🧪</span><span class="sentinel-label">Sentinel</span><span class="sentinel-dot" aria-hidden="true"></span>';
      heading.appendChild(launcher);
      launcher.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        const ownerButton = document.getElementById(LEGACY_MENU_ID);
        if (ownerButton) ownerButton.click();
      });
    }

    syncState(legacy, launcher);
    if (!legacy.dataset.sentinelLauncherObserved) {
      legacy.dataset.sentinelLauncherObserved = '1';
      new MutationObserver(() => syncState(legacy, launcher)).observe(legacy, { attributes:true, attributeFilter:['data-state'] });
    }
    return true;
  }

  function removeLauncherIfOwnerGone() {
    if (document.getElementById(LEGACY_MENU_ID)) return;
    document.getElementById(LAUNCHER_ID)?.remove();
  }

  function init() {
    installStyle();
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (injectLauncher() || tries > 80) clearInterval(timer);
    }, 150);

    const observer = new MutationObserver(() => {
      if (!injectLauncher()) removeLauncherIfOwnerGone();
    });
    observer.observe(document.documentElement, { childList:true, subtree:true });

    window.addEventListener('storage', (event) => {
      if (event.key === 'wfgg_portal_session' && !event.newValue) {
        document.getElementById(LAUNCHER_ID)?.remove();
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once:true });
  else init();
})();
