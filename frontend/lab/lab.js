(() => {
  'use strict';

  const TOKEN_KEY = 'wfgg_portal_session';
  const $ = (id) => document.getElementById(id);

  function setStatus(text, kind = 'neutral') {
    const el = $('status');
    el.textContent = text;
    el.className = `status ${kind}`;
  }

  async function api(path) {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) throw new Error('NO_SESSION');
    const response = await fetch(path, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store'
    });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (response.status === 401) throw new Error('UNAUTHORIZED');
    if (!response.ok) throw new Error(data?.error || `HTTP_${response.status}`);
    return data;
  }

  function value(id, data, fallback = '—') {
    $(id).textContent = data === null || data === undefined || data === '' ? fallback : String(data);
  }

  function renderPermissions(permissions = {}) {
    const host = $('permissions');
    host.innerHTML = '';
    const entries = Object.entries(permissions);
    if (!entries.length) {
      host.textContent = 'Aucune permission transmise.';
      return;
    }
    for (const [name, allowed] of entries) {
      const chip = document.createElement('span');
      chip.className = `chip ${allowed ? 'yes' : 'no'}`;
      chip.textContent = `${allowed ? '✓' : '×'} ${name}`;
      host.appendChild(chip);
    }
  }

  function renderContext(data) {
    const user = data.user || {};
    const membership = data.membership || {};
    const alliance = data.alliance || {};
    const system = data.system || {};

    value('userName', user.display_name || user.player_name);
    value('userId', user.id);
    value('allianceName', alliance.name);
    value('server', alliance.server);
    value('rank', membership.rank);
    value('officer', membership.officer_title);
    value('systemRole', system.role);
    value('language', user.language);
    renderPermissions(data.permissions || {});

    $('identityCard').classList.remove('hidden');
    $('permissionCard').classList.remove('hidden');
    $('rosterCard').classList.remove('hidden');
  }

  async function boot() {
    $('identityCard').classList.add('hidden');
    $('permissionCard').classList.add('hidden');
    $('rosterCard').classList.add('hidden');
    setStatus('Vérification de la session…', 'pending');

    if (!localStorage.getItem(TOKEN_KEY)) {
      setStatus('Aucune session WfGg trouvée. Revenez au portail et connectez-vous.', 'error');
      return;
    }

    try {
      const data = await api('/api/me');
      renderContext(data);
      const name = data.user?.display_name || data.user?.player_name || 'utilisateur';
      setStatus(`Session héritée du portail : ${name} reconnu automatiquement, sans nouveau login.`, 'success');
    } catch (error) {
      if (['NO_SESSION', 'UNAUTHORIZED'].includes(error.message)) {
        setStatus('La session du portail est absente ou expirée. Une reconnexion au portail est nécessaire.', 'error');
      } else {
        setStatus(`Échec du contexte partagé : ${error.message}`, 'error');
      }
    }
  }

  async function testRoster() {
    const button = $('rosterButton');
    const result = $('rosterResult');
    button.disabled = true;
    button.textContent = 'Test en cours…';
    result.classList.remove('hidden');
    result.className = 'status neutral';
    result.textContent = 'Demande du contexte Train…';
    try {
      const data = await api('/api/train/context');
      const count = Array.isArray(data.roster) ? data.roster.length : 0;
      result.className = 'status success';
      result.textContent = `Accès confirmé : ${count} membre${count > 1 ? 's' : ''} visible${count > 1 ? 's' : ''}. Les fiches individuelles ne sont pas affichées dans ce module laboratoire.`;
    } catch (error) {
      result.className = 'status error';
      result.textContent = `Accès refusé ou indisponible : ${error.message}`;
    } finally {
      button.disabled = false;
      button.textContent = 'Tester l’accès au roster';
    }
  }

  $('refreshButton').addEventListener('click', boot);
  $('rosterButton').addEventListener('click', testRoster);
  boot();
})();
