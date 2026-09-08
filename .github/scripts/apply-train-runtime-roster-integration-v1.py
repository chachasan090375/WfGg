from pathlib import Path
import hashlib, json

WORKER=Path('frontend/_worker.js')
LIVE=Path('frontend/train-native/app.v14.live.js')
PROD=Path('.github/workflows/production-recette.yml')
README=Path('frontend/train-native/README.md')
V15=Path('frontend/train-native/app.v15.js')
V15_SHA=Path('frontend/train-native/app.v15.js.sha256')

w=WORKER.read_text(encoding='utf-8')
if 'WFGG_TRAIN_ROSTER_INTEGRATION_UI_RUNTIME_V1' in w:
    print('runtime patch already present')
    raise SystemExit(0)

role_old="""    function roleKeyLabel(key) {
        if (key === 'vip')
            return rolePoolLabel('vip');
        if (key === 'driver-r3')
            return rolePoolLabel('r3driver');
        return rolePoolLabel('officer');
    }
"""
role_new=role_old+r'''    /* WFGG_ROSTER_INTEGRATION_UI_V1
       Le backend est l'autorité pour les quotas d'intégration. Le frontend
       affiche les compteurs calculés côté serveur sans recalculer les cycles. */
    function integrationText(fr,en,it,es){
        const lang=currentLanguage();
        return lang==='en'?en:lang==='it'?it:lang==='es'?es:fr;
    }
    function integrationPoolLabel(poolKey){
        if(poolKey==='officer')return integrationText('Conducteur A','Driver A','Conducente A','Conductor A');
        if(poolKey==='r3driver')return integrationText('Conducteur B','Driver B','Conducente B','Conductor B');
        return 'VIP R3';
    }
    function integrationReasonLabel(reason){
        const map={
          new_member:integrationText('Nouveau membre','New member','Nuovo membro','Nuevo miembro'),
          promotion:integrationText('Promotion','Promotion','Promozione','Promoción'),
          demotion:integrationText('Rétrogradation','Demotion','Retrocessione','Descenso'),
          reactivation:integrationText('Réactivation','Reactivation','Riattivazione','Reactivación')
        };
        return map[reason]||integrationText('Intégration','Integration','Integrazione','Integración');
    }
    function integrationTierLabel(tier){
        const n=Number(tier)||0;
        if(n===1)return integrationText('1er tiers','1st third','1° terzo','1.er tercio');
        if(n===2)return integrationText('2e tiers','2nd third','2° terzo','2.º tercio');
        if(n===3)return integrationText('dernier tiers','last third','ultimo terzo','último tercio');
        return '';
    }
    function rotationIntegrationStatuses(){
        return Array.isArray(state.rotationIntegrationStatus)?state.rotationIntegrationStatus:[];
    }
    function activeIntegrationStatusesFor(id){
        return rotationIntegrationStatuses().filter(x=>String(x.memberId)===String(id)&&!x.integrationCompleted);
    }
    function integrationCounterLabel(x){
        const done=Math.max(0,Number(x.completedCount)||0);
        const remainingRaw=Number(x.remainingCount);
        const remaining=Number.isFinite(remainingRaw)?Math.max(0,remainingRaw):Math.max(0,(Number(x.targetCount)||0)-done);
        const target=done+remaining;
        return `${integrationPoolLabel(x.poolKey)} ${done}/${target}`;
    }
    function memberIntegrationHtml(id,{compact=false}={}){
        const rows=activeIntegrationStatusesFor(id);
        if(!rows.length)return '';
        const first=rows[0],head=[integrationReasonLabel(first.reason),first.previousRank&&first.newRank?`${first.previousRank}→${first.newRank}`:'',integrationTierLabel(first.tier)].filter(Boolean).join(' · ');
        const counters=rows.map(integrationCounterLabel).join(' · ');
        const effective=first.effectiveFrom?`${integrationText('Effet','Effective','Effetto','Efecto')} ${fmtShort(parseISO(first.effectiveFrom))}`:'';
        return `<div class="warning roster-integration-status ${compact?'compact':''}"><b>🧭 ${esc(head)}</b><br><span>${esc(counters)}</span>${effective?`<br><small>${esc(effective)}</small>`:''}</div>`;
    }
    function allIntegrationStatusHtml(){
        const rows=rotationIntegrationStatuses().filter(x=>!x.integrationCompleted);
        if(!rows.length)return `<div class="success">✅ ${integrationText('Aucune intégration en cours','No integration in progress','Nessuna integrazione in corso','No hay ninguna integración en curso')}</div>`;
        const ids=[...new Set(rows.map(x=>String(x.memberId)))];
        return `<div class="option-list">${ids.map(id=>{
          const p=byId[id],sub=rows.filter(x=>String(x.memberId)===id),first=sub[0];
          const head=[integrationReasonLabel(first.reason),first.previousRank&&first.newRank?`${first.previousRank}→${first.newRank}`:'',integrationTierLabel(first.tier)].filter(Boolean).join(' · ');
          return `<div class="option"><span>🧭</span><span><b>${esc(p?.pseudo||id)}</b><small>${esc(head)}<br>${esc(sub.map(integrationCounterLabel).join(' · '))}</small></span></div>`;
        }).join('')}</div>`;
    }
'''

