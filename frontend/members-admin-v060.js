/* WfGg Portal — Administration des membres v0.6.0
   Vue unique inspirée directement de l'ergonomie WfGg Train.
   Aucune couche concurrente, aucun onclick inline, aucun MutationObserver.
*/
(() => {
  'use strict';

  const VERSION = '0.6.0';
  const cfg = window.WFGG_PORTAL_CONFIG || { API_BASE: '' };
  const TOKEN_KEY = 'wfgg_portal_session';
  const RANKS = ['R5', 'R4', 'R3', 'R2', 'R1'];
  const OFFICES = ['', 'WARLORD', 'RECRUITER', 'MUSE', 'BUTLER'];
  const OFFICE_LABELS = {
    WARLORD: 'Seigneur de guerre',
    RECRUITER: 'Recruteur',
    MUSE: 'Muse',
    BUTLER: 'Majordome'
  };
  const LEGACY = window.WFGG_LEGACY_AVATARS || {};

  const state = {
    me: null,
    members: [],
    rank: 'TOUS',
    search: '',
    busy: false,
    open: false,
    editorId: null
  };

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

  const token = () => localStorage.getItem(TOKEN_KEY);

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (token()) headers.set('Authorization', `Bearer ${token()}`);
    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(`${cfg.API_BASE}${path}`, { ...options, headers, cache: 'no-store' });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data?.error || `HTTP_${response.status}`);
    return data;
  }

  function memberName(m) {
    return m?.display_name || m?.player_name || '?';
  }

  function initials(name = '?') {
    return String(name).trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?';
  }

  function avatarUrl(m) {
    return m?.avatar_url || LEGACY[m?.player_name] || LEGACY[m?.display_name] || '';
  }

  function avatarHtml(m, cls = '') {
    const name = memberName(m);
    const url = avatarUrl(m);
    if (url) {
      return `<span class="w6-avatar ${cls}" role="img" aria-label="${esc(name)}" style="background-image:url('${esc(url)}')"></span>`;
    }
    return `<span class="w6-avatar w6-initials ${cls}" aria-label="${esc(name)}">${esc(initials(name))}</span>`;
  }

  function relativeLastSeen(value) {
    if (!value) return 'jamais connecté';
    const ts = new Date(value).getTime();
    if (!Number.isFinite(ts)) return String(value);
    const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (sec < 100) return 'en ligne';
    const min = Math.floor(sec / 60);
    if (min < 60) return `il y a ${min} min`;
    const hour = Math.floor(min / 60);
    if (hour < 24) return `il y a ${hour} h`;
    const day = Math.floor(hour / 24);
    if (day < 30) return `il y a ${day} jour${day > 1 ? 's' : ''}`;
    const month = Math.max(1, Math.floor(day / 30));
    if (day < 365) return `il y a ${month} mois`;
    const year = Math.max(1, Math.floor(day / 365));
    return `il y a ${year} an${year > 1 ? 's' : ''}`;
  }

  function rankClass(rank) {
    return `rank-${String(rank || 'R3').toLowerCase()}`;
  }

  function statusLine(m) {
    const bits = [m.active ? 'actif' : 'désactivé'];
    if (m.officer_title) bits.push(OFFICE_LABELS[m.officer_title] || m.officer_title);
    if (m.system_role === 'OWNER') bits.push('OWNER');
    return bits.join(' · ');
  }

  function filteredMembers() {
    const q = state.search.trim().toLocaleLowerCase('fr');
    return state.members.filter((m) => {
      if (state.rank !== 'TOUS' && m.rank !== state.rank) return false;
      if (!q) return true;
      const hay = `${m.player_name || ''} ${m.display_name || ''} ${m.rank || ''} ${m.officer_title || ''}`.toLocaleLowerCase('fr');
      return hay.includes(q);
    });
  }

  function canToggleActive(m) {
    if (!state.me?.permissions?.can_admin_members) return false;
    if (m.rank === 'R5') return false;
    if (m.system_role === 'OWNER') return false;
    if (m.id === state.me?.user?.id) return false;
    if (m.rank === 'R4' && !(state.me?.permissions?.is_owner || state.me?.membership?.rank === 'R5')) return false;
    return true;
  }

  function memberRow(m) {
    const toggleAllowed = canToggleActive(m);
    const toggleLabel = m.active ? 'Désactiver' : 'Réactiver';
    const last = relativeLastSeen(m.last_login_at);
    return `
      <article class="w6-member ${m.active ? '' : 'is-inactive'}" data-member-id="${esc(m.id)}">
        ${avatarHtml(m)}
        <div class="w6-member-copy">
          <strong class="w6-member-name">${esc(memberName(m))}</strong>
          <div class="w6-member-status">
            <span class="w6-rank ${rankClass(m.rank)}">${esc(m.rank)}</span>
            <span>${esc(statusLine(m))}</span>
          </div>
          <div class="w6-last">🕒 Dernière connexion · ${esc(last)}</div>
        </div>
        <div class="w6-member-actions">
          <button class="w6-btn w6-btn-gold w6-btn-edit" type="button" data-action="edit" data-id="${esc(m.id)}">
            <span>✏️</span><span>Modifier</span>
          </button>
          <button class="w6-btn w6-btn-outline" type="button" data-action="toggle" data-id="${esc(m.id)}"
            ${toggleAllowed ? '' : 'disabled'}>
            ${toggleAllowed ? esc(toggleLabel) : 'Protégé'}
          </button>
        </div>
      </article>`;
  }

  function renderList() {
    const list = document.getElementById('w6MemberList');
    const count = document.getElementById('w6Count');
    if (!list) return;
    const filtered = filteredMembers();
    if (count) count.textContent = `${filtered.length} profil${filtered.length > 1 ? 's' : ''}`;
    list.innerHTML = filtered.length
      ? filtered.map(memberRow).join('')
      : '<div class="w6-empty">Aucun joueur trouvé.</div>';

    document.querySelectorAll('#w6RankFilters [data-rank]').forEach((btn) => {
      const active = btn.dataset.rank === state.rank;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', String(active));
    });
  }

  function buildRoot() {
    if (document.getElementById('wfggMembersAdminView')) return;
    const root = document.createElement('section');
    root.id = 'wfggMembersAdminView';
    root.className = 'w6-view hidden';
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = `
      <header class="w6-topbar">
        <div class="w6-brand">
          <img id="w6AllianceLogo" class="w6-logo" alt="WfGg">
          <div class="w6-brand-copy">
            <strong id="w6BrandName">WfGg</strong>
            <span>Alliance · Last War</span>
          </div>
        </div>
        <div class="w6-top-actions">
          <span class="w6-online-dot" aria-label="Connecté"></span>
          <button type="button" class="w6-icon-btn" data-action="native-alliance" aria-label="Paramètres alliance">⚙️</button>
          <button type="button" class="w6-icon-btn" data-action="close-view" aria-label="Retour">↪</button>
        </div>
      </header>

      <main class="w6-main">
        <div class="w6-title-row">
          <h1>👥 Joueurs de l’alliance</h1>
          <span id="w6Count">0 profil</span>
        </div>

        <section class="w6-panel">
          <button type="button" class="w6-add" data-action="add">＋ Ajouter un joueur</button>

          <label class="w6-search-wrap">
            <span>🔎</span>
            <input id="w6Search" type="search" autocomplete="off" placeholder="Rechercher un pseudo…" aria-label="Rechercher un pseudo">
          </label>

          <nav id="w6RankFilters" class="w6-rank-filters" aria-label="Filtrer par rang">
            ${['TOUS','R5','R4','R3','R2','R1'].map((r) => `
              <button type="button" data-action="filter" data-rank="${r}" aria-pressed="${r === 'TOUS' ? 'true' : 'false'}" class="${r === 'TOUS' ? 'active' : ''}">${r}</button>
            `).join('')}
          </nav>

          <div id="w6MemberList" class="w6-member-list">
            <div class="w6-empty">Chargement des joueurs…</div>
          </div>
        </section>
      </main>

      <div id="w6Modal" class="w6-modal hidden" aria-hidden="true">
        <div class="w6-modal-backdrop" data-action="close-modal"></div>
        <section class="w6-sheet" role="dialog" aria-modal="true">
          <div class="w6-sheet-handle"></div>
          <button type="button" class="w6-sheet-close" data-action="close-modal" aria-label="Fermer">×</button>
          <div id="w6ModalBody"></div>
        </section>
      </div>
    `;
    document.body.appendChild(root);
    bindRootEvents(root);
  }

  function showView() {
    buildRoot();
    const root = document.getElementById('wfggMembersAdminView');
    if (!root) return;
    root.classList.remove('hidden');
    root.setAttribute('aria-hidden', 'false');
    document.documentElement.classList.add('w6-admin-open');
    state.open = true;
    loadMembers(true);
  }

  function closeView() {
    const root = document.getElementById('wfggMembersAdminView');
    root?.classList.add('hidden');
    root?.setAttribute('aria-hidden', 'true');
    document.documentElement.classList.remove('w6-admin-open');
    state.open = false;
    closeModal();
  }

  function openNativeAllianceSettings() {
    closeView();
    const profile = document.getElementById('profileTab');
    const alliance = document.getElementById('allianceTab');
    const tabs = document.querySelectorAll('#settingsOverlay .tab');
    if (!profile || !alliance) return;
    profile.classList.add('hidden');
    alliance.classList.remove('hidden');
    tabs.forEach((t) => t.classList.toggle('active', t.dataset.tab === 'alliance'));
  }

  function openModal(html) {
    const modal = document.getElementById('w6Modal');
    const body = document.getElementById('w6ModalBody');
    if (!modal || !body) return;
    body.innerHTML = html;
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeModal() {
    const modal = document.getElementById('w6Modal');
    modal?.classList.add('hidden');
    modal?.setAttribute('aria-hidden', 'true');
    state.editorId = null;
  }

  function editorMessage(text, error = false) {
    const box = document.getElementById('w6EditorMessage');
    if (!box) return;
    box.textContent = text;
    box.className = `w6-message${error ? ' error' : ''}`;
  }

  function rankOptions(m) {
    const values = ['R4', 'R3', 'R2', 'R1'];
    if (m?.rank === 'R5') values.unshift('R5');
    return values.map((r) => `<option value="${r}" ${m?.rank === r ? 'selected' : ''}>${r}</option>`).join('');
  }

  function officeOptions(m) {
    return OFFICES.map((o) => `<option value="${o}" ${m?.officer_title === o ? 'selected' : ''}>${esc(o ? OFFICE_LABELS[o] : 'Aucune')}</option>`).join('');
  }

  function openMemberForm(id = '') {
    if (!state.me?.permissions?.can_admin_members) return;
    const m = id ? state.members.find((x) => x.id === id) : null;
    state.editorId = m?.id || '';

    if (!m) {
      openModal(`
        <div class="w6-sheet-title">
          <div><span class="w6-kicker">Administration</span><h2>＋ Ajouter un joueur</h2></div>
        </div>
        <label class="w6-field"><span>Pseudo</span><input id="w6Pseudo" maxlength="40" placeholder="Pseudo exact"></label>
        <div class="w6-form-grid">
          <label class="w6-field"><span>Rang</span><select id="w6Rank">${rankOptions(null)}</select></label>
          <label class="w6-field"><span>Fonction R4</span><select id="w6Office">${officeOptions(null)}</select></label>
        </div>
        <p class="w6-info">Le code personnel à 6 chiffres sera généré automatiquement et affiché une seule fois.</p>
        <div id="w6EditorMessage"></div>
        <div class="w6-sheet-actions">
          <button class="w6-btn w6-btn-gold" type="button" data-action="save-member">💾 Enregistrer</button>
          <button class="w6-btn w6-btn-outline" type="button" data-action="close-modal">Annuler</button>
        </div>`);
      syncOfficeField();
      return;
    }

    const p = state.me.permissions || {};
    const ownerTarget = m.system_role === 'OWNER';
    const self = m.id === state.me?.user?.id;
    const rankDisabled = m.rank === 'R5' || (m.rank === 'R4' && !p.is_owner && state.me?.membership?.rank !== 'R5') || (ownerTarget && !p.is_owner);
    const officeDisabled = !p.can_assign_r4_offices || m.rank !== 'R4';
    const activeDisabled = m.rank === 'R5' || self || ownerTarget || (m.rank === 'R4' && !p.is_owner && state.me?.membership?.rank !== 'R5');
    const transferAllowed = Boolean(p.can_transfer_r5 && m.rank === 'R4' && !ownerTarget);

    openModal(`
      <div class="w6-editor-head">
        ${avatarHtml(m, 'large')}
        <div><span class="w6-kicker">Administration</span><h2>Modifier le joueur</h2><p>${esc(memberName(m))}${ownerTarget ? ' · OWNER' : ''}</p></div>
      </div>
      <div class="w6-form-grid">
        <label class="w6-field"><span>Rang</span><select id="w6Rank" ${rankDisabled ? 'disabled' : ''}>${rankOptions(m)}</select></label>
        <label class="w6-field"><span>Fonction R4</span><select id="w6Office" ${officeDisabled ? 'disabled' : ''}>${officeOptions(m)}</select></label>
      </div>
      <label class="w6-switch-row">
        <div><strong>Profil actif</strong><small>${ownerTarget ? 'Compte OWNER protégé' : (m.rank === 'R5' ? 'Transférer le R5 avant désactivation' : 'Autorise la connexion au portail')}</small></div>
        <input id="w6Active" type="checkbox" ${m.active ? 'checked' : ''} ${activeDisabled ? 'disabled' : ''}>
      </label>
      ${m.rank === 'R5' ? '<p class="w6-info">Pour changer le R5, ouvre un joueur R4 puis utilise « Nommer R5 ».</p>' : ''}
      <div id="w6EditorMessage"></div>
      <div class="w6-sheet-actions">
        <button class="w6-btn w6-btn-gold" type="button" data-action="save-member">💾 Enregistrer</button>
        <button class="w6-btn w6-btn-outline" type="button" data-action="reset-code" data-id="${esc(m.id)}">🔑 Nouveau code</button>
        ${transferAllowed ? `<button class="w6-btn w6-btn-outline" type="button" data-action="transfer-r5" data-id="${esc(m.id)}">♛ Nommer R5</button>` : ''}
      </div>`);
    syncOfficeField();
  }

  function syncOfficeField() {
    const rank = document.getElementById('w6Rank');
    const office = document.getElementById('w6Office');
    if (!rank || !office) return;
    const sync = () => {
      const allowed = rank.value === 'R4' && Boolean(state.me?.permissions?.can_assign_r4_offices);
      office.disabled = !allowed;
      if (!allowed) office.value = '';
    };
    rank.addEventListener('change', sync);
    sync();
  }

  function generateCode() {
    const a = new Uint32Array(1);
    crypto.getRandomValues(a);
    return String(a[0] % 1000000).padStart(6, '0');
  }

  async function createMemberWithUniqueCode(playerName, rank, officerTitle) {
    let lastError = null;
    for (let i = 0; i < 8; i += 1) {
      const code = generateCode();
      try {
        await api('/api/admin/members', {
          method: 'POST',
          body: JSON.stringify({ player_name: playerName, rank, officer_title: officerTitle || null, code })
        });
        return code;
      } catch (e) {
        lastError = e;
        if (!/CODE|PLAYER_OR_CODE_ALREADY_EXISTS/i.test(e.message)) throw e;
      }
    }
    throw lastError || new Error('Impossible de générer un code unique');
  }

  async function saveMemberForm() {
    const m = state.editorId ? state.members.find((x) => x.id === state.editorId) : null;
    const rank = document.getElementById('w6Rank')?.value || 'R3';
    const office = document.getElementById('w6Office')?.value || null;

    if (!m) {
      const pseudo = document.getElementById('w6Pseudo')?.value.trim();
      if (!pseudo) return editorMessage('Pseudo obligatoire.', true);
      try {
        const code = await createMemberWithUniqueCode(pseudo, rank, rank === 'R4' ? office : null);
        await loadMembers(true);
        openModal(`
          <span class="w6-kicker">Joueur ajouté</span><h2>✅ ${esc(pseudo)}</h2>
          <p>Code personnel :</p><div class="w6-new-code">${esc(code)}</div>
          <p class="w6-info">Ce code n’est affiché qu’une fois. Copie-le avant de fermer.</p>
          <div class="w6-sheet-actions">
            <button class="w6-btn w6-btn-gold" type="button" data-action="copy-code" data-code="${esc(code)}">📋 Copier le code</button>
            <button class="w6-btn w6-btn-outline" type="button" data-action="close-modal">Fermer</button>
          </div>`);
      } catch (e) { editorMessage(`Impossible d’ajouter : ${e.message}`, true); }
      return;
    }

    const active = document.getElementById('w6Active')?.checked ?? m.active;
    try {
      if (m.officer_title && rank !== 'R4') {
        await api(`/api/admin/members/${encodeURIComponent(m.id)}`, { method: 'PATCH', body: JSON.stringify({ officer_title: null }) });
        m.officer_title = null;
      }
      if (rank !== m.rank) {
        await api(`/api/admin/members/${encodeURIComponent(m.id)}`, { method: 'PATCH', body: JSON.stringify({ rank }) });
        m.rank = rank;
      }
      const nextOffice = rank === 'R4' ? (office || null) : null;
      if (rank === 'R4' && nextOffice !== (m.officer_title || null)) {
        await api(`/api/admin/members/${encodeURIComponent(m.id)}`, { method: 'PATCH', body: JSON.stringify({ officer_title: nextOffice }) });
        m.officer_title = nextOffice;
      }
      if (Boolean(active) !== Boolean(m.active)) {
        await api(`/api/admin/members/${encodeURIComponent(m.id)}`, { method: 'PATCH', body: JSON.stringify({ active: Boolean(active) }) });
        m.active = Boolean(active);
      }
      await loadMembers(true);
      editorMessage('Modifications enregistrées.');
      setTimeout(closeModal, 450);
    } catch (e) { editorMessage(`Impossible d’enregistrer : ${e.message}`, true); }
  }

  async function toggleActive(id) {
    const m = state.members.find((x) => x.id === id);
    if (!m || !canToggleActive(m)) return;
    try {
      await api(`/api/admin/members/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        body: JSON.stringify({ active: !m.active })
      });
      await loadMembers(true);
    } catch (e) {
      openModal(`<span class="w6-kicker">Erreur</span><h2>Modification impossible</h2><p class="w6-info">${esc(e.message)}</p><div class="w6-sheet-actions"><button class="w6-btn w6-btn-outline" type="button" data-action="close-modal">Fermer</button></div>`);
    }
  }

  async function resetMemberCode(id) {
    const m = state.members.find((x) => x.id === id);
    if (!m) return;
    const code = generateCode();
    try {
      await api(`/api/admin/members/${encodeURIComponent(id)}/code`, {
        method: 'POST',
        body: JSON.stringify({ code })
      });
      openModal(`
        <span class="w6-kicker">Nouveau code</span><h2>🔑 ${esc(memberName(m))}</h2>
        <div class="w6-new-code">${esc(code)}</div>
        <p class="w6-info">Toutes les anciennes sessions de ce joueur sont fermées.</p>
        <div class="w6-sheet-actions">
          <button class="w6-btn w6-btn-gold" type="button" data-action="copy-code" data-code="${esc(code)}">📋 Copier le code</button>
          <button class="w6-btn w6-btn-outline" type="button" data-action="close-modal">Fermer</button>
        </div>`);
    } catch (e) { editorMessage(`Impossible de créer le code : ${e.message}`, true); }
  }

  function transferR5(id) {
    const m = state.members.find((x) => x.id === id);
    if (!m || !state.me?.permissions?.can_transfer_r5) return;
    state.editorId = id;
    openModal(`
      <span class="w6-kicker">Leadership</span><h2>♛ Nommer ${esc(memberName(m))} R5</h2>
      <p class="w6-info">Le R5 actuel sera rétrogradé R4. Confirme l’opération avec ton code personnel.</p>
      <label class="w6-field"><span>Ton code actuel à 6 chiffres</span><input id="w6OwnerCode" type="password" inputmode="numeric" maxlength="6" pattern="[0-9]{6}" placeholder="••••••"></label>
      <div id="w6EditorMessage"></div>
      <div class="w6-sheet-actions">
        <button class="w6-btn w6-btn-gold" type="button" data-action="confirm-r5" data-id="${esc(id)}">Confirmer le changement de R5</button>
        <button class="w6-btn w6-btn-outline" type="button" data-action="close-modal">Annuler</button>
      </div>`);
  }

  async function confirmTransferR5(id) {
    const currentCode = document.getElementById('w6OwnerCode')?.value.trim();
    if (!/^\d{6}$/.test(currentCode || '')) return editorMessage('Code personnel requis.', true);
    try {
      await api('/api/admin/leadership/transfer', {
        method: 'POST',
        body: JSON.stringify({ target_user_id: id, current_code: currentCode })
      });
      await loadMembers(true);
      editorMessage('R5 modifié.');
      setTimeout(closeModal, 550);
    } catch (e) { editorMessage(`Impossible de changer le R5 : ${e.message}`, true); }
  }

  async function copyCode(code, button) {
    try {
      await navigator.clipboard.writeText(code);
    } catch (_) {
      const t = document.createElement('textarea');
      t.value = code;
      t.style.position = 'fixed';
      t.style.left = '-9999px';
      document.body.appendChild(t);
      t.select();
      document.execCommand('copy');
      t.remove();
    }
    if (button) button.textContent = '✅ Copié';
  }

  async function loadMembers(force = false) {
    if (!token()) return;
    if (state.busy && !force) return;
    state.busy = true;
    const list = document.getElementById('w6MemberList');
    try {
      state.me = await api('/api/me');
      const logo = document.getElementById('w6AllianceLogo');
      const name = document.getElementById('w6BrandName');
      if (name) name.textContent = state.me?.alliance?.name || 'WfGg';
      if (logo) {
        logo.src = state.me?.alliance?.logo_url || 'https://wfgg-train-app.pages.dev/assets/icon-192.png';
      }
      if (!state.me?.permissions?.can_admin_members) {
        if (list) list.innerHTML = '<div class="w6-empty">Accès administrateur requis.</div>';
        return;
      }
      const data = await api('/api/admin/members');
      state.members = data.members || [];
      renderList();
    } catch (e) {
      if (list) list.innerHTML = `<div class="w6-empty">Erreur : ${esc(e.message)}</div>`;
      console.error('[WfGg members v0.6.0]', e);
    } finally {
      state.busy = false;
    }
  }

  function bindRootEvents(root) {
    root.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn || btn.disabled) return;
      const action = btn.dataset.action;
      const id = btn.dataset.id || '';

      if (action === 'close-view') return closeView();
      if (action === 'native-alliance') return openNativeAllianceSettings();
      if (action === 'close-modal') return closeModal();
      if (action === 'add') return openMemberForm();
      if (action === 'edit') return openMemberForm(id);
      if (action === 'filter') {
        state.rank = btn.dataset.rank || 'TOUS';
        renderList();
        return;
      }
      if (action === 'toggle') return toggleActive(id);
      if (action === 'save-member') return saveMemberForm();
      if (action === 'reset-code') return resetMemberCode(id);
      if (action === 'transfer-r5') return transferR5(id);
      if (action === 'confirm-r5') return confirmTransferR5(id);
      if (action === 'copy-code') return copyCode(btn.dataset.code || '', btn);
    });

    root.addEventListener('input', (e) => {
      if (e.target.id === 'w6Search') {
        state.search = e.target.value || '';
        renderList();
      }
    });
  }

  function interceptAllianceTab() {
    document.addEventListener('click', (e) => {
      const target = e.target.closest?.('#allianceTabButton');
      if (!target) return;
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      showView();
    }, true);
  }

  function hideLegacyMemberAdmin() {
    document.documentElement.classList.add('w6-single-admin');
  }

  function start() {
    buildRoot();
    hideLegacyMemberAdmin();
    interceptAllianceTab();
    window.WFGG_MEMBERS_ADMIN = Object.freeze({
      version: VERSION,
      open: showView,
      close: closeView,
      reload: () => loadMembers(true)
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();