#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')
text = UI.read_text(encoding='utf-8')
MARKER = 'WFGG_RADAR_AUTOPILOT_CONTINUE_PARTIAL_LIMIT_UI_V61910'

if MARKER in text:
    print('RADAR_V61910_UI=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '<!-- WFGG_RADAR_AUTOPILOT_TARGETED_HISTORY_QUALITY_UI_V6199 -->'
if text.count(anchor) != 1:
    raise SystemExit(f'V61910_UI_MARKER_ANCHOR_COUNT={text.count(anchor)}')
text = text.replace(anchor, anchor + '\n  <!-- ' + MARKER + ' -->', 1)

old_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.9 · ARRÊTÉ</span>'
new_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.10 · ARRÊTÉ</span>'
if text.count(old_title) != 1:
    raise SystemExit(f'V61910_UI_TITLE_ANCHOR_COUNT={text.count(old_title)}')
text = text.replace(old_title, new_title, 1)

skip_anchor = "else if(phase==='SEED_SKIPPED_NO_DATA'"
if text.count(skip_anchor) != 1:
    raise SystemExit(f'V61910_UI_SKIP_BRANCH_ANCHOR_COUNT={text.count(skip_anchor)}')

scouting_no_data = "phase==='SEED_SKIPPED_NO_DATA'||(phase==='SCOUTING'&&job.lastSkippedSeed)"
if text.count(scouting_no_data) != 1:
    raise SystemExit(f'V61910_UI_SCOUTING_CONDITION_ANCHOR_COUNT={text.count(scouting_no_data)}')
text = text.replace(
    scouting_no_data,
    "phase==='SEED_SKIPPED_NO_DATA'||(phase==='SCOUTING'&&job.lastSkippedSeed&&!String(job.lastSkippedSeed.reason||'').includes('PARTIAL'))",
    1,
)

partial_branch = "else if(phase==='SEED_SKIPPED_PARTIAL'||(phase==='SCOUTING'&&job.lastSkippedSeed&&String(job.lastSkippedSeed.reason||'').includes('PARTIAL'))){const s=job.lastSkippedSeed||{};note.textContent=`Seed ${s.seed||'—'} : trop de cycles partiels après retries · ${s.validatedCycles||0}/${job.requiredFullCycles||3} preuve(s) 9/9 conservée(s) · seed non confirmée · passage automatique à la suivante.`;}\n  "
text = text.replace(skip_anchor, partial_branch + skip_anchor, 1)

old_note2 = 'READ-ONLY côté Last War · historique ciblé par seed · terminalisation Collector et récupération stale conservées · erreurs globales bloquantes.'
new_note2 = 'READ-ONLY côté Last War · no-data et partiels persistants ignorent seulement la seed · preuves 9/9 conservées · erreurs globales bloquantes.'
if text.count(old_note2) != 1:
    raise SystemExit(f'V61910_UI_INFO_ANCHOR_COUNT={text.count(old_note2)}')
text = text.replace(old_note2, new_note2, 1)

UI.write_text(text, encoding='utf-8')
print('RADAR_V61910_UI=PATCHED')