home_old="""    <button type=\"button\" class=\"stat-card stat-button\" onclick=\"W.showRotationStatus()\"><small>🔁 Rotation</small><strong>${isOut(m.id) ? 'PAUSE' : 'ACTIVE'}</strong><em>Gérer mon statut</em></button>
  </div>
  `;"""
home_new="""    <button type=\"button\" class=\"stat-card stat-button\" onclick=\"W.showRotationStatus()\"><small>🔁 Rotation</small><strong>${isOut(m.id) ? 'PAUSE' : 'ACTIVE'}</strong><em>Gérer mon statut</em></button>
  </div>
  ${memberIntegrationHtml(m.id)}
  `;"""

modal_old="""    <div class=\"warning\">${pools.length ? `Tu participes actuellement à : ${pools.join(' · ')}.` : 'Ton rang n’est actuellement sélectionné dans aucune rotation automatique.'}</div>
    ${canSelfManage() ? `<button class=\"btn ${isOut(m.id) ? 'success' : 'outline'} full\" onclick=\"W.toggleRotation();W.showRotationStatus()\">${isOut(m.id) ? '✅ Reprendre la rotation' : '⏸ Me retirer de la rotation'}</button>` : ''}`);"""
modal_new="""    <div class=\"warning\">${pools.length ? `Tu participes actuellement à : ${pools.join(' · ')}.` : 'Ton rang n’est actuellement sélectionné dans aucune rotation automatique.'}</div>
    ${memberIntegrationHtml(m.id,{compact:true})}
    ${canSelfManage() ? `<button class=\"btn ${isOut(m.id) ? 'success' : 'outline'} full\" onclick=\"W.toggleRotation();W.showRotationStatus()\">${isOut(m.id) ? '✅ Reprendre la rotation' : '⏸ Me retirer de la rotation'}</button>` : ''}`);"""

save_old="""    async function saveRotationRanks() {
        if (!isAdmin())
            return;
        const rotationRanks = {};
        for (const key of ['officer', 'r3driver', 'vip']) {
            rotationRanks[key] = [...document.querySelectorAll(`input[data-rotation-key=\"${key}\"]:checked`)].map(x => x.value);
            if (!rotationRanks[key].length)
                return toast('Sélectionne au moins un rang dans chaque rotation');
        }
        const ok = await mutate('/api/admin/rotation-ranks', { method: 'PUT', body: JSON.stringify({ rotationRanks }) }, 'Rotations mises à jour');
        if (ok)
            openAdminSection('rotations');
    }
"""
save_new="""    async function saveRotationRanks() {
        if (!isAdmin()) return;
        const rotationRanks={officer:['R5','R4'],r3driver:['R3'],vip:['R3']};
        const ok=await mutate('/api/admin/rotation-ranks',{method:'PUT',body:JSON.stringify({rotationRanks})},'Rotations vérifiées');
        if(ok)openAdminSection('rotations');
    }
"""

