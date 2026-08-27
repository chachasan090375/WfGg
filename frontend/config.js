window.WFGG_PORTAL_CONFIG = {
  API_BASE: "",
  MODULES: {
    train: "/train/",
    guides: "/guides/",
    simulator: "/simulateur/"
  }
};

// Preview-only Last War diagnostic bridge. It never exposes secrets or payloads:
// only the server's normalized WfGg error code is surfaced when the normal UI
// would otherwise collapse it into a generic "service unavailable" message.
(()=>{
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    try {
      const input = args[0];
      const url = String(typeof input === 'string' ? input : (input?.url || ''));
      if (!response.ok && /\/api\/lastwar\/(?:identity\/|cloud-sync)/.test(url)) {
        const data = await response.clone().json().catch(() => null);
        const code = typeof data?.error === 'string' ? data.error.trim() : '';
        if (/^(?:LASTWAR_|BROKER_)/.test(code)) {
          window.WFGG_LASTWAR_LAST_ERROR = code;
          queueMicrotask(relabelLastWarError);
        }
      }
    } catch (_) {}
    return response;
  };

  function relabelLastWarError() {
    const code = String(window.WFGG_LASTWAR_LAST_ERROR || '');
    const box = document.getElementById('lwMessage');
    if (!code || !box || box.hidden) return;
    const text = String(box.textContent || '');
    if (/service de connexion Last War|Last War connection service|servizio di connessione Last War|servicio de conexi[oó]n Last War/i.test(text)) {
      box.textContent = `Diagnostic WfGg : ${code}`;
    }
  }

  const startObserver = () => {
    if (!document.documentElement) return;
    new MutationObserver(relabelLastWarError).observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['hidden', 'class']
    });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startObserver, { once: true });
  else startObserver();
})();
