#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')
text = UI.read_text(encoding='utf-8')
MARKER = 'WFGG_RADAR_AUTOPILOT_PERSISTENT_LEDGER_UI_V61913'

if MARKER in text:
    print('RADAR_V61913_UI=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '<!-- WFGG_RADAR_AUTOPILOT_NO_RESCAN_QUALIFIED_UI_V61912 -->'
if text.count(anchor) != 1:
    raise SystemExit(f'V61913_UI_MARKER_ANCHOR_COUNT={text.count(anchor)}')
text = text.replace(anchor, anchor + '\n  <!-- ' + MARKER + ' -->', 1)

old_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.12 · ARRÊTÉ</span>'
new_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.13 · ARRÊTÉ</span>'
if text.count(old_title) != 1:
    raise SystemExit(f'V61913_UI_TITLE_ANCHOR_COUNT={text.count(old_title)}')
text = text.replace(old_title, new_title, 1)

meta_anchor = "  if(Array.isArray(job.qualifiedSeedsSkipped)&&job.qualifiedSeedsSkipped.length)progress+=` · déjà qualifiées ignorées ${job.qualifiedSeedsSkipped.length}`;"
if text.count(meta_anchor) != 1:
    raise SystemExit(f'V61913_UI_META_ANCHOR_COUNT={text.count(meta_anchor)}')
text = text.replace(
    meta_anchor,
    meta_anchor + "\n  if(Array.isArray(job.persistentSeedsSkipped)&&job.persistentSeedsSkipped.length)progress+=` · ledger ignorées ${job.persistentSeedsSkipped.length}`;"
    + "\n  if(job.persistentLedgerWrites)progress+=` · écritures ledger ${job.persistentLedgerWrites}`;",
    1,
)

note_anchor = "  if(phase==='SCOUT_SKIPPED_QUALIFIED')note.textContent='Seed déjà qualifiée sur 3 cycles 9/9 : aucun probe Seed Scout, passage automatique à la suivante.';"
if text.count(note_anchor) != 1:
    raise SystemExit(f'V61913_UI_NOTE_ANCHOR_COUNT={text.count(note_anchor)}')
text = text.replace(
    note_anchor,
    "  if(phase==='LEDGER_RESUME_SKIPPED_TERMINAL')note.textContent='Reprise persistante : seed déjà terminale dans le ledger Collector, passage automatique à la suivante.';\n"
    "  else if(phase==='SCOUT_SKIPPED_PERSISTED')note.textContent='Ledger persistant : seed déjà traitée (qualifiée, no-data ou limite partielle), aucun nouveau probe.';\n"
    + note_anchor.replace("  if(", "  else if("),
    1,
)

old_info = 'READ-ONLY côté Last War · seeds déjà qualifiées jamais rescannées · no-data/partiels ignorent seulement la seed · preuves 9/9 conservées.'
new_info = 'READ-ONLY côté Last War · ledger Collector persistant · reprise après redémarrage avec token frais · seeds qualifiées/no-data/partielles non rescannées.'
if text.count(old_info) != 1:
    raise SystemExit(f'V61913_UI_INFO_ANCHOR_COUNT={text.count(old_info)}')
text = text.replace(old_info, new_info, 1)

UI.write_text(text, encoding='utf-8')
print('RADAR_V61913_UI=PATCHED')
