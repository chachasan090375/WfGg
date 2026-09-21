#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')
text = UI.read_text(encoding='utf-8')
MARKER = 'WFGG_RADAR_AUTOPILOT_NO_RESCAN_QUALIFIED_UI_V61912'

if MARKER in text:
    print('RADAR_V61912_UI=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '<!-- WFGG_RADAR_AUTOPILOT_CONTINUE_PARTIAL_LIMIT_UI_V61910 -->'
if text.count(anchor) != 1:
    raise SystemExit(f'V61912_UI_MARKER_ANCHOR_COUNT={text.count(anchor)}')
text = text.replace(anchor, anchor + '\n  <!-- ' + MARKER + ' -->', 1)

old_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.10 · ARRÊTÉ</span>'
new_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.12 · ARRÊTÉ</span>'
if text.count(old_title) != 1:
    raise SystemExit(f'V61912_UI_TITLE_ANCHOR_COUNT={text.count(old_title)}')
text = text.replace(old_title, new_title, 1)

meta_anchor = '  meta.textContent=progress;'
if text.count(meta_anchor) != 1:
    raise SystemExit(f'V61912_UI_META_ANCHOR_COUNT={text.count(meta_anchor)}')
text = text.replace(
    meta_anchor,
    "  if(Array.isArray(job.qualifiedSeedsSkipped)&&job.qualifiedSeedsSkipped.length)progress+=\` · déjà qualifiées ignorées \${job.qualifiedSeedsSkipped.length}\`;\n  meta.textContent=progress;",
    1,
)

note_anchor = "  if(job.lastCycle?.classification==='PARTIAL')note.textContent="
if text.count(note_anchor) != 1:
    raise SystemExit(f'V61912_UI_NOTE_ANCHOR_COUNT={text.count(note_anchor)}')
text = text.replace(
    note_anchor,
    "  if(phase==='SCOUT_SKIPPED_QUALIFIED')note.textContent='Seed déjà qualifiée sur 3 cycles 9/9 : aucun probe Seed Scout, passage automatique à la suivante.';\n  else if(job.lastCycle?.classification==='PARTIAL')note.textContent=",
    1,
)

old_note2 = 'READ-ONLY côté Last War · no-data et partiels persistants ignorent seulement la seed · preuves 9/9 conservées · erreurs globales bloquantes.'
new_note2 = 'READ-ONLY côté Last War · seeds déjà qualifiées jamais rescannées · no-data/partiels ignorent seulement la seed · preuves 9/9 conservées.'
if text.count(old_note2) != 1:
    raise SystemExit(f'V61912_UI_INFO_ANCHOR_COUNT={text.count(old_note2)}')
text = text.replace(old_note2, new_note2, 1)

UI.write_text(text, encoding='utf-8')
print('RADAR_V61912_UI=PATCHED')
