from pathlib import Path
import hashlib

sentinel = Path('frontend/train-native/sentinel-train-v1.js')
app = Path('frontend/train-native/app.v15.js')
worker = Path('frontend/_worker.js')
checksum = Path('frontend/train-native/app.v15.js.sha256')

s = sentinel.read_text(encoding='utf-8')
s = s.replace("const VERSION = 'sentinel-train-v14.4';", "const VERSION = 'sentinel-train-v14.5';", 1)
anchor = """    const portalSource=(file,fn)=>({repository:'chachasan090375/WfGg',file,function:fn||null,line:portalSourceMap?.files?.[file]?.functions?.[fn]?.line||null,sourceCommit:portalSourceMap?.sourceCommit||null});\n"""
insert = anchor + """    /* WFGG_SENTINEL_PORTAL_TRAIN_AUTH_REPAIR_V14_5\n       Les erreurs serveur participent aussi au moteur de correctifs. Un 401\n       sur train-snapshot avec « Session Portail requise » signifie que le\n       module a été autorisé mais que l'identité s'est perdue avant wfgg-train. */\n    const snapshotFailure=bad.get('train-snapshot');\n    if(snapshotFailure && (Number(snapshotFailure.status||0)===401 || /401|Session Portail requise/i.test([snapshotFailure.observed,snapshotFailure.detail,snapshotFailure.probableCause].filter(Boolean).join(' '))))out.push(localRepairCandidateV12({\n      id:'repair-train-portal-session-bridge-v14-5',title:'Réparer le bridge de session Portail → Train',score:100,verdict:'recommended',\n      target:'frontend/_worker.js + wfgg-train/worker.js :: proxy /api/snapshot / requireAuth',\n      proposedChange:'Conserver le Portail comme seule autorité. Après validation du cookie HttpOnly, transmettre explicitement la session au Worker Train par X-WfGg-Portal-Token avec un transport serveur de secours strictement marqué; le backend doit revalider cette session Portail et ne jamais réactiver le login Train historique.',\n      simulation:{readonly:true,portalOnlyPreserved:true,legacyAuthDisabled:true,expectedSnapshotStatus:200,expectedBridge:'cookie-auth-v6'},\n      evidence:['/train/ est déjà autorisé par la session Portail alors que /api/snapshot répond 401 « Session Portail requise ».','La panne est située sur le saut Worker Portail → backend Train, avant le chargement des données Train.'],\n      risks:['Ne jamais accepter Authorization comme authentification Train autonome.','Le fallback doit être limité au bridge serveur explicitement marqué et revalidé auprès du Portail.'],\n      manualValidation:['Accès direct /train/ sans session Portail → refus/redirect.','Session Portail valide → /api/snapshot HTTP 200.','/api/snapshot sans session Portail → HTTP 401/403.'],\n      source:portalSource('frontend/_worker.js',null)\n    }));\n"""
if anchor not in s:
    raise SystemExit('sentinel repair anchor not found')
s = s.replace(anchor, insert, 1)
old_call = "const localCandidates=localRepairCandidatesV12(local,portalSourceMap);"
new_call = "const localCandidates=localRepairCandidatesV12(checks,portalSourceMap);"
if old_call not in s:
    raise SystemExit('sentinel localCandidates anchor not found')
s = s.replace(old_call, new_call, 1)
sentinel.write_text(s, encoding='utf-8')

p = app.read_text(encoding='utf-8')
anchor_app = """        if (local.bridge)\n            lines.push(`Bridge: ${local.bridge}`);\n"""
insert_app = anchor_app + """        /* WFGG_SENTINEL_BOOT_REPAIR_VISUAL_V14_5\n           Le correctif prescriptif est visible même si le Sentinel serveur ou\n           son overlay ne finit pas de s'ouvrir sur Android. */\n        if (Number(local.status || 0) === 401 && /Session Portail requise/i.test(String(local.error || local.message || ''))) {\n            lines.push('');\n            lines.push('🧭 CORRECTIF SENTINEL RECOMMANDÉ · 100/100');\n            lines.push('Réparer le bridge de session Portail → Train');\n            lines.push('Cause racine: /train/ est autorisé, mais la session disparaît avant /api/snapshot.');\n            lines.push('Proposition: transmettre côté serveur la session Portail validée vers wfgg-train, la revalider côté backend et conserver l’auth Train historique désactivée.');\n            lines.push('Simulation: READONLY · attendu après correction: /api/snapshot HTTP 200 · accès sans Portail toujours refusé.');\n            lines.push('Statut: RECOMMANDÉ · aucun correctif appliqué automatiquement.');\n        }\n"""
if anchor_app not in p:
    raise SystemExit('app inline repair anchor not found')
p = p.replace(anchor_app, insert_app, 1)
app.write_text(p, encoding='utf-8')

a = worker.read_text(encoding='utf-8')
if "sentinel-train-v1.js?v=0144" not in a:
    raise SystemExit('worker sentinel cache bust anchor not found')
a = a.replace("sentinel-train-v1.js?v=0144", "sentinel-train-v1.js?v=0145", 1)
worker.write_text(a, encoding='utf-8')

digest = hashlib.sha256(app.read_bytes()).hexdigest()
checksum.write_text(f'{digest}  app.v15.js\n', encoding='utf-8')

print('WFGG_SENTINEL_REPAIR_VISUAL_V14_5=PATCHED')
print('app_sha256=' + digest)
