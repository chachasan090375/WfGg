from pathlib import Path

p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
marker='    /* WFGG_TRAIN_EXCHANGE_OWN_CANCEL_V1'
if 'WFGG_TRAIN_SCHEDULE_PARITY_V1' in s:
    print('WFGG_TRAIN_SCHEDULE_PARITY_V1 already present')
    raise SystemExit(0)
if marker not in s:
    raise SystemExit('exchange insertion marker missing')

block=r'''    /* WFGG_TRAIN_SCHEDULE_PARITY_V1
       Le frontend historique calculait encore l'ancien planning, tandis que
       le Worker applique désormais le cycle d'équité R3. La bourse validait
       donc les places contre deux calendriers différents. On remplace ici le
       moteur frontend par le même modèle que generateSchedule() côté Worker :
       cycle défini par les R3, 1 Conducteur R3 + 1 VIP par R3/cycle,
       Conducteur A indépendant, historique manuel et mêmes exclusions.
    */
    {
      const schedulePattern = /    function generateSchedule\(days = 260\) \{[\s\S]*?\n    \}\n    function schedule\(\) \{ return generateSchedule\(\); \}/;
      const scheduleReplacement = String.raw`    function wfggHistorySeed(pool, role) {
        const mh = state.manualHistory || {};
        const counts = (mh.counts && mh.counts[role]) || {};
        const links = mh.links || {};
        const out = {};
        for (const m of pool) {
            const key = links[m.id];
            const h = key ? counts[key] : null;
            out[m.id] = {
                count: Number((h && h.count) || 0),
                last: String((h && h.last) || '0000-00-00')
            };
        }
        return out;
    }
    function generateSchedule(days = 420) {
        const anchor = parseISO(state.settings.anchorDate || '2026-08-10');
        ensureRotationRankSettings();
        const officers = orderedPool(activePool(ranksForRotation('officer')), 'officer');
        const r3Drivers = orderedPool(activePool(['R3']), 'r3driver');
        const vipPool = orderedPool(activePool(ranksForRotation('vip')), 'r3vip');
        const nonR3VipPool = vipPool.filter(m => m.rank !== 'R3');
        const localById = Object.fromEntries(ROSTER.map(m => [String(m.id), m]));
        const officerHistory = wfggHistorySeed(officers, 'driver');
        const r3DriverHistory = wfggHistorySeed(r3Drivers, 'driver');
        const vipHistory = wfggHistorySeed(vipPool, 'vip');
        const r3Parity = (state.settings.officersFirst ?? true) ? 1 : 0;
        const r3Count = r3Drivers.length;
        let activeR3Cycle = -1;
        let cycleDrivers = new Set();
        let cycleVips = new Set();
        const cycleForOffset = (offset) => {
            if (!r3Count) return 0;
            const slot = offset < r3Parity ? 0 : Math.floor((offset - r3Parity) / 2);
            return Math.floor(slot / r3Count);
        };
        const out = [];
        for (let i = 0; i < days; i++) {
            const d = addDays(anchor, i), ds = dateISO(d);
            const r3Cycle = cycleForOffset(i);
            if (r3Cycle !== activeR3Cycle) {
                activeR3Cycle = r3Cycle;
                cycleDrivers = new Set();
                cycleVips = new Set();
            }
            const officerDay = (state.settings.officersFirst ?? true) ? i % 2 === 0 : i % 2 === 1;
            let driver;
            if (officerDay) {
                driver = pickFair(officers, ds, officerHistory, []);
            } else {
                const missingDrivers = r3Drivers.filter(m => !cycleDrivers.has(String(m.id)));
                driver = pickFair(missingDrivers.length ? missingDrivers : r3Drivers, ds, r3DriverHistory, []);
            }
            const exclude = driver ? [driver.id] : [];
            const missingVips = r3Drivers.filter(m => !cycleVips.has(String(m.id)));
            let vip = null;
            if (missingVips.length) {
                vip = pickFair(missingVips, ds, vipHistory, exclude);
                if (!vip && nonR3VipPool.length) vip = pickFair(nonR3VipPool, ds, vipHistory, exclude);
            } else if (nonR3VipPool.length) {
                vip = pickFair(nonR3VipPool, ds, vipHistory, exclude);
            }
            if (!vip) vip = pickFair(vipPool, ds, vipHistory, exclude);
            let item = {
                date: ds,
                driverId: (driver && driver.id) || null,
                vipId: (vip && vip.id) || null,
                driverClass: officerDay ? 'officer' : 'r3',
                r3Cycle
            };
            if (state.overrides[ds]) item = Object.assign(Object.assign({}, item), state.overrides[ds]);
            const actualDriver = localById[String(item.driverId || '')];
            const actualVip = localById[String(item.vipId || '')];
            if (officerDay) touchHistory(officerHistory, actualDriver, ds);
            else touchHistory(r3DriverHistory, actualDriver, ds);
            touchHistory(vipHistory, actualVip, ds);
            if (!officerDay && actualDriver && actualDriver.rank === 'R3') cycleDrivers.add(String(actualDriver.id));
            if (actualVip && actualVip.rank === 'R3') cycleVips.add(String(actualVip.id));
            out.push(item);
        }
        return out;
    }
    function schedule() { return generateSchedule(); }`;
      if (!schedulePattern.test(rewritten)) {
        throw new Error('WFGG_TRAIN_SCHEDULE_PARITY_SOURCE_MISMATCH');
      }
      rewritten = rewritten.replace(schedulePattern, () => scheduleReplacement);
    }

'''
s=s.replace(marker, block+marker, 1)
p.write_text(s,encoding='utf-8')
print('WFGG_TRAIN_SCHEDULE_PARITY_V1=PATCHED')
