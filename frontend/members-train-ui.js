/* WfGg Portal — Members UI v0.5.0
   Reimplementation based on the member-management ergonomics of WfGg Train v1.12.
   Uses a dedicated panel so the legacy/native portal renderer cannot overwrite controls. */
(() => {
  'use strict';

  const cfg = window.WFGG_PORTAL_CONFIG || { API_BASE: '' };
  const TOKEN_KEY = 'wfgg_portal_session';
  const LEGACY = window.WFGG_LEGACY_AVATARS || {};
  const RANKS = ['R5', 'R4', 'R3', 'R2', 'R1'];
  const OFFICES = ['', 'WARLORD', 'RECRUITER', 'MUSE', 'BUTLER'];
  const OFFICE_LABELS = {
    WARLORD: 'Seigneur de guerre',
    RECRUITER: 'Recruteur',
    MUSE: 'Muse',
    BUTLER: 'Majordome'
  };

  const state = {
    me: null,
    members: [],
    rank: 'TOUS',
    search: '',
    busy: false,
    mounted: false
  };

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

  const token = () => localStorage.getItem(TOKEN_KEY);

  function initials(name = '?') {
    return String(name).trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?';
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (token()) headers.set('Authorization', `Bearer ${token()}`);
    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(`${cfg.API_BASE}${path}`, { ...options, headers });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data?.error || `HTTP_${response.status}`);
    return data;
  }

  function memberName(m) {
    return m?.display_name || m?.player_name || '?';
  }

  function avatarUrl(m) {
    return m?.avatar_url || LEGACY[m?.player_name] || LEGACY[m?.display_name] || '';
  }

  function avatarHtml(m, cls = '') {
    const name = memberName(m);
    const url = avatarUrl(m);
    if (url) {
      return `<span class="wt-member-avatar ${cls}" role="img" aria-label="${esc(name)}" style="background-image:url('${esc(url)}')"></span>`;
    }
    return `<span class="wt-member-avatar wt-initials ${cls}" aria-label="${esc(name)}">${esc(initials(name))}</span>`;
  }

  function rankBadge(rank) {
    return `<span class="wt-rank-badge wt-${esc(rank)}">${esc(rank)}</span>`;
  }

  function relativeLastSeen(value) {
    if (!value) return { online: false, text: 'jamais connecté' };
    const ts = new Date(value).getTime();
    if (!Number.isFinite(ts)) return { online: false, text: String(value) };
    const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (sec < 100) return { online: true, text: 'En ligne maintenant' };
    const min = Math.floor(sec / 60);
    if (min < 60) return { online: false, text: `il y a ${min} min` };
    const hour = Math.floor(min / 60);
    if (hour < 24) return { online: false, text: `il y a ${hour} h` };
    const day = Math.floor(hour / 24);
    if (day < 30) return { online: false, text: `il y a ${day} jour${day > 1 ? 's' : ''}` };
    const month = Math.max(1, Math.floor(day / 30));
    if (day < 365) return { online: false, text: `il y a ${month} mois` };
    const year = Math.max(1, Math.floor(day / 365));
    return { online: false, text: `il y a ${year} an${year > 1 ? 's' : ''}` };
  }

  function memberLastSeenLine(m) {
    const x = relativeLastSeen(m.last_login_at);
    const exact = m.last_login_at ? new Date(m.last_login_at).toLocaleString('fr-FR') : '';
    if (x.online) return `<small class="wt-member-last-seen online" ${exact ? `title="${esc(exact)}"` : ''}>🟢 ${esc(x.text)}</small>`;
    return `<small class="wt-member-last-seen" ${exact ? `title="${esc(exact)}"` : ''}>🕒 Dernière connexion · ${esc(x.text)}</small>`;
  }

  function statusText(m) {
    const parts = [rankBadge(m.rank), m.active ? 'actif' : 'désactivé'];
    if (m.officer_title) parts.push(OFFICE_LABELS[m.officer_title] || m.officer_title);
    if (m.system_role === 'OWNER') parts.push('<span class="wt-owner-label">OWNER</span>');
    return parts.join(' · ');
  }

  function canToggleActive(m) {
    if (!state.me?.permissions?.can_admin_members) return false;
    if (m.rank === 'R5') return false;
    if (m.system_role === 'OWNER') return false;
    if (m.id === state.me?.user?.id) return false;
    if (m.rank === 'R4' && !(state.me?.permissions?.is_owner || state.me?.membership?.rank === 'R5')) return false;
    return true;
  }

  function memberRows(list) {
    return list.map((m) => {
      const toggleAllowed = canToggleActive(m);
      const toggleLabel = m.active ? 'Désactiver' : 'Réactiver';
      const toggleClass = m.active ? 'outline' : 'success';
      return `<div class="wt-member-row ${m.active ? '' : 'is-inactive'}">
        ${avatarHtml(m, 'xs')}
        <div class="wt-member-row-main">
          <b>${esc(memberName(m))}</b>
          <small>${statusText(m)}</small>
          ${memberLastSeenLine(m)}
        </div>
        <div class="wt-member-admin-actions">
          <button type="button" class="wt-btn small gold" onclick="WFGG_TRAIN_MEMBERS.openMemberForm('${esc(m.id)}')">✏️ Modifier</button>
          <button type="button" class="wt-btn small ${toggleClass}" ${toggleAllowed ? `onclick="WFGG_TRAIN_MEMBERS.toggleActive('${esc(m.id)}')"` : 'disabled'}>${toggleAllowed ? toggleLabel : 'Protégé'}</button>
        </div>
      </div>`;
    }).join('');
  }

  function currentFilteredList() {
    let list = state.members;
    if (state.search) {
      const s = state.search.trim().toLowerCase();
      list = !s ? state.members : state.members.filter((m) => {
        const hay = `${m.player_name || ''} ${m.display_name || ''} ${m.rank || ''}`.toLowerCase();
        return hay.includes(s);
      });
      return list;
    }
    return state.rank === 'TOUS' ? list : list.filter((m) => m.rank === state.rank);
  }

  function paintList(list = currentFilteredList()) {
    const box = document.getElementById('wtAdminMembers');
    const count = document.getElementById('wtMembersCount');
    if (!box) return;
    if (count) count.textContent = `${list.length} profil${list.length > 1 ? 's' : ''}`;
    box.innerHTML = list.length ? memberRows(list) : '<div class="wt-empty">Aucun membre trouvé.</div>';
  }

  function filterMembers(rank, btn) {
    state.search = '';
    state.rank = rank;
    const search = document.getElementById('wtMemberSearchAdmin');
    if (search) search.value = '';
    document.querySelectorAll('#wtMemberPanel .wt-chip').forEach((x) => x.classList.remove('active'));
    if (btn) btn.classList.add('active');
    paintList(rank === 'TOUS' ? state.members : state.members.filter((m) => m.rank === rank));
  }

  function searchMembers(q) {
    state.search = String(q || '');
    const s = state.search.trim().toLowerCase();
    paintList(!s ? state.members : state.members.filter((m) => {
      const hay = `${m.player_name || ''} ${m.display_name || ''} ${m.rank || ''}`.toLowerCase();
      return hay.includes(s);
    }));
  }

  function injectStyles() {
    if (document.getElementById('wt-members-style-v050')) return;
    const style = document.createElement('style');
    style.id = 'wt-members-style-v050';
    style.textContent = `
      /* Hide the experimental/native member renderers. The v0.5 panel owns this section. */
      #wfggMemberToolbar, #memberList, #addMemberForm, #memberMessage { display:none !important; }
      #refreshMembersButton { display:none !important; }
      #allianceTab > .section-heading { display:none !important; }

      #wtMemberPanel { margin-top:10px; }
      .wt-section-title{display:flex;align-items:end;justify-content:space-between;gap:12px;margin:0 0 10px}
      .wt-section-title h2{font-size:1.35rem;letter-spacing:0;margin:0}.wt-section-title p{margin:0;color:#91a6ba;font-size:.78rem;font-weight:800}
      .wt-admin-panel{background:#0a294d;border:1px solid rgba(240,196,91,.18);border-radius:18px;padding:15px;margin-bottom:12px;box-shadow:0 14px 35px rgba(0,0,0,.18)}
      .wt-btn{border:0;border-radius:13px;padding:11px 14px;font-weight:950;display:inline-flex;align-items:center;justify-content:center;gap:7px;text-decoration:none;cursor:pointer;touch-action:manipulation;-webkit-tap-highlight-color:rgba(240,196,91,.22)}
      .wt-btn.gold{background:linear-gradient(#ffe39a,#e7b642);color:#12233d}.wt-btn.outline{background:#0b294c;color:#fff;border:1px solid rgba(240,196,91,.34)}
      .wt-btn.danger{background:#8b2e35;color:#fff}.wt-btn.success{background:#0e7253;color:#fff}.wt-btn.full{width:100%;margin-top:0}.wt-btn.small{padding:8px 10px;font-size:.82rem}
      .wt-btn:disabled{opacity:.42;cursor:not-allowed}.wt-btn:active:not(:disabled){transform:scale(.985)}
      .wt-admin-search{width:100%;margin:12px 0 9px;border:1px solid rgba(240,196,91,.22);border-radius:13px;background:#071f3a;color:#fff;padding:12px 13px}
      .wt-admin-search::placeholder{color:#90a3b8}
      .wt-chips{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0 14px}.wt-chip{border:1px solid rgba(240,196,91,.25);background:#0a294d;color:#fff;border-radius:999px;padding:7px 10px;font-weight:850;font-size:.78rem;cursor:pointer;touch-action:manipulation}
      .wt-chip.active{background:#f0c45b;color:#13233b;box-shadow:0 0 0 2px rgba(240,196,91,.10)}
      .wt-member-list{display:grid;gap:8px}.wt-member-row{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:9px;padding:9px;background:#082341;border-radius:14px;border:1px solid rgba(255,255,255,.025)}
      .wt-member-row.is-inactive{opacity:.62}.wt-member-row-main{min-width:0}.wt-member-row b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wt-member-row small{color:#90a3b8}
      .wt-member-admin-actions{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}
      .wt-member-avatar{width:58px;height:58px;aspect-ratio:1/1;border-radius:10px;display:grid;place-items:center;background:#071d39 center/contain no-repeat;border:2px solid rgba(240,196,91,.70);font-weight:950;color:#ffe197;flex:none;box-shadow:0 5px 16px rgba(0,0,0,.22)}
      .wt-member-avatar.editor{width:76px;height:76px;border-radius:13px}.wt-member-last-seen{display:block!important;margin-top:4px!important;color:#8fa5ba!important;font-size:.68rem!important;line-height:1.25}.wt-member-last-seen.online{color:#70dda0!important;font-weight:800}
      .wt-rank-badge{display:inline-block;padding:2px 6px;border-radius:999px;font-size:.68rem;font-weight:950;background:#17385b;color:#dbe7f2;border:1px solid rgba(240,196,91,.18)}
      .wt-rank-badge.wt-R5{background:#73551a;color:#ffe39a}.wt-rank-badge.wt-R4{background:#3c386b;color:#e2d7ff}.wt-owner-label{color:#ffe197;font-weight:950}.wt-empty{padding:22px;text-align:center;border:1px dashed rgba(240,196,91,.25);border-radius:18px;color:#9badc0}

      .wt-modal{position:fixed;inset:0;z-index:120;display:grid;place-items:end center}.wt-modal.hidden{display:none}.wt-modal-backdrop{position:absolute;inset:0;background:rgba(0,8,18,.74);backdrop-filter:blur(5px)}
      .wt-modal-card{position:relative;z-index:1;width:min(620px,100%);max-height:88vh;overflow:auto;background:#071d39;border:1px solid rgba(240,196,91,.32);border-radius:22px 22px 0 0;padding:22px 16px calc(22px + env(safe-area-inset-bottom));box-shadow:0 -20px 60px rgba(0,0,0,.4);color:#fff}
      .wt-modal-close{position:absolute;right:13px;top:12px;width:38px;height:38px;border-radius:50%;border:1px solid rgba(255,255,255,.15);background:#0d3157;color:#fff;font-size:1.3rem;cursor:pointer}.wt-modal-card h2{margin:0 45px 12px 0;font-size:1.45rem;letter-spacing:0}.wt-modal-card p{color:#b4c2d0}
      .wt-field-label{display:block;color:#dce6f0;font-weight:850;font-size:.78rem;margin:10px 0 6px}.wt-modal-card input,.wt-modal-card select{width:100%;border:1px solid rgba(240,196,91,.20);border-radius:13px;background:#0a294d;color:#fff;padding:12px 13px}
      .wt-avatar-edit-preview{display:flex;align-items:center;gap:10px;margin:8px 0;color:#a9bacb}.wt-toggle-row{display:flex;align-items:center;justify-content:space-between;gap:12px;background:#0a294d;border:1px solid rgba(240,196,91,.16);border-radius:14px;padding:11px 12px;margin-top:12px}.wt-toggle-row input{width:22px;height:22px;accent-color:#e7b642}
      .wt-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.wt-actions .wt-btn{flex:1 1 140px}.wt-warning{background:#5a4118;color:#ffeab0;border:1px solid #8f6d29;border-radius:14px;padding:11px;font-size:.82rem;margin:10px 0}.wt-new-pin{font-size:2rem;font-weight:950;letter-spacing:.22em;text-align:center;color:#ffe197;background:#082341;border:1px solid rgba(240,196,91,.28);border-radius:14px;padding:16px;margin:12px 0}
      .wt-editor-header{display:flex;align-items:center;gap:12px;margin-bottom:12px}.wt-editor-header h2{margin-bottom:3px}.wt-editor-sub{color:#93a7ba;font-size:.78rem}.wt-form-message{margin-top:10px;padding:10px 12px;border-radius:12px;background:#0e674b;color:#fff;font-weight:800;font-size:.8rem}.wt-form-message.error{background:#8b2e35}
      .wt-grid-two{display:grid;grid-template-columns:1fr 1fr;gap:9px}

      @media(max-width:520px){
        .wt-member-admin-actions{flex-direction:column}.wt-member-admin-actions .wt-btn{width:100%}
        .wt-member-avatar{width:58px;height:58px}.wt-grid-two{grid-template-columns:1fr}
      }
    `;
    document.head.appendChild(style);
  }

  function ensureModal() {
    let root = document.getElementById('wtMemberModal');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'wtMemberModal';
    root.className = 'wt-modal hidden';
    root.innerHTML = '<div class="wt-modal-backdrop"></div><div class="wt-modal-card"><button type="button" class="wt-modal-close" onclick="WFGG_TRAIN_MEMBERS.closeModal()">×</button><div id="wtModalBody"></div></div>';
    document.body.appendChild(root);
    root.querySelector('.wt-modal-backdrop').addEventListener('click', closeModal);
    return root;
  }

  function openModal(html) {
    const root = ensureModal();
    root.querySelector('#wtModalBody').innerHTML = html;
    root.classList.remove('hidden');
  }

  function closeModal() {
    document.getElementById('wtMemberModal')?.classList.add('hidden');
  }

  function editorMessage(text, error = false) {
    const box = document.getElementById('wtEditorMessage');
    if (!box) return;
    box.textContent = text;
    box.className = `wt-form-message${error ? ' error' : ''}`;
  }

  function generateCode() {
    const a = new Uint32Array(1);
    crypto.getRandomValues(a);
    return String(a[0] % 1000000).padStart(6, '0');
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

    if (!m) {
      openModal(`<h2>＋ Ajouter un joueur</h2>
        <label class="wt-field-label">Pseudo</label>
        <input id="wtMemberPseudoField" placeholder="Pseudo exact" maxlength="40">
        <div class="wt-grid-two">
          <div><label class="wt-field-label">Rang</label><select id="wtMemberRankField">${['R4','R3','R2','R1'].map((r) => `<option value="${r}" ${r === 'R3' ? 'selected' : ''}>${r}</option>`).join('')}</select></div>
          <div><label class="wt-field-label">Fonction R4</label><select id="wtMemberOfficeField">${officeOptions(null)}</select></div>
        </div>
        <div class="wt-warning">Le code personnel à 6 chiffres sera généré automatiquement et affiché une seule fois après création. Pour nommer un R5, crée d’abord le membre en R4.</div>
        <div id="wtEditorMessage"></div>
        <div class="wt-actions"><button type="button" class="wt-btn gold" onclick="WFGG_TRAIN_MEMBERS.saveMemberForm()">💾 Enregistrer</button><button type="button" class="wt-btn outline" onclick="WFGG_TRAIN_MEMBERS.closeModal()">Annuler</button></div>`);
      const rank = document.getElementById('wtMemberRankField');
      const office = document.getElementById('wtMemberOfficeField');
      const syncOffice = () => { if (office) { office.disabled = rank?.value !== 'R4'; if (rank?.value !== 'R4') office.value = ''; } };
      rank?.addEventListener('change', syncOffice); syncOffice();
      return;
    }

    const p = state.me.permissions || {};
    const ownerTarget = m.system_role === 'OWNER';
    const self = m.id === state.me?.user?.id;
    const rankDisabled = m.rank === 'R5' || (m.rank === 'R4' && !p.is_owner && state.me?.membership?.rank !== 'R5') || (ownerTarget && !p.is_owner);
    const officeDisabled = !p.can_assign_r4_offices || m.rank !== 'R4';
    const activeDisabled = m.rank === 'R5' || self || ownerTarget || (m.rank === 'R4' && !p.is_owner && state.me?.membership?.rank !== 'R5');
    const transferAllowed = Boolean(p.can_transfer_r5 && m.rank === 'R4' && !ownerTarget);

    openModal(`<div class="wt-editor-header">${avatarHtml(m, 'editor')}<div><h2>✏️ Modifier le joueur</h2><div class="wt-editor-sub">${esc(memberName(m))}${ownerTarget ? ' · OWNER' : ''}</div></div></div>
      <input type="hidden" id="wtMemberIdField" value="${esc(m.id)}">
      <label class="wt-field-label">Pseudo</label>
      <input id="wtMemberPseudoField" value="${esc(memberName(m))}" readonly>
      <div class="wt-grid-two">
        <div><label class="wt-field-label">Rang</label><select id="wtMemberRankField" ${rankDisabled ? 'disabled' : ''}>${rankOptions(m)}</select></div>
        <div><label class="wt-field-label">Fonction R4</label><select id="wtMemberOfficeField" ${officeDisabled ? 'disabled' : ''}>${officeOptions(m)}</select></div>
      </div>
      <label class="wt-toggle-row"><span><b>Profil actif</b><small>${ownerTarget ? 'Compte OWNER protégé' : (m.rank === 'R5' ? 'Transférer le R5 avant désactivation' : '')}</small></span><input id="wtMemberActiveField" type="checkbox" ${m.active ? 'checked' : ''} ${activeDisabled ? 'disabled' : ''}></label>
      ${m.rank === 'R5' ? '<div class="wt-warning">Pour changer le R5, sélectionne un R4 dans la liste puis utilise « Nommer R5 ».</div>' : ''}
      <div id="wtEditorMessage"></div>
      <div class="wt-actions">
        <button type="button" class="wt-btn gold" onclick="WFGG_TRAIN_MEMBERS.saveMemberForm()">💾 Enregistrer</button>
        <button type="button" class="wt-btn outline" onclick="WFGG_TRAIN_MEMBERS.resetMemberPin('${esc(m.id)}')">🔑 Nouveau code</button>
        ${transferAllowed ? `<button type="button" class="wt-btn outline" onclick="WFGG_TRAIN_MEMBERS.transferR5('${esc(m.id)}')">♛ Nommer R5</button>` : ''}
      </div>`);

    const rank = document.getElementById('wtMemberRankField');
    const office = document.getElementById('wtMemberOfficeField');
    rank?.addEventListener('change', () => {
      if (!office || !p.can_assign_r4_offices) return;
      office.disabled = rank.value !== 'R4';
      if (rank.value !== 'R4') office.value = '';
    });
  }

  async function createMemberWithUniqueCode(playerName, rank, officerTitle) {
    let lastError = null;
    for (let i = 0; i < 6; i += 1) {
      const code = generateCode();
      try {
        const result = await api('/api/admin/members', {
          method: 'POST',
          body: JSON.stringify({ player_name: playerName, rank, officer_title: officerTitle || null, code })
        });
        return { result, code };
      } catch (e) {
        lastError = e;
        if (!/CODE|PLAYER_OR_CODE_ALREADY_EXISTS/i.test(e.message)) throw e;
      }
    }
    throw lastError || new Error('Impossible de générer un code unique');
  }

  async function saveMemberForm() {
    const id = document.getElementById('wtMemberIdField')?.value || '';
    const m = id ? state.members.find((x) => x.id === id) : null;
    const rank = document.getElementById('wtMemberRankField')?.value || 'R3';
    const office = document.getElementById('wtMemberOfficeField')?.value || null;

    if (!m) {
      const pseudo = document.getElementById('wtMemberPseudoField')?.value.trim();
      if (!pseudo) return editorMessage('Pseudo obligatoire.', true);
      try {
        const { code } = await createMemberWithUniqueCode(pseudo, rank, rank === 'R4' ? office : null);
        await loadMembers(true);
        openModal(`<h2>✅ Joueur ajouté</h2><p>Code personnel de <strong>${esc(pseudo)}</strong> :</p><div class="wt-new-pin">${esc(code)}</div><div class="wt-warning">Ce code n’est affiché qu’une fois. Copie-le avant de fermer cette fenêtre.</div><div class="wt-actions"><button type="button" class="wt-btn gold" onclick="WFGG_TRAIN_MEMBERS.copyCode('${esc(code)}', this)">📋 Copier le code</button><button type="button" class="wt-btn outline" onclick="WFGG_TRAIN_MEMBERS.closeModal()">Fermer</button></div>`);
      } catch (e) { editorMessage(`Impossible d’ajouter le joueur : ${e.message}`, true); }
      return;
    }

    const active = document.getElementById('wtMemberActiveField')?.checked ?? m.active;
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
      editorMessage('Profil corrigé.');
      await loadMembers(true);
      setTimeout(closeModal, 450);
    } catch (e) { editorMessage(`Impossible d’enregistrer : ${e.message}`, true); }
  }

  async function toggleActive(id) {
    const m = state.members.find((x) => x.id === id);
    if (!m || !canToggleActive(m)) return;
    try {
      await api(`/api/admin/members/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ active: !m.active }) });
      await loadMembers(true);
    } catch (e) {
      openModal(`<h2>⚠️ Modification impossible</h2><div class="wt-warning">${esc(e.message)}</div><div class="wt-actions"><button type="button" class="wt-btn outline" onclick="WFGG_TRAIN_MEMBERS.closeModal()">Fermer</button></div>`);
    }
  }

  async function resetMemberPin(id) {
    const m = state.members.find((x) => x.id === id);
    if (!m) return;
    const code = generateCode();
    try {
      await api(`/api/admin/members/${encodeURIComponent(id)}/code`, { method: 'POST', body: JSON.stringify({ code }) });
      openModal(`<h2>🔑 Nouveau code</h2><p>Nouveau code personnel de <strong>${esc(memberName(m))}</strong> :</p><div class="wt-new-pin">${esc(code)}</div><div class="wt-warning">Ce code n’est affiché qu’une fois. Toutes les sessions précédentes de ce joueur sont fermées.</div><div class="wt-actions"><button type="button" class="wt-btn gold" onclick="WFGG_TRAIN_MEMBERS.copyCode('${esc(code)}', this)">📋 Copier le code</button><button type="button" class="wt-btn outline" onclick="WFGG_TRAIN_MEMBERS.closeModal()">Fermer</button></div>`);
    } catch (e) { editorMessage(`Impossible de créer le code : ${e.message}`, true); }
  }

  function transferR5(id) {
    const m = state.members.find((x) => x.id === id);
    if (!m || !state.me?.permissions?.can_transfer_r5) return;
    openModal(`<h2>♛ Nommer ${esc(memberName(m))} R5</h2><div class="wt-warning">Le R5 actuel sera automatiquement rétrogradé R4. Cette opération exige ton code personnel actuel.</div><label class="wt-field-label">Ton code actuel à 6 chiffres</label><input id="wtOwnerCode" type="password" inputmode="numeric" maxlength="6" pattern="[0-9]{6}" placeholder="••••••"><div id="wtEditorMessage"></div><div class="wt-actions"><button type="button" class="wt-btn gold" onclick="WFGG_TRAIN_MEMBERS.confirmTransferR5('${esc(id)}')">Confirmer le changement de R5</button><button type="button" class="wt-btn outline" onclick="WFGG_TRAIN_MEMBERS.closeModal()">Annuler</button></div>`);
  }

  async function confirmTransferR5(id) {
    const currentCode = document.getElementById('wtOwnerCode')?.value.trim();
    if (!/^\d{6}$/.test(currentCode || '')) return editorMessage('Code personnel requis.', true);
    try {
      await api('/api/admin/leadership/transfer', { method: 'POST', body: JSON.stringify({ target_user_id: id, current_code: currentCode }) });
      editorMessage('R5 modifié.');
      await loadMembers(true);
      setTimeout(closeModal, 550);
    } catch (e) { editorMessage(`Impossible de changer le R5 : ${e.message}`, true); }
  }

  async function copyCode(code, button) {
    try { await navigator.clipboard.writeText(code); if (button) button.textContent = '✅ Copié'; }
    catch (_) {
      const t = document.createElement('textarea'); t.value = code; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); if (button) button.textContent = '✅ Copié';
    }
  }

  function ensurePanel() {
    const allianceTab = document.getElementById('allianceTab');
    const nativeList = document.getElementById('memberList');
    if (!allianceTab || !nativeList) return null;

    injectStyles();
    let panel = document.getElementById('wtMemberPanel');
    if (panel) return panel;

    panel = document.createElement('section');
    panel.id = 'wtMemberPanel';
    panel.innerHTML = `<div class="wt-section-title"><h2>👥 Joueurs de l’alliance</h2><p id="wtMembersCount">0 profil</p></div>
      <div class="wt-admin-panel">
        <button type="button" class="wt-btn gold full" onclick="WFGG_TRAIN_MEMBERS.openMemberForm()">＋ Ajouter un joueur</button>
        <input id="wtMemberSearchAdmin" class="wt-admin-search" placeholder="🔎 Rechercher un pseudo…" oninput="WFGG_TRAIN_MEMBERS.searchMembers(this.value)">
        <div class="wt-chips">${['TOUS','R5','R4','R3','R2','R1'].map((r) => `<button type="button" class="wt-chip ${r === 'TOUS' ? 'active' : ''}" onclick="WFGG_TRAIN_MEMBERS.filterMembers('${r}',this)">${r}</button>`).join('')}</div>
        <div id="wtAdminMembers" class="wt-member-list"><div class="wt-empty">Chargement des membres…</div></div>
      </div>`;

    nativeList.parentNode.insertBefore(panel, nativeList);
    state.mounted = true;
    return panel;
  }

  async function loadMembers(force = false) {
    if (!token()) return;
    if (state.busy && !force) return;
    state.busy = true;
    try {
      ensurePanel();
      state.me = await api('/api/me');
      if (!state.me?.permissions?.can_admin_members) return;
      const data = await api('/api/admin/members');
      state.members = data.members || [];
      paintList();
    } catch (e) {
      const box = document.getElementById('wtAdminMembers');
      if (box) box.innerHTML = `<div class="wt-empty">Erreur : ${esc(e.message)}</div>`;
      console.error('[WfGg Members v0.5]', e);
    } finally {
      state.busy = false;
    }
  }

  function scheduleLoad() {
    setTimeout(() => loadMembers(), 80);
    setTimeout(() => loadMembers(true), 450);
  }

  function bindHooks() {
    document.getElementById('allianceTabButton')?.addEventListener('click', scheduleLoad);
    document.getElementById('openSettingsButton')?.addEventListener('click', () => setTimeout(() => {
      if (!document.getElementById('allianceTab')?.classList.contains('hidden')) scheduleLoad();
    }, 100));
    window.addEventListener('storage', (e) => { if (e.key === TOKEN_KEY && e.newValue) scheduleLoad(); });
  }

  window.WFGG_TRAIN_MEMBERS = Object.freeze({
    loadMembers,
    filterMembers,
    searchMembers,
    openMemberForm,
    saveMemberForm,
    toggleActive,
    resetMemberPin,
    transferR5,
    confirmTransferR5,
    copyCode,
    closeModal
  });

  function start() {
    injectStyles();
    ensurePanel();
    bindHooks();
    if (token()) scheduleLoad();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
