(() => {
  'use strict';

  const V2 = '/lab/master-assets-v2';
  const V1 = '/lab/master-assets-v1';

  function heroIdFromMember(member) {
    const img = member.querySelector('.lw-unit-thumb');
    const m = String(img?.getAttribute('src') || '').match(/\/heroes\/(\d+)\.png/);
    return m ? Number(m[1]) : null;
  }

  function teamKeyFromCard(card) {
    const badge = Number(card.querySelector('.lw-squad-badge')?.textContent || 0);
    return badge === 2 ? 'aircraft' : badge === 3 ? 'missile' : 'tank';
  }

  function exactImg(src, cls, alt = '') {
    const img = document.createElement('img');
    img.className = cls;
    img.src = src;
    img.alt = alt;
    return img;
  }

  function hydrateFormationMember(member) {
    if (member.dataset.pixelHydrated === '1') return;
    member.dataset.pixelHydrated = '1';

    // Never show the temporary CSS/unit silhouette in pixel-master mode.
    member.querySelector('.lw-formation-type')?.remove();

    const heroId = heroIdFromMember(member);
    if (!heroId) return;
    member.dataset.heroId = String(heroId);

    const mount = document.createElement('div');
    mount.className = 'lw-vehicle-mount';
    mount.dataset.heroId = String(heroId);

    // Phase 36 will populate authentic Unity-rendered idle frames here.
    // Missing frame = blank mount, never a fabricated substitute.
    const frame = exactImg(`${V2}/vehicles/${heroId}/idle-000.webp`, 'lw-vehicle-frame', '');
    frame.addEventListener('error', () => frame.remove(), { once: true });
    mount.appendChild(frame);
    member.insertBefore(mount, member.firstChild);
  }

  function hydrateRosterCard(card) {
    if (card.dataset.pixelHydrated === '1') return;
    card.dataset.pixelHydrated = '1';

    // Native card top-left is the hero role badge, not troop family.
    // Hide the incorrect old icon until the authoritative role map is attached.
    card.querySelector(':scope > .lw-unit-type')?.remove();

    // Troop-family icon beside level is authentic; use recovered exact sprite.
    const teamKey = teamKeyFromCard(card);
    const levelIcon = card.querySelector('.lw-level-line img');
    if (levelIcon) {
      levelIcon.src = `${V2}/ui/type-${teamKey}-small.png`;
      levelIcon.addEventListener('error', () => {
        levelIcon.src = `${V1}/ui/type-${teamKey}.png`;
      }, { once: true });
    }
  }

  function hydrateControls(screen) {
    const controls = screen.querySelectorAll('.lw-side-controls .lw-round-control');
    if (controls[0] && controls[0].dataset.pixelHydrated !== '1') {
      controls[0].dataset.pixelHydrated = '1';
      controls[0].replaceChildren(exactImg(`${V2}/ui/squad-control-1.png`, 'lw-native-control-icon', ''));
    }
    if (controls[1] && controls[1].dataset.pixelHydrated !== '1') {
      controls[1].dataset.pixelHydrated = '1';
      controls[1].replaceChildren(exactImg(`${V2}/ui/drone-chip-icon.png`, 'lw-native-control-icon', ''));
    }
    if (controls[2] && controls[2].dataset.pixelHydrated !== '1') {
      controls[2].dataset.pixelHydrated = '1';
      controls[2].classList.add('plus');
      controls[2].style.setProperty('display', 'grid', 'important');
      controls[2].replaceChildren(exactImg(`${V2}/ui/add.png`, 'lw-native-control-icon', ''));
    }

    const lock = screen.querySelector('.lw-team-lock');
    if (lock && lock.dataset.pixelHydrated !== '1') {
      lock.dataset.pixelHydrated = '1';
      lock.replaceChildren(exactImg(`${V2}/ui/lock.png`, 'lw-native-lock-icon', ''));
    }
  }

  function hydrate(screen) {
    document.body.classList.add('lw-native-loaded');
    screen.querySelectorAll('.lw-formation-member').forEach(hydrateFormationMember);
    screen.querySelectorAll('.lw-master-card').forEach(hydrateRosterCard);
    hydrateControls(screen);
  }

  function scan() {
    document.querySelectorAll('.lw-authentic-screen').forEach(hydrate);
  }

  const observer = new MutationObserver(scan);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  scan();
})();
