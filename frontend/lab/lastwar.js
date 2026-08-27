(() => {
  'use strict';

  const TOKEN_KEY = 'wfgg_portal_session';
  const $ = (id) => document.getElementById(id);

  function setStatus(text, kind = 'neutral') {
    const el = $('status');
    el.textContent = text;
    el.className = `status ${kind}`;
  }

  async function load() {
    $('identity').classList.add('hidden');
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setStatus('Aucune session WfGg trouvée. Connectez-vous d’abord au portail Preview.', 'error');
      return;
    }

    setStatus('Lecture du contexte WfGg…', 'pending');
    try {
      const response = await fetch('/api/me', {
        headers: { Authorization: `Bearer ${token}` },
        cache: 'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error || `HTTP_${response.status}`);

      $('name').textContent = data.user?.display_name || data.user?.player_name || '—';
      $('userId').textContent = data.user?.id || '—';
      $('alliance').textContent = data.alliance?.name || '—';
      $('server').textContent = data.alliance?.server || '—';
      $('identity').classList.remove('hidden');
      setStatus('Socle WfGg reconnu. Une future identité Last War vérifiée pourra être reliée à ce user_id sans changer les modules.', 'success');
    } catch (error) {
      setStatus(`Contexte indisponible : ${error.message}`, 'error');
    }
  }

  $('refreshButton').addEventListener('click', load);
  load();
})();
