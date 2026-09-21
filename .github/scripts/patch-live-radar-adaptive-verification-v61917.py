#!/usr/bin/env python3
from pathlib import Path

UI = Path('/tmp/wfgg-radar/public/live-radar.html')
ui = UI.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_AUTOPILOT_ADAPTIVE_VERIFICATION_UI_V61917'
bt = chr(96)
dollar = chr(36)

if marker not in ui:
    anchor = '<!-- WFGG_RADAR_AUTOPILOT_FAILURE_SCOPE_CONTINUE_UI_V61916 -->'
    if ui.count(anchor) != 1:
        raise SystemExit(f'V61917_UI_MARKER_ANCHOR_COUNT={ui.count(anchor)}')
    ui = ui.replace(anchor, anchor + '\n  <!-- ' + marker + ' -->', 1)

    old_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.16 · ARRÊTÉ</span>'
    new_title = '<span id="autopilotTitle" class="federated-title">AUTOPILOT V6.19.17 · ARRÊTÉ</span>'
    if ui.count(old_title) != 1:
        raise SystemExit(f'V61917_UI_TITLE_ANCHOR_COUNT={ui.count(old_title)}')
    ui = ui.replace(old_title, new_title, 1)

    old_payload = "body:JSON.stringify({initialSeed,fullCyclesPerCluster:3,coverageMode:true})"
    new_payload = "body:JSON.stringify({initialSeed,fullCyclesPerCluster:1,adaptiveVerification:true,coverageMode:true})"
    if ui.count(old_payload) != 1:
        raise SystemExit(f'V61917_UI_PAYLOAD_ANCHOR_COUNT={ui.count(old_payload)}')
    ui = ui.replace(old_payload, new_payload, 1)

    seed_expr = dollar + '{initialSeed}'
    old_status = "setStatus('AUTOPILOT DÉMARRÉ',initialSeed?" + bt + "Seed " + seed_expr + " · couverture continue · preuve 3×9/9" + bt + ":'Couverture automatique jusqu’à épuisement de la frontière Seed Scout','ok');"
    new_status = "setStatus('AUTOPILOT DÉMARRÉ',initialSeed?" + bt + "Seed " + seed_expr + " · validation adaptative · 1×9/9 si propre" + bt + ":'Couverture rapide · 1×9/9 valide par grappe, reprises seulement si nécessaire','ok');"
    if ui.count(old_status) != 1:
        raise SystemExit(f'V61917_UI_STATUS_ANCHOR_COUNT={ui.count(old_status)}')
    ui = ui.replace(old_status, new_status, 1)

    info_old = 'READ-ONLY côté Last War · mode couverture continue jusqu’à épuisement réel de la frontière Seed Scout · ledger persistant · aucun token conservé.'
    info_new = 'READ-ONLY côté Last War · Fast Coverage adaptatif : 1×9/9 valide suffit, retries seulement si partiel/échec · ledger persistant · aucun token conservé.'
    if ui.count(info_old) != 1:
        raise SystemExit(f'V61917_UI_INFO_ANCHOR_COUNT={ui.count(info_old)}')
    ui = ui.replace(info_old, info_new, 1)

    windows = dollar + '{job.coverageWindows||0}'
    probes = dollar + '{job.coverageCandidatesScouted||0}'
    progress_anchor = "  if(job.coverageMode)progress+=" + bt + " · fenêtres " + windows + " · probes " + probes + bt + ";"
    if ui.count(progress_anchor) != 1:
        raise SystemExit(f'V61917_UI_PROGRESS_ANCHOR_COUNT={ui.count(progress_anchor)}')
    ui = ui.replace(
        progress_anchor,
        progress_anchor + "\n  if(job.adaptiveVerification)progress+=' · vérification adaptative';",
        1,
    )

UI.write_text(ui, encoding='utf-8')
print('RADAR_V61917_UI_ADAPTIVE_VERIFICATION=READY')