admin_old=r'''      <div class="admin-panel">
        <h3>🎚️ Rangs autorisés</h3>
        <p class="admin-lead">Choisis librement les rangs qui participent automatiquement à chacun des trois pools. Tu peux par exemple mettre le VIP sur R3 uniquement, ou sur R3+R2+R1.</p>
        ${rankCheckHtml('officer', 'Conducteur A — un jour sur deux')}
        ${rankCheckHtml('r3driver', 'Conducteur B — l’autre jour')}
        ${rankCheckHtml('vip', 'VIP — tous les jours')}
        <div class="warning">Un même rang peut être présent dans plusieurs pools. Un joueur ne pourra toutefois jamais être Conducteur et VIP le même jour.</div>
        <button class="btn gold full" onclick="W.saveRotationRanks()">💾 Enregistrer les rangs autorisés</button>
      </div>
'''
admin_new=r'''      <div class="admin-panel">
        <h3>🔒 Cycles automatiques</h3>
        <p class="admin-lead">Les trois cycles sont autoritatifs et indépendants. Les rangs ne sont pas modifiables depuis l’interface.</p>
        <div class="mini-grid">
          <div class="stat-card"><small>🚂 Conducteur A</small><strong>R4 / R5</strong><em>1 passage par cycle</em></div>
          <div class="stat-card"><small>🚆 Conducteur B</small><strong>R3</strong><em>1 passage par cycle</em></div>
          <div class="stat-card"><small>⭐ VIP</small><strong>R3</strong><em>2 passages par cycle</em></div>
          <div class="stat-card"><small>🎁 R2 / R1</small><strong>Hors cycle</strong><em>VIP uniquement sur nomination exceptionnelle</em></div>
        </div>
        <div class="warning">Une nomination VIP exceptionnelle R2/R1 apparaît bien au planning mais ne consomme jamais le compteur VIP R3.</div>
      </div>

      <div class="admin-panel">
        <h3>🧭 Intégrations en cours</h3>
        <p class="admin-lead">Arrivées, promotions, rétrogradations et réactivations : le quota affiché est celui du cycle réellement rejoint.</p>
        ${allIntegrationStatusHtml()}
      </div>
'''

pairs=[
  ("                vip: ['R3', 'R2', 'R1']", "                vip: ['R3']", 'default VIP pool'),
  ("            state.settings.rotationRanks.vip = ['R3', 'R2', 'R1'];", "            state.settings.rotationRanks.vip = ['R3'];", 'fallback VIP pool'),
  (role_old, role_new, 'integration helper block'),
  (home_old, home_new, 'Moi integration card'),
  (modal_old, modal_new, 'rotation modal integration card'),
  (save_old, save_new, 'fixed saveRotationRanks'),
  (admin_old, admin_new, 'fixed cycles admin panel'),
]

# Validate the exact runtime replacements against the last captured live bridge.
sim=LIVE.read_text(encoding='utf-8')
for before,after,label in pairs:
    if before not in sim:
        raise SystemExit(f'live capture missing patch target: {label}')
    sim=sim.replace(before,after,1)
for required in [
    'WFGG_ROSTER_INTEGRATION_UI_V1',
    "vip: ['R3']",
    'rotationIntegrationStatus',
    'remainingCount',
    '🎁 R2 / R1',
    '🧭 Intégrations en cours',
]:
    if required not in sim:
        raise SystemExit(f'simulation missing: {required}')
Path('/tmp/train-runtime-roster-sim.js').write_text(sim,encoding='utf-8')

# Generate a safe JS replacement block. JSON strings protect target template literals.
lines=[
"    /* WFGG_TRAIN_ROSTER_INTEGRATION_UI_RUNTIME_V1",
"       Le Train servi en production reste l'upstream historique patché par le Portail.",
"       Ce bloc aligne ce runtime sur le contrat des trois cycles autoritatifs et",
"       expose les compteurs d'intégration calculés par le backend. */",
"    {",
"      const rosterIntegrationUiPatches = [",
]
for before,after,label in pairs:
    lines.append('        ['+json.dumps(before,ensure_ascii=False)+','+json.dumps(after,ensure_ascii=False)+','+json.dumps(label,ensure_ascii=False)+'],')
