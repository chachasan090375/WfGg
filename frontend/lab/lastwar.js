(() => {
  'use strict';

  const TOKEN_KEY = 'wfgg_portal_session';
  const LAB_API_BASE = 'https://wfgg-api-lastwar-preview.chachasan090375.workers.dev';
  const $ = (id) => document.getElementById(id);
  let labReady = false;

  function setStatus(id, text, kind = 'neutral') {
    const el = $(id);
    el.textContent = text;
    el.className = `status ${kind}`;
  }

  function token() {
    return localStorage.getItem(TOKEN_KEY) || '';
  }

  function enableForm(enabled) {
    labReady = enabled;
    ['playerUid', 'serverId', 'allianceId', 'claimButton'].forEach((id) => {
      if ($(id)) $(id).disabled = !enabled;
    });
  }

  async function portalApi(path) {
    const response = await fetch(path, {
      headers: { Authorization: `Bearer ${token()}` },
      cache: 'no-store'
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.error || `HTTP_${response.status}`);
    return data;
  }

  async function labApi(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (token()) headers.set('Authorization', `Bearer ${token()}`);
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    const response = await fetch(`${LAB_API_BASE}${path}`, {
      ...options,
      headers,
      cache: 'no-store',
      credentials: 'omit'
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.error || `HTTP_${response.status}`);
    return data;
  }

  async function loadPortalContext() {
    $('identity').classList.add('hidden');
    if (!token()) {
      setStatus('status', 'Aucune session WfGg trouvée sur cette Preview. Revenez au portail de cette même Preview et connectez-vous.', 'error');
      throw new Error('NO_SESSION');
    }

    setStatus('status', 'Lecture du contexte WfGg…', 'pending');
    const data = await portalApi('/api/me');
    $('name').textContent = data.user?.display_name || data.user?.player_name || '—';
    $('userId').textContent = data.user?.id || '—';
    $('alliance').textContent = data.alliance?.name || '—';
    $('server').textContent = data.alliance?.server || '—';
    if (!$('serverId').value) $('serverId').value = data.alliance?.server || '';
    $('identity').classList.remove('hidden');
    setStatus('status', 'Session WfGg reconnue. Cette identité sera seulement référencée par le laboratoire.', 'success');
  }

  function badgeClass(status) {
    const value = String(status || '').toLowerCase();
    return ['pending', 'verified', 'revoked'].includes(value) ? value : 'pending';
  }

  function renderIdentities(items = []) {
    const host = $('identityList');
    host.innerHTML = '';
    if (!items.length) {
      host.innerHTML = '<p class="muted">Aucune liaison Last War enregistrée dans la D1 laboratoire.</p>';
      return;
    }

    for (const item of items) {
      const row = document.createElement('div');
      row.className = 'identity-row';
      const title = document.createElement('strong');
      title.textContent = `UID ${item.player_uid || '—'} · serveur ${item.server_id || '—'}`;
      row.appendChild(title);

      const meta = document.createElement('div');
      meta.className = 'identity-meta';
      meta.textContent = item.alliance_id ? `Alliance : ${item.alliance_id}` : 'Alliance : non renseignée';
      row.appendChild(meta);

      const badge = document.createElement('span');
      badge.className = `badge ${badgeClass(item.status)}`;
      badge.textContent = item.status || 'PENDING';
      row.appendChild(badge);

      if (item.status !== 'REVOKED') {
        const actions = document.createElement('div');
        actions.className = 'actions';
        actions.style.marginTop = '10px';
        const button = document.createElement('button');
        button.className = 'button secondary';
        button.type = 'button';
        button.textContent = 'Révoquer';
        button.addEventListener('click', () => revokeIdentity(item.id, button));
        actions.appendChild(button);
        row.appendChild(actions);
      }
      host.appendChild(row);
    }
  }

  async function loadIdentities() {
    if (!labReady) return;
    try {
      const data = await labApi('/api/me/identities');
      renderIdentities(data.identities || []);
    } catch (error) {
      setStatus('labStatus', `API laboratoire joignable mais contexte refusé : ${error.message}`, 'error');
      enableForm(false);
    }
  }

  async function probeLab() {
    enableForm(false);
    setStatus('labStatus', 'Recherche de la D1 et du Worker laboratoire…', 'pending');
    try {
      const health = await labApi('/api/health');
      if (!health?.ok || health?.storage !== 'LAB_DB_ONLY') throw new Error('LAB_CONFIGURATION_INVALID');
      setStatus('labStatus', 'Worker Preview opérationnel · écritures limitées à LAB_DB.', 'success');
      enableForm(true);
      await loadIdentities();
    } catch (_) {
      $('identityList').innerHTML = '<p class="muted">En attente de la D1 laboratoire dédiée.</p>';
      setStatus('labStatus', 'D1 laboratoire non connectée pour le moment. Aucun enregistrement n’est possible et aucune donnée de production n’est modifiée.', 'neutral');
      enableForm(false);
    }
  }

  async function claim(event) {
    event.preventDefault();
    if (!labReady) return;
    const playerUid = $('playerUid').value.trim();
    const serverId = $('serverId').value.trim();
    const allianceId = $('allianceId').value.trim();
    if (!playerUid || !serverId) return;

    $('claimButton').disabled = true;
    $('claimResult').classList.remove('hidden');
    setStatus('claimResult', 'Enregistrement dans la D1 laboratoire…', 'pending');
    try {
      const data = await labApi('/api/me/identities/lastwar/claim', {
        method: 'POST',
        body: JSON.stringify({ player_uid: playerUid, server_id: serverId, alliance_id: allianceId || null })
      });
      setStatus('claimResult', `Liaison enregistrée en ${data.identity?.status || 'PENDING'}. Elle ne peut pas servir à l’authentification.`, 'success');
      await loadIdentities();
    } catch (error) {
      setStatus('claimResult', `Échec : ${error.message}`, 'error');
    } finally {
      $('claimButton').disabled = !labReady;
    }
  }

  async function revokeIdentity(id, button) {
    button.disabled = true;
    try {
      await labApi(`/api/me/identities/lastwar/${encodeURIComponent(id)}`, { method: 'DELETE' });
      await loadIdentities();
    } catch (error) {
      setStatus('labStatus', `Révocation impossible : ${error.message}`, 'error');
    } finally {
      button.disabled = false;
    }
  }

  async function loadAll() {
    try {
      await loadPortalContext();
      await probeLab();
    } catch (_) {
      enableForm(false);
    }
  }

  $('refreshButton').addEventListener('click', loadAll);
  $('linkForm').addEventListener('submit', claim);
  loadAll();
})();
