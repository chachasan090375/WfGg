(() => {
  'use strict';

  const cfg = window.WFGG_PORTAL_CONFIG || { API_BASE: '', MODULES: {} };
  const STORAGE_TOKEN = 'wfgg_portal_session';
  const STORAGE_LANG = 'wfgg_portal_language';
  const RANKS = ['R1', 'R2', 'R3', 'R4', 'R5'];
  const state = {
    user: null,
    membership: null,
    alliance: null,
    lang: localStorage.getItem(STORAGE_LANG) || 'fr',
    members: []
  };

  const I18N = {
    fr: {
      auth: {
        title: 'Portail', subtitle: 'Entrez votre code WfGg pour vous connecter.', codeLabel: 'Code d’authentification',
        login: 'Se connecter', invalid: 'Code invalide ou compte désactivé.', rate: 'Trop de tentatives. Réessayez plus tard.'
      },
      portal: {
        brandSub: 'Portail', welcomeLabel: 'Bienvenue', subtitle: 'Choisissez votre espace WfGg.',
        profileRequired: 'Complétez votre profil avant d’ouvrir les modules.'
      },
      menu: { settings: 'Paramètres', logout: 'Déconnexion' },
      modules: {
        train: 'Organisation et rotations', guides: 'Saison 6 et Inter-Saison',
        simulatorTitle: 'Simulateur', simulator: 'Module autonome en préparation'
      },
      common: {
        soon: 'Bientôt', save: 'Enregistrer', refresh: 'Actualiser', saved: 'Enregistré.',
        error: 'Une erreur est survenue.', active: 'Actif', inactive: 'Inactif'
      },
      settings: {
        title: 'Paramètres', profileTab: 'Mon profil', allianceTab: 'Alliance', onboardingTitle: 'Première connexion',
        onboardingText: 'Choisissez votre pseudo affiché et votre langue. Vous pourrez ajouter ou changer votre photo à tout moment.'
      },
      profile: {
        avatar: 'Changer la photo', avatarHint: 'JPG, PNG ou WebP — 2 Mo max.', displayName: 'Pseudo affiché',
        language: 'Langue', alliance: 'Alliance', server: 'Serveur', rank: 'Rang'
      },
      alliance: {
        name: 'Nom de l’alliance', server: 'Serveur', logo: 'URL du logo', admin: 'Administration',
        members: 'Membres & codes', playerName: 'Pseudo', add: 'Ajouter', codeReset: 'Nouveau code',
        disable: 'Désactiver', enable: 'Réactiver', codePlaceholder: 'Code 6 chiffres'
      }
    },
    it: {
      auth: {
        title: 'Portale', subtitle: 'Inserisci il tuo codice WfGg per accedere.', codeLabel: 'Codice di autenticazione',
        login: 'Accedi', invalid: 'Codice non valido o account disattivato.', rate: 'Troppi tentativi. Riprova più tardi.'
      },
      portal: {
        brandSub: 'Portale', welcomeLabel: 'Benvenuto', subtitle: 'Scegli il tuo spazio WfGg.',
        profileRequired: 'Completa il profilo prima di aprire i moduli.'
      },
      menu: { settings: 'Impostazioni', logout: 'Disconnetti' },
      modules: {
        train: 'Organizzazione e rotazioni', guides: 'Stagione 6 e Interstagione',
        simulatorTitle: 'Simulatore', simulator: 'Modulo autonomo in preparazione'
      },
      common: {
        soon: 'Prossimamente', save: 'Salva', refresh: 'Aggiorna', saved: 'Salvato.',
        error: 'Si è verificato un errore.', active: 'Attivo', inactive: 'Disattivato'
      },
      settings: {
        title: 'Impostazioni', profileTab: 'Il mio profilo', allianceTab: 'Alleanza', onboardingTitle: 'Primo accesso',
        onboardingText: 'Scegli il nome visualizzato e la lingua. Potrai aggiungere o cambiare la foto in qualsiasi momento.'
      },
      profile: {
        avatar: 'Cambia foto', avatarHint: 'JPG, PNG o WebP — max 2 MB.', displayName: 'Nome visualizzato',
        language: 'Lingua', alliance: 'Alleanza', server: 'Server', rank: 'Grado'
      },
      alliance: {
        name: 'Nome alleanza', server: 'Server', logo: 'URL logo', admin: 'Amministrazione',
        members: 'Membri e codici', playerName: 'Nome giocatore', add: 'Aggiungi', codeReset: 'Nuovo codice',
        disable: 'Disattiva', enable: 'Riattiva', codePlaceholder: 'Codice 6 cifre'
      }
    },
    en: {
      auth: {
        title: 'Portal', subtitle: 'Enter your WfGg code to sign in.', codeLabel: 'Authentication code',
        login: 'Sign in', invalid: 'Invalid code or disabled account.', rate: 'Too many attempts. Try again later.'
      },
      portal: {
        brandSub: 'Portal', welcomeLabel: 'Welcome', subtitle: 'Choose your WfGg space.',
        profileRequired: 'Complete your profile before opening the modules.'
      },
      menu: { settings: 'Settings', logout: 'Sign out' },
      modules: {
        train: 'Organisation and rotations', guides: 'Season 6 and Interseason',
        simulatorTitle: 'Simulator', simulator: 'Standalone module in preparation'
      },
      common: {
        soon: 'Coming soon', save: 'Save', refresh: 'Refresh', saved: 'Saved.',
        error: 'Something went wrong.', active: 'Active', inactive: 'Inactive'
      },
      settings: {
        title: 'Settings', profileTab: 'My profile', allianceTab: 'Alliance', onboardingTitle: 'First sign-in',
        onboardingText: 'Choose your display name and language. You can add or change your photo at any time.'
      },
      profile: {
        avatar: 'Change photo', avatarHint: 'JPG, PNG or WebP — 2 MB max.', displayName: 'Display name',
        language: 'Language', alliance: 'Alliance', server: 'Server', rank: 'Rank'
      },
      alliance: {
        name: 'Alliance name', server: 'Server', logo: 'Logo URL', admin: 'Administration',
        members: 'Members & codes', playerName: 'Player name', add: 'Add', codeReset: 'New code',
        disable: 'Disable', enable: 'Enable', codePlaceholder: '6-digit code'
      }
    },
    es: {
      auth: {
        title: 'Portal', subtitle: 'Introduce tu código WfGg para iniciar sesión.', codeLabel: 'Código de autenticación',
        login: 'Entrar', invalid: 'Código no válido o cuenta desactivada.', rate: 'Demasiados intentos. Inténtalo más tarde.'
      },
      portal: {
        brandSub: 'Portal', welcomeLabel: 'Bienvenido', subtitle: 'Elige tu espacio WfGg.',
        profileRequired: 'Completa tu perfil antes de abrir los módulos.'
      },
      menu: { settings: 'Ajustes', logout: 'Cerrar sesión' },
      modules: {
        train: 'Organización y rotaciones', guides: 'Temporada 6 e Intertemporada',
        simulatorTitle: 'Simulador', simulator: 'Módulo autónomo en preparación'
      },
      common: {
        soon: 'Próximamente', save: 'Guardar', refresh: 'Actualizar', saved: 'Guardado.',
        error: 'Se ha producido un error.', active: 'Activo', inactive: 'Inactivo'
      },
      settings: {
        title: 'Ajustes', profileTab: 'Mi perfil', allianceTab: 'Alianza', onboardingTitle: 'Primera conexión',
        onboardingText: 'Elige tu nombre visible y tu idioma. Podrás añadir o cambiar tu foto en cualquier momento.'
      },
      profile: {
        avatar: 'Cambiar foto', avatarHint: 'JPG, PNG o WebP — 2 MB máx.', displayName: 'Nombre visible',
        language: 'Idioma', alliance: 'Alianza', server: 'Servidor', rank: 'Rango'
      },
      alliance: {
        name: 'Nombre de la alianza', server: 'Servidor', logo: 'URL del logo', admin: 'Administración',
        members: 'Miembros y códigos', playerName: 'Nombre del jugador', add: 'Añadir', codeReset: 'Nuevo código',
        disable: 'Desactivar', enable: 'Reactivar', codePlaceholder: 'Código de 6 cifras'
      }
    }
  };

  const $ = (id) => document.getElementById(id);
  const getPath = (obj, path) => path.split('.').reduce((current, key) => current && current[key], obj);
  const t = (path) => getPath(I18N[state.lang] || I18N.fr, path) || getPath(I18N.fr, path) || path;
  const canAdminAlliance = () => ['R4', 'R5'].includes(state.membership?.rank);
  const profileIsComplete = () => Boolean(state.user?.profile_completed);

  function applyLanguage() {
    document.documentElement.lang = state.lang;
    document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    document.querySelectorAll('.language-strip button').forEach((button) => {
      button.classList.toggle('active', button.dataset.lang === state.lang);
    });
    if ($('languageSelect')) $('languageSelect').value = state.lang;
    renderIdentity();
  }

  async function api(path, options = {}) {
    const token = localStorage.getItem(STORAGE_TOKEN);
    const headers = new Headers(options.headers || {});
    if (token) headers.set('Authorization', `Bearer ${token}`);
    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    const response = await fetch(`${cfg.API_BASE}${path}`, { ...options, headers });
    let data = null;
    try { data = await response.json(); } catch (_) {}

    if (response.status === 401) {
      clearSession();
      showAuth();
      throw new Error('UNAUTHORIZED');
    }
    if (!response.ok) throw new Error(data?.error || `HTTP_${response.status}`);
    return data;
  }

  function setView(name) {
    ['bootView', 'authView', 'portalView'].forEach((id) => $(id).classList.add('hidden'));
    $(name).classList.remove('hidden');
  }

  function showAuth() {
    setView('authView');
    setTimeout(() => $('authCode')?.focus(), 20);
  }

  function showPortal() {
    setView('portalView');
    renderIdentity();
    if (!profileIsComplete()) openSettings(true);
  }

  function clearSession() {
    localStorage.removeItem(STORAGE_TOKEN);
    state.user = null;
    state.membership = null;
    state.alliance = null;
    state.members = [];
  }

  function initials(name = '?') {
    return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('') || '?';
  }

  function paintAvatar(element, user) {
    if (!element || !user) return;
    if (user.avatar_url) {
      element.textContent = '';
      element.style.backgroundImage = `url("${String(user.avatar_url).replace(/"/g, '')}")`;
    } else {
      element.style.backgroundImage = '';
      element.textContent = initials(user.display_name || user.player_name);
    }
  }

  function renderIdentity() {
    if (!state.user) return;

    const name = state.user.display_name || state.user.player_name;
    const rank = state.membership?.rank || 'R3';
    $('topName').textContent = name;
    $('heroName').textContent = name;
    $('topRole').textContent = rank;
    paintAvatar($('topAvatar'), state.user);
    paintAvatar($('settingsAvatar'), state.user);

    $('displayName').value = name;
    $('languageSelect').value = state.user.language || state.lang;
    $('profileAlliance').textContent = state.alliance?.name || '—';
    $('profileServer').textContent = state.alliance?.server || '—';
    $('profileRank').textContent = rank;

    const admin = canAdminAlliance();
    $('allianceTabButton').classList.toggle('hidden', !admin);
    if (admin) {
      $('allianceName').value = state.alliance?.name || '';
      $('allianceServer').value = state.alliance?.server || '';
      $('allianceLogo').value = state.alliance?.logo_url || '';
    }

    $('profileRequiredBanner').classList.toggle('hidden', profileIsComplete());
    $('onboardingNotice').classList.toggle('hidden', profileIsComplete());
    document.querySelectorAll('.module-card[data-module]').forEach((card) => {
      card.classList.toggle('profile-locked', !profileIsComplete());
    });
  }

  function hydrate(data) {
    state.user = data.user;
    state.membership = data.membership;
    state.alliance = data.alliance;
    if (data.user?.language && I18N[data.user.language]) {
      state.lang = data.user.language;
      localStorage.setItem(STORAGE_LANG, state.lang);
    }
    applyLanguage();
  }

  async function boot() {
    applyLanguage();
    if (!localStorage.getItem(STORAGE_TOKEN)) return showAuth();
    try {
      hydrate(await api('/api/me'));
      showPortal();
    } catch (error) {
      if (error.message !== 'UNAUTHORIZED') showAuth();
    }
  }

  $('authForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    $('authError').classList.add('hidden');
    const code = $('authCode').value.trim();

    try {
      const data = await api('/api/auth', { method: 'POST', body: JSON.stringify({ code }) });
      localStorage.setItem(STORAGE_TOKEN, data.session_token);
      hydrate(data);
      $('authCode').value = '';
      showPortal();
    } catch (error) {
      $('authError').textContent = error.message === 'TOO_MANY_ATTEMPTS' ? t('auth.rate') : t('auth.invalid');
      $('authError').classList.remove('hidden');
    }
  });

  document.querySelectorAll('.language-strip button').forEach((button) => {
    button.addEventListener('click', () => {
      state.lang = button.dataset.lang;
      localStorage.setItem(STORAGE_LANG, state.lang);
      applyLanguage();
    });
  });

  $('profileMenuButton').addEventListener('click', () => {
    const menu = $('profileMenu');
    const hidden = menu.classList.toggle('hidden');
    $('profileMenuButton').setAttribute('aria-expanded', String(!hidden));
  });

  $('homeButton').addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

  $('logoutButton').addEventListener('click', async () => {
    try { await api('/api/logout', { method: 'POST' }); } catch (_) {}
    clearSession();
    $('profileMenu').classList.add('hidden');
    $('settingsOverlay').classList.add('hidden');
    showAuth();
  });

  document.querySelectorAll('[data-module]').forEach((card) => {
    card.addEventListener('click', () => {
      if (!profileIsComplete()) {
        openSettings(true);
        return;
      }
      const url = cfg.MODULES?.[card.dataset.module];
      if (url) window.location.href = url;
    });
  });

  function selectTab(tab) {
    if (tab === 'alliance' && !canAdminAlliance()) tab = 'profile';
    document.querySelectorAll('.tab').forEach((item) => item.classList.toggle('active', item.dataset.tab === tab));
    $('profileTab').classList.toggle('hidden', tab !== 'profile');
    $('allianceTab').classList.toggle('hidden', tab !== 'alliance');
    if (tab === 'alliance') loadMembers();
  }

  function openSettings(onboarding = false) {
    $('profileMenu').classList.add('hidden');
    selectTab('profile');
    $('settingsOverlay').classList.remove('hidden');
    $('settingsOverlay').dataset.onboarding = onboarding && !profileIsComplete() ? 'true' : 'false';
    renderIdentity();
    setTimeout(() => $('displayName')?.focus(), 20);
  }

  function closeSettings() {
    $('settingsOverlay').classList.add('hidden');
    delete $('settingsOverlay').dataset.onboarding;
  }

  document.querySelectorAll('.tab').forEach((item) => item.addEventListener('click', () => selectTab(item.dataset.tab)));
  $('openSettingsButton').addEventListener('click', () => openSettings(false));
  $('closeSettingsButton').addEventListener('click', closeSettings);
  $('settingsOverlay').addEventListener('click', (event) => { if (event.target === $('settingsOverlay')) closeSettings(); });

  function showMessage(element, text, isError = false) {
    element.textContent = text;
    element.classList.toggle('error', isError);
    element.classList.remove('hidden');
    setTimeout(() => element.classList.add('hidden'), 3500);
  }

  $('profileForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const data = await api('/api/profile', {
        method: 'PATCH',
        body: JSON.stringify({ display_name: $('displayName').value.trim(), language: $('languageSelect').value })
      });
      hydrate(data);
      showMessage($('profileMessage'), t('common.saved'));
    } catch (_) {
      showMessage($('profileMessage'), t('common.error'), true);
    }
  });

  $('avatarInput').addEventListener('change', async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      showMessage($('profileMessage'), t('common.error'), true);
      return;
    }

    const form = new FormData();
    form.append('avatar', file);
    try {
      hydrate(await api('/api/profile/avatar', { method: 'POST', body: form }));
      showMessage($('profileMessage'), t('common.saved'));
    } catch (_) {
      showMessage($('profileMessage'), t('common.error'), true);
    }
    event.target.value = '';
  });

  $('allianceForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const data = await api('/api/alliance', {
        method: 'PATCH',
        body: JSON.stringify({
          name: $('allianceName').value.trim(),
          server: $('allianceServer').value.trim(),
          logo_url: $('allianceLogo').value.trim() || null
        })
      });
      state.alliance = data.alliance;
      renderIdentity();
      showMessage($('allianceMessage'), t('common.saved'));
    } catch (_) {
      showMessage($('allianceMessage'), t('common.error'), true);
    }
  });

  async function loadMembers() {
    if (!canAdminAlliance()) return;
    try {
      const data = await api('/api/admin/members');
      state.members = data.members || [];
      renderMembers();
    } catch (_) {
      showMessage($('memberMessage'), t('common.error'), true);
    }
  }

  function renderMembers() {
    const list = $('memberList');
    list.innerHTML = '';

    for (const member of state.members) {
      const row = document.createElement('div');
      row.className = 'member-row';

      const main = document.createElement('div');
      main.className = 'member-main';
      const strong = document.createElement('strong');
      strong.textContent = member.display_name || member.player_name;
      const small = document.createElement('small');
      small.textContent = `${member.rank} · ${member.active ? t('common.active') : t('common.inactive')}`;
      main.append(strong, small);

      const rankSelect = document.createElement('select');
      rankSelect.setAttribute('aria-label', 'Rank');
      for (const rank of RANKS) {
        const option = document.createElement('option');
        option.value = rank;
        option.textContent = rank;
        option.selected = member.rank === rank;
        if (rank === 'R5' && state.membership?.rank !== 'R5') option.disabled = true;
        rankSelect.appendChild(option);
      }
      if (member.rank === 'R5' && state.membership?.rank !== 'R5') rankSelect.disabled = true;
      rankSelect.addEventListener('change', async () => {
        try {
          await api(`/api/admin/members/${encodeURIComponent(member.id)}`, {
            method: 'PATCH', body: JSON.stringify({ rank: rankSelect.value })
          });
        } catch (_) {}
        await loadMembers();
      });

      const actions = document.createElement('div');
      actions.className = 'member-actions';

      const codeButton = document.createElement('button');
      codeButton.type = 'button';
      codeButton.textContent = '🔑';
      codeButton.title = t('alliance.codeReset');
      codeButton.disabled = member.rank === 'R5' && state.membership?.rank !== 'R5';
      codeButton.addEventListener('click', async () => {
        const code = prompt(`${t('alliance.codeReset')} — ${t('alliance.codePlaceholder')}`);
        if (!code) return;
        try {
          await api(`/api/admin/members/${encodeURIComponent(member.id)}/code`, {
            method: 'POST', body: JSON.stringify({ code })
          });
          showMessage($('memberMessage'), t('common.saved'));
        } catch (_) {
          showMessage($('memberMessage'), t('common.error'), true);
        }
      });

      const activeButton = document.createElement('button');
      activeButton.type = 'button';
      activeButton.textContent = member.active ? '⏸' : '▶';
      activeButton.title = member.active ? t('alliance.disable') : t('alliance.enable');
      activeButton.disabled = member.id === state.user?.id || (member.rank === 'R5' && state.membership?.rank !== 'R5');
      activeButton.addEventListener('click', async () => {
        try {
          await api(`/api/admin/members/${encodeURIComponent(member.id)}`, {
            method: 'PATCH', body: JSON.stringify({ active: !member.active })
          });
          await loadMembers();
        } catch (_) {
          showMessage($('memberMessage'), t('common.error'), true);
        }
      });

      actions.append(codeButton, activeButton);
      row.append(main, rankSelect, actions);
      list.appendChild(row);
    }
  }

  $('refreshMembersButton').addEventListener('click', loadMembers);

  $('addMemberForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api('/api/admin/members', {
        method: 'POST',
        body: JSON.stringify({
          player_name: $('newMemberName').value.trim(),
          rank: $('newMemberRank').value,
          code: $('newMemberCode').value.trim()
        })
      });
      event.target.reset();
      $('newMemberRank').value = 'R3';
      await loadMembers();
      showMessage($('memberMessage'), t('common.saved'));
    } catch (_) {
      showMessage($('memberMessage'), t('common.error'), true);
    }
  });

  boot();
})();
