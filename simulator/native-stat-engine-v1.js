(() => {
  'use strict';

  const DATA_URL = 'data/native-hero-stats-v2.json';
  let dataset = null;
  let loadError = null;

  const readyPromise = fetch(DATA_URL, { cache: 'no-store' })
    .then(r => {
      if (!r.ok) throw new Error(`native stat dataset HTTP ${r.status}`);
      return r.json();
    })
    .then(d => {
      if (d?.coverage?.heroCount !== 31) throw new Error('native stat dataset hero coverage is not 31');
      if ((d?.coverage?.unsupportedHeroIds || []).length) throw new Error('native stat dataset contains unsupported heroes');
      if ((d?.coverage?.fallbacks || []).length) throw new Error('native stat dataset contains fallbacks');
      if (d?.formula?.maxHeroLevelAtHQ35 !== 175) throw new Error('native stat dataset hero level cap is not 175');
      if (d?.validation?.williams150Rank26?.exactMatch !== true) throw new Error('Williams native anchor is not validated');
      dataset = d;
      return d;
    })
    .catch(err => {
      loadError = err;
      console.error('WfGg native stat engine', err);
      throw err;
    });

  const intInRange = (value, min, max, label) => {
    const n = Number(value);
    if (!Number.isInteger(n) || n < min || n > max) {
      throw new RangeError(`${label} must be an integer from ${min} to ${max}`);
    }
    return n;
  };

  function rankFromStars(stars) {
    const n = Number(stars);
    if (!Number.isFinite(n) || n < 0 || n > 5) {
      throw new RangeError('stars must be from 0 to 5');
    }
    const tiers = n * 5;
    const rounded = Math.round(tiers);
    if (Math.abs(tiers - rounded) > 1e-8) {
      throw new RangeError('stars must align to one of the five tiers per star (increments of 0.2)');
    }
    return rounded + 1;
  }

  function starsFromRank(rank) {
    const rk = intInRange(rank, 1, 26, 'rank');
    return (rk - 1) / 5;
  }

  function calculateSync({ nativeId, level, rank, stars }) {
    if (!dataset) {
      if (loadError) throw loadError;
      throw new Error('native stat dataset is not loaded yet');
    }

    const id = intInRange(nativeId, 1, Number.MAX_SAFE_INTEGER, 'nativeId');
    const lv = intInRange(level, 1, 175, 'level');
    if (rank != null && stars != null) throw new Error('provide rank or stars, not both');
    const rk = rank != null ? intInRange(rank, 1, 26, 'rank') : rankFromStars(stars ?? 0);
    const hero = dataset.heroes?.[String(id)];
    if (!hero) throw new Error(`unsupported native hero id ${id}`);

    const curve = dataset.templateCurves?.[String(hero.templateId)]?.[String(lv)];
    const rankRow = dataset.ranks?.[String(rk)];
    if (!curve) throw new Error(`missing template ${hero.templateId} level ${lv}`);
    if (!rankRow) throw new Error(`missing rank ${rk}`);

    const stats = {};
    for (const stat of ['hp', 'attack', 'defense']) {
      const factor = Number(hero.base?.[stat]) / 10000;
      if (!Number.isFinite(factor)) throw new Error(`invalid ${stat} base for hero ${id}`);
      const levelBase = Math.floor(Number(curve[stat]) * factor);
      const gradeBonus = Math.floor(Number(rankRow[stat]) * factor);
      stats[stat] = Object.freeze({
        levelBase,
        gradeBonus,
        nativeLevelPlusGrade: levelBase + gradeBonus
      });
    }

    return Object.freeze({
      layer: 'native_level_plus_grade',
      finalDisplayedAttributes: false,
      nativeId: id,
      level: lv,
      rank: rk,
      stars: starsFromRank(rk),
      templateId: hero.templateId,
      quality: hero.quality,
      stats: Object.freeze(stats),
      source: Object.freeze({
        client: dataset.source?.client,
        buildId: dataset.source?.buildId,
        dataTableMd5: dataset.source?.dataTableMd5
      }),
      warning: 'Native level + grade only. Skills, exclusive weapon, awakening/promotion, gear, Wall of Honor and account/research layers are not included.'
    });
  }

  async function calculate(input) {
    await readyPromise;
    return calculateSync(input);
  }

  async function selfTest() {
    await readyPromise;
    const byRank = calculateSync({ nativeId: 50007, level: 150, rank: 26 });
    const byStars = calculateSync({ nativeId: 50007, level: 150, stars: 5 });
    const grade = {
      hp: byRank.stats.hp.gradeBonus,
      attack: byRank.stats.attack.gradeBonus,
      defense: byRank.stats.defense.gradeBonus
    };
    const expected = { hp: 201433, attack: 2837, defense: 741 };
    const ok = Object.keys(expected).every(k => grade[k] === expected[k]) && byStars.rank === 26;
    if (!ok) throw new Error(`Williams self-test failed: ${JSON.stringify(grade)}`);
    const tierChecks = [0, 0.2, 1, 2, 3, 4, 5].map(s => ({ stars: s, rank: rankFromStars(s) }));
    return Object.freeze({ ok: true, grade, expected, tierChecks, maxHeroLevelAtHQ35: 175, heroCount: dataset.coverage.heroCount });
  }

  window.WfGgNativeStats = Object.freeze({
    version: '1.1.0',
    ready: () => readyPromise,
    calculate,
    calculateSync,
    rankFromStars,
    starsFromRank,
    selfTest,
    metadata: () => dataset ? Object.freeze({
      heroCount: dataset.coverage.heroCount,
      templateIds: [...dataset.coverage.templateIds],
      levelRange: [...dataset.formula.heroLevelRange],
      rankRange: [...dataset.formula.rankRange],
      starTierStep: 0.2,
      maxHeroLevelAtHQ35: dataset.formula.maxHeroLevelAtHQ35,
      dataTableMd5: dataset.source.dataTableMd5
    }) : null
  });
})();
