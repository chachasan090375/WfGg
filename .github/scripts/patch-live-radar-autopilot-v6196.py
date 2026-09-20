#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')
text = UI.read_text(encoding='utf-8')
MARKER = 'WFGG_RADAR_AUTOPILOT_CONTINUE_NO_DATA_UI_V6196'

if MARKER in text:
    print('RADAR_V6196_AUTOPILOT_UI=ALREADY_PRESENT')
    raise SystemExit(0)

text = text.replace(
    '<!-- WFGG_RADAR_AUTOPILOT_UI_V6194 -->',
    '<!-- WFGG_RADAR_AUTOPILOT_UI_V6194 -->\n  <!-- WFGG_RADAR_AUTOPILOT_CONTINUE_NO_DATA_UI_V6196 -->',
    1,
)
text = text.replace(
    '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.4 · ARRÊTÉ</span>',
    '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.6 · ARRÊTÉ</span>',
    1,
)
text = text.replace(
    'READ-ONLY côté Last War · les cycles complets mettent à jour le Collector. Les cycles partiels ne comptent pas.',
    'READ-ONLY côté Last War · cycles complets conservés · seeds sans données ignorées après 3 essais · erreurs globales bloquantes.',
    1,
)

old_title = "title.textContent=`AUTOPILOT V6.19.4 · ${status} · ${phase}`;"
new_title = "const version=String(job.autopilotVersion||'v6.19.6').replace(/^v/i,'V');title.textContent=`AUTOPILOT ${version} · ${status} · ${phase}`;"
if text.count(old_title) != 1:
    raise SystemExit(f'V6196_UI_TITLE_ANCHOR_COUNT={text.count(old_title)}')
text = text.replace(old_title, new_title, 1)

old_progress = "let progress=`Grappe ${Number(job.confirmedClusters||0)+1}/${job.maxClusters||5} · seed ${seed} · cycles 9/9 ${job.validatedCycles||0}/${job.requiredFullCycles||3} · partiels ${job.partialCycles||0}`;"
new_progress = "let progress=`Grappe ${Number(job.confirmedClusters||0)+1}/${job.maxClusters||5} · seed ${seed} · cycles 9/9 ${job.validatedCycles||0}/${job.requiredFullCycles||3} · partiels ${job.partialCycles||0} · ignorées ${job.skippedSeeds?.length||0}`;"
if text.count(old_progress) != 1:
    raise SystemExit(f'V6196_UI_PROGRESS_ANCHOR_COUNT={text.count(old_progress)}')
text = text.replace(old_progress, new_progress, 1)

old_note = "if(job.lastCycle?.classification==='PARTIAL')note.textContent=`Dernier cycle partiel ${job.lastCycle.regionsCompleted||0}/9 : conservé mais NON compté. Relance automatique de ${job.currentCommand||'la même seed'}.`;\n  else if(phase==='CLUSTER_CONFIRMED')note.textContent='Grappe confirmée sur 3 cycles complets · recherche automatique de la seed suivante.';"
new_note = "if(job.lastCycle?.classification==='PARTIAL')note.textContent=`Dernier cycle partiel ${job.lastCycle.regionsCompleted||0}/9 : conservé mais NON compté. Relance automatique de ${job.currentCommand||'la même seed'}.`;\n  else if(phase==='SEED_SKIPPED_NO_DATA'||(phase==='SCOUTING'&&job.lastSkippedSeed)){const s=job.lastSkippedSeed||{};note.textContent=`Seed ${s.seed||'—'} : aucune donnée exploitable après retries · ${s.validatedCycles||0}/${job.requiredFullCycles||3} preuve(s) 9/9 conservée(s) · passage automatique à la suivante.`;}\n  else if(phase==='CYCLE_NO_DATA_RETRY')note.textContent=`Aucune donnée exploitable sur ${job.currentCommand||'la seed'} · essai ${job.consecutiveNoData||1}/${job.noDataRetryLimit||3}.`;\n  else if(phase==='CLUSTER_CONFIRMED')note.textContent='Grappe confirmée sur 3 cycles complets · recherche automatique de la seed suivante.';"
if text.count(old_note) != 1:
    raise SystemExit(f'V6196_UI_NOTE_ANCHOR_COUNT={text.count(old_note)}')
text = text.replace(old_note, new_note, 1)

old_start = "setStatus('AUTOPILOT DÉMARRÉ',initialSeed?`Seed ${initialSeed} · preuve fraîche 3×9/9`:'Seed Scout automatique','ok');"
new_start = "setStatus('AUTOPILOT DÉMARRÉ',initialSeed?`Seed ${initialSeed} · objectif 3×9/9 · preuves valides existantes réutilisées`:'Seed Scout automatique','ok');"
if text.count(old_start) == 1:
    text = text.replace(old_start, new_start, 1)

UI.write_text(text, encoding='utf-8')
print('RADAR_V6196_AUTOPILOT_UI=PATCHED')
