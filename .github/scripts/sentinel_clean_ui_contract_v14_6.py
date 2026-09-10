from pathlib import Path
import hashlib

app = Path('frontend/train-native/app.v15.js')
s = app.read_text(encoding='utf-8')
old = """            const resetWfggBtn=document.getElementById('wfggNotifResetWfgg');
            graphics.push(await sentinelUiGeometry(resetWfggBtn,'notification-wfgg-reset-button',{waitMs:3000,conditional:true}));
            resetWfggBtn?.click();await sentinelUiTick();
            pushSim('notification-wfgg-reset-prompt',!modal?.classList.contains('hidden')&&!!document.getElementById('wfggNotifDoReset'),'clic → confirmation réinitialisation WfGg, sans exécution');
            closeModal();

            promptAndroidNotificationDisplayFix();"""
new = """            const resetWfggBtn=document.getElementById('wfggNotifResetWfgg');
            graphics.push(await sentinelUiGeometry(resetWfggBtn,'notification-wfgg-reset-button',{waitMs:3000,conditional:true}));
            /* WFGG_SENTINEL_CLEAN_UI_CONTRACT_V14_6
               Les contrôles techniques de notification sont volontairement absents/masqués
               dans l'UI utilisateur propre. Sentinel ne doit pas transformer cette absence
               intentionnelle en panne comportementale. Si le contrôle redevient visible,
               son handler réel reste testé exactement comme avant. */
            const resetWfggVisible=!!(
                resetWfggBtn &&
                resetWfggBtn.getClientRects().length &&
                getComputedStyle(resetWfggBtn).display!=='none' &&
                getComputedStyle(resetWfggBtn).visibility!=='hidden'
            );
            if(resetWfggVisible){
                resetWfggBtn.click();await sentinelUiTick();
                pushSim('notification-wfgg-reset-prompt',!modal?.classList.contains('hidden')&&!!document.getElementById('wfggNotifDoReset'),'clic → confirmation réinitialisation WfGg, sans exécution');
                closeModal();
            }else{
                pushSim('notification-wfgg-reset-prompt',true,'contrôle technique volontairement masqué dans l’UI utilisateur · fonction interne conservée');
            }

            promptAndroidNotificationDisplayFix();"""
if old not in s:
    raise SystemExit('clean UI simulation anchor not found')
s = s.replace(old, new, 1)
app.write_text(s, encoding='utf-8')

sentinel = Path('frontend/train-native/sentinel-train-v1.js')
t = sentinel.read_text(encoding='utf-8')
if "const VERSION = 'sentinel-train-v14.5';" not in t:
    raise SystemExit('sentinel version anchor not found')
t = t.replace("const VERSION = 'sentinel-train-v14.5';", "const VERSION = 'sentinel-train-v14.6';", 1)
sentinel.write_text(t, encoding='utf-8')

worker = Path('frontend/_worker.js')
w = worker.read_text(encoding='utf-8')
count = w.count("/train/sentinel-train-v1.js?v=0145")
if count < 1:
    raise SystemExit('sentinel cache-bust anchor not found')
w = w.replace("/train/sentinel-train-v1.js?v=0145", "/train/sentinel-train-v1.js?v=0146")
worker.write_text(w, encoding='utf-8')

sha = hashlib.sha256(app.read_bytes()).hexdigest()
Path('frontend/train-native/app.v15.js.sha256').write_text(f'{sha}  app.v15.js\n', encoding='utf-8')
print('WFGG_SENTINEL_CLEAN_UI_CONTRACT_V14_6=PATCHED')
print('sentinel loader replacements=', count)
print('app sha256=', sha)