lines += [
"      ];",
"      for (const [before, after, label] of rosterIntegrationUiPatches) {",
"        if (rewritten.includes(before)) {",
"          rewritten = rewritten.replace(before, after);",
"        } else if (!rewritten.includes(after)) {",
"          console.warn('WFGG_TRAIN_ROSTER_INTEGRATION_PATCH_MISS', label);",
"        }",
"      }",
"    }",
"",
]
block='\n'.join(lines)
needle='    /* WFGG_TRAIN_DANGLING_TOKEN_FIX_V1'
if needle not in w:
    raise SystemExit('worker insertion point missing')
w=w.replace(needle,block+needle,1)
header="    jsHeaders.set('X-WfGg-Train-Cache-Bridge', 'v1');"
if header not in w:
    raise SystemExit('worker header marker missing')
w=w.replace(header,header+"\n    jsHeaders.set('X-WfGg-Train-Roster-Integration-Bridge', 'v1');",1)
WORKER.write_text(w,encoding='utf-8')

# Permanent production guard: verify the actual /train/app.js runtime, not only source/reference files.
y=PROD.read_text(encoding='utf-8')
source_guard="          grep -q 'WFGG_TRAIN_EXCHANGE_ORPHAN_FALLBACK_V1' frontend/_worker.js\n"
if source_guard not in y:
    raise SystemExit('production source guard insertion point missing')
y=y.replace(source_guard,source_guard+"          grep -q 'WFGG_TRAIN_ROSTER_INTEGRATION_UI_RUNTIME_V1' frontend/_worker.js\n",1)
wait_guard="              && grep -Fq 'state.__serverSchedule' /tmp/app.js \\\n"
if wait_guard not in y:
    raise SystemExit('production live wait insertion point missing')
y=y.replace(wait_guard,wait_guard+"              && grep -Fq 'WFGG_ROSTER_INTEGRATION_UI_V1' /tmp/app.js \\\n              && grep -Fq '🧭 Intégrations en cours' /tmp/app.js \\\n",1)
post_guard="          grep -Fq 'Retirer mon annonce' /tmp/app.js\n"
if post_guard not in y:
    raise SystemExit('production post guard insertion point missing')
y=y.replace(post_guard,post_guard+"          grep -Fq 'WFGG_ROSTER_INTEGRATION_UI_V1' /tmp/app.js\n          grep -Fq 'rotationIntegrationStatus' /tmp/app.js\n          grep -Fq 'remainingCount' /tmp/app.js\n          grep -Fq \"vip: ['R3']\" /tmp/app.js\n",1)
PROD.write_text(y,encoding='utf-8')

# Keep the reference checksum/documentation coherent with PR #17.
digest=hashlib.sha256(V15.read_bytes()).hexdigest()
V15_SHA.write_text(f'{digest}  frontend/train-native/app.v15.js\n',encoding='utf-8')
r=README.read_text(encoding='utf-8')
old="""À ce stade :
- aucun routage de production n'est modifié ;
- `_worker.js` continue de servir le bridge v14 existant ;
- ce fichier sert uniquement de référence canonique pour supprimer progressivement
  les réécritures runtime.
"""
new="""État actuel :
- `app.v15.js` reste la référence canonique du frontend Train consolidé ;
- la production `/train/app.js` est encore obtenue depuis l'upstream historique puis
  corrigée par `_worker.js` ;
- le bridge runtime `WFGG_TRAIN_ROSTER_INTEGRATION_UI_RUNTIME_V1` aligne maintenant
  la production sur les cycles fixes et les quotas d'intégration de cette référence ;
- la recette de production vérifie explicitement ce marqueur dans le JS réellement servi.
"""
if old not in r:
    raise SystemExit('README state block missing')
README.write_text(r.replace(old,new,1),encoding='utf-8')

print('runtime roster integration patch prepared')
