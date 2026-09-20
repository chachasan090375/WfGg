#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')
text = UI.read_text(encoding='utf-8')
MARKER = 'WFGG_RADAR_COLLECTOR_CYCLE_TERMINALIZATION_UI_V6198'

if MARKER in text:
    print('RADAR_V6198_UI=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '<!-- WFGG_RADAR_AUTOPILOT_STALE_CYCLE_RECOVERY_UI_V6197 -->'
if text.count(anchor) != 1:
    raise SystemExit(f'V6198_UI_MARKER_ANCHOR_COUNT={text.count(anchor)}')
text = text.replace(anchor, anchor + '\n  <!-- ' + MARKER + ' -->', 1)

old_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.7 · ARRÊTÉ</span>'
new_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.8 · ARRÊTÉ</span>'
if text.count(old_title) != 1:
    raise SystemExit(f'V6198_UI_TITLE_ANCHOR_COUNT={text.count(old_title)}')
text = text.replace(old_title, new_title, 1)

old_note = 'READ-ONLY côté Last War · cycles complets conservés · seeds sans données ignorées après 3 essais · cycles Collector stale récupérés · erreurs globales bloquantes.'
new_note = 'READ-ONLY côté Last War · cycles Collector toujours terminalisés après erreur · récupération stale conservée · erreurs globales bloquantes.'
if text.count(old_note) != 1:
    raise SystemExit(f'V6198_UI_NOTE_ANCHOR_COUNT={text.count(old_note)}')
text = text.replace(old_note, new_note, 1)

UI.write_text(text, encoding='utf-8')
print('RADAR_V6198_UI=PATCHED')
