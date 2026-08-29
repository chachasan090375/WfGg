(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const MASTER = '/lab/master-assets-v1';
  const heroMap = window.WFGG_LASTWAR_HERO_AUTHORITATIVE_MAP || { heroes: [] };
  let currentData = null;
  let activeTeam = 1;

  const TEAM_PROFILE = {
    1: { key: 'tank', label: 'Blindés' },
    2: { key: 'aircraft', label: 'Aérien' },
    3: { key: 'missile', label: 'Missiles' }
  };

  const UNIT_POSITIONS = [
    { x: 50, y: 17 },
    { x: 18, y: 43 },
    { x: 47, y: 47 },
    { x: 78, y: 47 },
    { x: 49, y: 74 }
  ];

  const fmt = (n) => Number.isFinite(Number(n)) ? new Intl.NumberFormat('fr-FR').format(Number(n)) : '—';
  const fmtM = (n) => {
    const v = Number(n);
    if (!Number.isFinite(v)) return '—';
    return `${(v / 1_000_000).toFixed(2)}M`;
  };

  const mappedHero = (id) => heroMap.heroes.find((h) => Number(h.heroId) === Number(id)) || null;
  const heroRecord = (id) => (currentData?.heroes || []).find((h) => Number(h.heroId) === Number(id)) || null;
  const heroAsset = (id) => `${MASTER}/heroes/${Number(id)}.png`;
  const uiAsset = (name) => `${MASTER}/ui/${name}`;
  const companionAsset = (name) => `${MASTER}/companions/${name}`;

  function starCount(rankLv) {
    const rank = Math.max(0, Number(rankLv) || 0);
    if (!rank) return 0;
    return Math.max(0, Math.min(5, Math.floor((rank - 1) / 5)));
  }

  function teamForHero(id) {
    const formations = currentData?.armyFormations || [];
    for (let i = 0; i < formations.length; i += 1) {
      if ((formations[i].heroIds || []).some((x) => Number(x) === Number(id))) return i + 1;
    }
    return null;
  }

  function formationForTeam(teamNo) {
    return (currentData?.armyFormations || [])[teamNo - 1] || null;
  }

  function starsElement(rankLv, className = 'lw-stars') {
    const full = starCount(rankLv);
    const row = document.createElement('div');
    row.className = className;
    for (let i = 0; i < 5; i += 1) {
      const img = document.createElement('img');
      img.src = uiAsset('star-full.png');
      img.alt = '';
      img.className = i < full ? 'on' : 'off';
      row.appendChild(img);
    }
    return row;
  }

  function fallbackImage(img, label) {
    img.addEventListener('error', () => {
      const fb = document.createElement('span');
      fb.className = 'lw-image-fallback';
      fb.textContent = label || '?';
      img.replaceWith(fb);
    }, { once: true });
  }

  function rosterCard(hero) {
    const id = Number(hero.heroId);
    const mapped = mappedHero(id);
    const assignment = teamForHero(id);
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `lw-master-card${assignment === activeTeam ? ' selected' : ''}`;
    card.dataset.heroId = String(id);
    card.title = mapped?.name || `Héros ${id}`;

    const portrait = document.createElement('img');
    portrait.className = 'lw-card-image';
    portrait.src = heroAsset(id);
    portrait.alt = mapped?.name || `Héros ${id}`;
    fallbackImage(portrait, mapped?.name?.slice(0, 2).toUpperCase());
    card.appendChild(portrait);

    const type = document.createElement('img');
    type.className = 'lw-unit-type';
    const profile = TEAM_PROFILE[assignment || activeTeam] || TEAM_PROFILE[1];
    type.src = uiAsset(`type-${profile.key}.png`);
    type.alt = profile.label;
    card.appendChild(type);

    if (assignment) {
      const badge = document.createElement('span');
      badge.className = 'lw-squad-badge';
      badge.textContent = String(assignment);
      card.appendChild(badge);
    }

    const level = document.createElement('div');
    level.className = 'lw-level-line';
    const unitIcon = document.createElement('img');
    unitIcon.src = uiAsset(`type-${profile.key}.png`);
    unitIcon.alt = '';
    const strong = document.createElement('strong');
    strong.textContent = `Lv.${hero.level || '—'}`;
    level.append(unitIcon, strong);
    card.appendChild(level);

    card.appendChild(starsElement(hero.rankLv));

    if (assignment === activeTeam) {
      const check = document.createElement('img');
      check.className = 'lw-selected-check';
      check.src = uiAsset('selected-check.png');
      check.alt = 'Sélectionné';
      card.appendChild(check);
    }

    return card;
  }

  function formationUnit(heroId, index, teamNo) {
    const rec = heroRecord(heroId) || {};
    const mapped = mappedHero(heroId);
    const profile = TEAM_PROFILE[teamNo] || TEAM_PROFILE[1];
    const pos = UNIT_POSITIONS[index] || UNIT_POSITIONS[0];

    const unit = document.createElement('div');
    unit.className = 'lw-formation-member';
    unit.style.left = `${pos.x}%`;
    unit.style.top = `${pos.y}%`;

    const typeIcon = document.createElement('img');
    typeIcon.className = 'lw-formation-type';
    typeIcon.src = uiAsset(`type-${profile.key}.png`);
    typeIcon.alt = profile.label;
    unit.appendChild(typeIcon);

    const label = document.createElement('div');
    label.className = 'lw-unit-label';

    const portrait = document.createElement('img');
    portrait.className = 'lw-unit-thumb';
    portrait.src = heroAsset(heroId);
    portrait.alt = mapped?.name || `Héros ${heroId}`;
    fallbackImage(portrait, mapped?.name?.slice(0, 1));

    const info = document.createElement('div');
    info.className = 'lw-unit-info';
    const level = document.createElement('strong');
    level.textContent = `Niv.${rec.level || '—'}`;
    info.append(level, starsElement(rec.rankLv, 'lw-unit-stars'));

    label.append(portrait, info);
    unit.appendChild(label);
    return unit;
  }

  function renderFormation(teamNo) {
    const formation = formationForTeam(teamNo);
    const profile = TEAM_PROFILE[teamNo] || TEAM_PROFILE[1];

    const field = document.createElement('section');
    field.className = 'lw-formation-field';

    const board = document.createElement('img');
    board.className = 'lw-formation-board';
    board.src = uiAsset(`formation-${teamNo}.png`);
    board.alt = `Formation ${teamNo}`;
    field.appendChild(board);

    const power = document.createElement('div');
    power.className = 'lw-formation-power';
    power.innerHTML = `<span>◆</span><b>${fmtM(currentData?.drone?.totalSquadEquipPower)}</b>`;
    field.appendChild(power);

    const units = document.createElement('div');
    units.className = 'lw-formation-members';
    (formation?.heroIds || []).slice(0, 5).forEach((heroId, index) => {
      units.appendChild(formationUnit(heroId, index, teamNo));
    });
    field.appendChild(units);

    const drone = document.createElement('div');
    drone.className = 'lw-drone-wrap';
    const droneImage = document.createElement('img');
    droneImage.src = companionAsset('drone-162.png');
    droneImage.alt = 'Drone';
    drone.appendChild(droneImage);
    field.appendChild(drone);

    const controls = document.createElement('div');
    controls.className = 'lw-side-controls';
    const droneBtn = document.createElement('div');
    droneBtn.className = 'lw-round-control';
    droneBtn.innerHTML = `<span>✈</span><b>${fmt(currentData?.drone?.level)}</b>`;
    const presetBtn = document.createElement('div');
    presetBtn.className = 'lw-round-control secondary';
    presetBtn.innerHTML = `<span>▱</span><b>n°${formation?.chipEquipGroup || teamNo}</b>`;
    const plusBtn = document.createElement('div');
    plusBtn.className = 'lw-round-control secondary plus';
    plusBtn.textContent = '+';
    controls.append(droneBtn, presetBtn, plusBtn);
    field.appendChild(controls);

    const switcher = document.createElement('div');
    switcher.className = 'lw-team-switcher';
    const title = document.createElement('strong');
    title.textContent = 'Équipe';
    switcher.appendChild(title);
    for (let n = 1; n <= 3; n += 1) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `lw-team-button${n === activeTeam ? ' active' : ''}`;
      button.textContent = String(n);
      button.dataset.team = String(n);
      button.setAttribute('aria-label', `Afficher équipe ${n}`);
      switcher.appendChild(button);
    }
    const lock = document.createElement('span');
    lock.className = 'lw-team-lock';
    lock.textContent = '🔒';
    switcher.appendChild(lock);
    field.appendChild(switcher);

    const teamLabel = document.createElement('div');
    teamLabel.className = 'lw-team-label';
    teamLabel.textContent = profile.label;
    field.appendChild(teamLabel);

    return field;
  }

  function renderRoster() {
    const panel = document.createElement('section');
    panel.className = 'lw-roster-panel';
    const grid = document.createElement('div');
    grid.className = 'lw-roster-grid';

    const heroes = [...(currentData?.heroes || [])].sort((a, b) => {
      const ta = teamForHero(a.heroId) || 9;
      const tb = teamForHero(b.heroId) || 9;
      if (ta !== tb) return ta - tb;
      return Number(b.heroId) - Number(a.heroId);
    });
    heroes.forEach((hero) => grid.appendChild(rosterCard(hero)));
    panel.appendChild(grid);

    const filters = document.createElement('div');
    filters.className = 'lw-roster-filters';
    const all = document.createElement('button');
    all.type = 'button';
    all.className = 'active';
    all.textContent = 'ALL';
    filters.appendChild(all);
    ['tank', 'missile', 'aircraft'].forEach((key) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.disabled = true;
      const img = document.createElement('img');
      img.src = uiAsset(`type-${key}.png`);
      img.alt = key;
      button.appendChild(img);
      filters.appendChild(button);
    });
    panel.appendChild(filters);
    return panel;
  }

  function renderScreen() {
    const host = $('squadGrid');
    if (!host || !currentData) return;
    host.innerHTML = '';
    const screen = document.createElement('div');
    screen.className = 'lw-authentic-screen';
    screen.append(renderFormation(activeTeam), renderRoster());
    host.appendChild(screen);

    host.querySelectorAll('.lw-team-button').forEach((button) => {
      button.addEventListener('click', () => {
        activeTeam = Number(button.dataset.team) || 1;
        renderScreen();
      });
    });
  }

  function validate(data) {
    if (!data || data.format !== 'WFGG_LASTWAR_MODULE_DATA_V3') throw new Error('Le fichier doit être le JSON Phase 19 / V3.');
    if (!data.privacy || data.privacy.networkUsed !== false) throw new Error('Contrat de confidentialité invalide.');
    if ((data.armyFormations || []).length < 3) throw new Error('Trois escouades actives sont nécessaires.');
    return data;
  }

  function updateStatus() {
    const formations = currentData?.armyFormations || [];
    const ids = formations.flatMap((f) => f.heroIds || []);
    const mapped = ids.filter((id) => mappedHero(id)).length;
    if ($('replicaStatus')) $('replicaStatus').textContent = `${formations.length} équipes · ${mapped}/${ids.length} héros résolus · sélecteur 1/2/3 actif`;
    if ($('assetStatus')) {
      $('assetStatus').textContent = 'Master assets V1 · 31 portraits · UI Formation authentique';
      $('assetStatus').className = 'asset-status ok';
    }
    if ($('squadEquipPower')) $('squadEquipPower').textContent = fmt(currentData?.drone?.totalSquadEquipPower);
  }

  const input = $('squadDataFile');
  if (input) {
    input.addEventListener('change', async (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        currentData = validate(JSON.parse(await file.text()));
        activeTeam = 1;
        updateStatus();
        renderScreen();
      } catch (error) {
        if ($('replicaStatus')) $('replicaStatus').textContent = `Erreur : ${error.message || error}`;
      }
    });
  }
})();
