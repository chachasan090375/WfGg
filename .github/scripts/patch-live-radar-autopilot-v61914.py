#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')
text = UI.read_text(encoding='utf-8')
MARKER = 'WFGG_RADAR_AUTOPILOT_COVERAGE_COMPLETION_UI_V61914'

if MARKER in text:
    print('RADAR_V61914_UI=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '<!-- WFGG_RADAR_AUTOPILOT_PERSISTENT_LEDGER_UI_V61913 -->'
if text.count(anchor) != 1:
    raise SystemExit(f'V61914_UI_MARKER_ANCHOR_COUNT={text.count(anchor)}')
text = text.replace(anchor, anchor + '\n  <!-- ' + MARKER + ' -->', 1)

old_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.13 · ARRÊTÉ</span>'
new_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.14 · ARRÊTÉ</span>'
if text.count(old_title) != 1:
    raise SystemExit(f'V61914_UI_TITLE_ANCHOR_COUNT={text.count(old_title)}')
text = text.replace(old_title, new_title, 1)

old_progress = "  let progress=`Grappe ${Number(job.confirmedClusters||0)+1}/${job.maxClusters||5} · seed ${seed} · cycles 9/9 ${job.validatedCycles||0}/${job.requiredFullCycles||3} · partiels ${job.partialCycles||0}`;"
if text.count(old_progress) != 1:
    raise SystemExit(f'V61914_UI_PROGRESS_ANCHOR_COUNT={text.count(old_progress)}')
new_progress = "  let progress=job.coverageMode?\`Couverture · grappes confirmées \${Number(job.confirmedClusters||0)} · seed \${seed} · cycles 9/9 \${job.validatedCycles||0}/\${job.requiredFullCycles||3} · partiels \${job.partialCycles||0}\`:\`Grappe \${Number(job.confirmedClusters||0)+1}/\${job.maxClusters||5} · seed \${seed} · cycles 9/9 \${job.validatedCycles||0}/\${job.requiredFullCycles||3} · partiels \${job.partialCycles||0}\`;"
text = text.replace(old_progress, new_progress, 1)

meta_anchor = "  if(job.persistentLedgerWrites)progress+=` · écritures ledger ${job.persistentLedgerWrites}`;"
if text.count(meta_anchor) != 1:
    raise SystemExit(f'V61914_UI_META_ANCHOR_COUNT={text.count(meta_anchor)}')
text = text.replace(
    meta_anchor,
    meta_anchor
    + "\n  if(job.coverageMode)progress+=\` · fenêtres \${job.coverageWindows||0} · probes \${job.coverageCandidatesScouted||0}\`;"
    + "\n  if(job.coverageComplete)progress+=' · COUVERTURE TERMINÉE';",
    1,
)

note_anchor = "  if(phase==='LEDGER_RESUME_SKIPPED_TERMINAL')note.textContent='Reprise persistante : seed déjà terminale dans le ledger Collector, passage automatique à la suivante.';"
if text.count(note_anchor) != 1:
    raise SystemExit(f'V61914_UI_NOTE_ANCHOR_COUNT={text.count(note_anchor)}')
text = text.replace(
    note_anchor,
    "  if(phase==='COVERAGE_COMPLETE')note.textContent='COUVERTURE TERMINÉE · aucune nouvelle seed exploitable dans la frontière Seed Scout.';\n"
    "  else if(phase==='COVERAGE_FRONTIER_CONTINUE')note.textContent='Fenêtre Seed Scout parcourue sans nouvelle grappe · poursuite automatique sur la fenêtre suivante.';\n"
    + note_anchor.replace("  if(", "  else if("),
    1,
)

old_info = 'READ-ONLY côté Last War · ledger Collector persistant · reprise après redémarrage avec token frais · seeds qualifiées/no-data/partielles non rescannées.'
new_info = 'READ-ONLY côté Last War · mode couverture continue jusqu’à épuisement réel de la frontière Seed Scout · ledger persistant · aucun token conservé.'
if text.count(old_info) != 1:
    raise SystemExit(f'V61914_UI_INFO_ANCHOR_COUNT={text.count(old_info)}')
text = text.replace(old_info, new_info, 1)

old_payload = "body:JSON.stringify({initialSeed,fullCyclesPerCluster:3,maxClusters:5})"
new_payload = "body:JSON.stringify({initialSeed,fullCyclesPerCluster:3,coverageMode:true})"
if text.count(old_payload) != 1:
    raise SystemExit(f'V61914_UI_START_PAYLOAD_ANCHOR_COUNT={text.count(old_payload)}')
text = text.replace(old_payload, new_payload, 1)

old_status = "setStatus('AUTOPILOT DÉMARRÉ',initialSeed?`Seed ${initialSeed} · preuve fraîche 3×9/9`:'Seed Scout automatique','ok');"
if text.count(old_status) != 1:
    raise SystemExit(f'V61914_UI_START_STATUS_ANCHOR_COUNT={text.count(old_status)}')
new_status = "setStatus('AUTOPILOT DÉMARRÉ',initialSeed?`Seed ${initialSeed} · couverture continue · preuve 3×9/9`:'Couverture automatique jusqu’à épuisement de la frontière Seed Scout','ok');"
text = text.replace(old_status, new_status, 1)

UI.write_text(text, encoding='utf-8')
print('RADAR_V61914_UI=PATCHED')
