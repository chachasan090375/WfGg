(() => {
  'use strict';

  const TOKEN_KEY = 'wfgg_portal_session';
  const cfg = window.WFGG_PORTAL_CONFIG || { API_BASE: '' };

  const $ = (id) => document.getElementById(id);

  function redact(value) {
    if (Array.isArray(value)) return value.map(redact);
    if (!value || typeof value !== 'object') return value;
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      if (/(token|secret|auth.?code|code.?key|password)/i.test(key)) {
        out[key] = '[masqué]';
      } else {
        out[key] = redact(item);
      }
    }
    return out;
  }

  function showJson(id, value) {
    $(id).textContent = JSON.stringify(redact(value), null, 2);
  }

  function cell(label, value) {
    const el = document.createElement('div');
    el.className = 'datum';
    const k = document.createElement('span');
    k.className = 'datum-label';
    k.textContent = label;
    const v = document.createElement('strong');
    v.textContent = value === null || value === undefined || value === '' ? '—' : String(value);
    el.append(k, v);
    return el;
  }

  async function api(path) {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) throw new Error('NO_SESSION');
    const response = await fetch(`${cfg.API_BASE || ''}${path}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      cache: 'no-store'
    });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data?.error || `HTTP_${response.status}`);
    return data;
  }

  function renderSummary(me, train) {
    const root = $('summary');
    root.innerHTML = '';
    const items = [
      ['ID utilisateur', me?.user?.id],
      ['Pseudo joueur', me?.user?.player_name],
      ['Pseudo affiché', me?.user?.display_name],
      ['Langue', me?.user?.language],
      ['Profil complété', me?.user?.profile_completed ? 'oui' : 'non'],
      ['Alliance', me?.alliance?.name],
      ['Serveur', me?.alliance?.server],
      ['Rang', me?.membership?.rank],
      ['Fonction officier', me?.membership?.officer_title],
      ['Rôle système', me?.system?.role],
      ['Membres visibles via contexte Train', Array.isArray(train?.roster) ? train.roster.length : 0]
    ];
    for (const [label, value] of items) root.appendChild(cell(label, value));
  }

  function trainDiagnostic(train) {
    const first = Array.isArray(train?.roster) && train.roster.length ? train.roster[0] : null;
    return {
      me: train?.me || null,
      alliance: train?.alliance || null,
      roster_count: Array.isArray(train?.roster) ? train.roster.length : 0,
      roster_fields_available: first ? Object.keys(first).sort() : []
    };
  }

  async function load() {
    const status = $('status');
    status.className = 'status';
    status.textContent = 'Lecture du contexte…';

    if (!localStorage.getItem(TOKEN_KEY)) {
      status.classList.add('bad');
      status.textContent = 'Aucune session sur cet alias. Revenez au portail et connectez-vous sur cette branche de test.';
      $('summary').innerHTML = '';
      $('meOutput').textContent = '—';
      $('trainOutput').textContent = '—';
      return;
    }

    try {
      const [me, train] = await Promise.all([
        api('/api/me'),
        api('/api/train/context')
      ]);
      status.classList.add('good');
      status.textContent = 'Session valide — les deux contextes sont accessibles.';
      renderSummary(me, train);
      showJson('meOutput', me);
      showJson('trainOutput', trainDiagnostic(train));
    } catch (error) {
      status.classList.add('bad');
      status.textContent = `Erreur : ${error.message}`;
    }
  }

  $('refreshButton').addEventListener('click', load);
  load();
})();
