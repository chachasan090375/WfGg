import fs from 'node:fs';
import assert from 'node:assert/strict';

const src=fs.readFileSync('frontend/_worker.js','utf8');
const checks=[
  ['runtime marker','WFGG_TRAIN_REMINDER_STATS_RUNTIME_V1'],
  ['analytics fallback marker','x-wfgg-analytics-fallback'],
  ['authoritative schedule cache','wfgg_train_v13'],
  ['roster cache','wfgg_train_roster_cache'],
  ['analytics route','/api/admin/analytics'],
  ['analytics timeout','4500'],
  ['calendar link route','/api/me/calendar-link'],
  ['calendar feed opener','__WFGG_OPEN_TRAIN_CALENDAR_FEED__'],
  ['webcal subscription',"replace(/^https:/i,'webcal:')"],
  ['J-1 wording','J-1'],
  ['30 minute wording','30 minutes avant'],
  ['alert observer','wfggTrainAlertObserver']
];
for(const [name,needle] of checks){assert.ok(src.includes(needle),`missing ${name}: ${needle}`);console.log('PASS',name)}
console.log(`TOTAL=${checks.length} PASS=${checks.length} FAIL=0`);
