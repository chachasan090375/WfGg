from pathlib import Path
import re

p=Path('frontend/train-native/app.v15.js')
s=p.read_text(encoding='utf-8')

# 1. Fixed automatic pool defaults: VIP is R3 only.
s,n=re.subn(r"vip:\s*\['R3',\s*'R2',\s*'R1'\]", "vip: ['R3']", s)
if n < 1:
    raise SystemExit('default VIP R3/R2/R1 marker not found')
s,n2=re.subn(r"state\.settings\.rotationRanks\.vip\s*=\s*\['R3',\s*'R2',\s*'R1'\];", "state.settings.rotationRanks.vip = ['R3'];", s)
print('fixed VIP defaults', n, n2)

# 2. Integration UI helpers, driven only by server snapshot status.
marker="""    function roleKeyLabel(key) {
        if (key === 'vip')
            return rolePoolLabel('vip');
        if (key === 'driver-r3')
            return rolePoolLabel('r3driver');
        return rolePoolLabel('officer');
    }
"""
if marker not in s:
    raise SystemExit('roleKeyLabel marker missing')
helpers=marker+r'''    /* WFGG_ROSTER_INTEGRATION_UI_V1
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
s=s.replace(marker,helpers,1)
print('added integration display helpers')

# 3. Current user's status gets the integration marker/card.
old="""    <button type=\"button\" class=\"stat-card stat-button\" onclick=\"W.showRotationStatus()\"><small>🔁 Rotation</small><strong>${isOut(m.id) ? 'PAUSE' : 'ACTIVE'}</strong><em>Gérer mon statut</em></button>
  </div>
  `;"""
new="""    <button type=\"button\" class=\"stat-card stat-button\" onclick=\"W.showRotationStatus()\"><small>🔁 Rotation</small><strong>${isOut(m.id) ? 'PAUSE' : 'ACTIVE'}</strong><em>Gérer mon statut</em></button>
  </div>
  ${memberIntegrationHtml(m.id)}
  `;"""
if old not in s:
    raise SystemExit('renderHome status grid marker missing')
s=s.replace(old,new,1)
print('added integration card on Moi')

# 4. Profile/rotation modal also shows integration details.
old="""    <div class=\"warning\">${pools.length ? `Tu participes actuellement à : ${pools.join(' · ')}.` : 'Ton rang n’est actuellement sélectionné dans aucune rotation automatique.'}</div>
    ${canSelfManage() ? `<button class=\"btn ${isOut(m.id) ? 'success' : 'outline'} full\" onclick=\"W.toggleRotation();W.showRotationStatus()\">${isOut(m.id) ? '✅ Reprendre la rotation' : '⏸ Me retirer de la rotation'}</button>` : ''}`);"""
new="""    <div class=\"warning\">${pools.length ? `Tu participes actuellement à : ${pools.join(' · ')}.` : 'Ton rang n’est actuellement sélectionné dans aucune rotation automatique.'}</div>
    ${memberIntegrationHtml(m.id,{compact:true})}
    ${canSelfManage() ? `<button class=\"btn ${isOut(m.id) ? 'success' : 'outline'} full\" onclick=\"W.toggleRotation();W.showRotationStatus()\">${isOut(m.id) ? '✅ Reprendre la rotation' : '⏸ Me retirer de la rotation'}</button>` : ''}`);"""
if old not in s:
    raise SystemExit('rotation status modal marker missing')
s=s.replace(old,new,1)
print('added integration card in rotation modal')

# 5. Replace misleading editable rank pools with fixed authoritative contract.
start="""      <div class=\"admin-panel\">
        <h3>🎚️ Rangs autorisés</h3>"""
end="""      <div class=\"admin-panel\">
        <h3>↕️ Ordre de priorité</h3>"""
i=s.find(start)
j=s.find(end,i+1)
if i<0 or j<0:
    raise SystemExit('admin rotations editable pool block missing')
fixed=r'''      <div class="admin-panel">
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
s=s[:i]+fixed+s[j:]
print('replaced editable pools with fixed contract + integration admin view')

# 6. saveRotationRanks cannot attempt to redefine fixed pools if called by stale cached UI.
pat=re.compile(r"    async function saveRotationRanks\(\) \{.*?\n    \}\n    function adminBackButton",re.S)
m=pat.search(s)
if not m:
    raise SystemExit('saveRotationRanks function missing')
replacement=r'''    async function saveRotationRanks() {
        if (!isAdmin()) return;
        const rotationRanks={officer:['R5','R4'],r3driver:['R3'],vip:['R3']};
        const ok=await mutate('/api/admin/rotation-ranks',{method:'PUT',body:JSON.stringify({rotationRanks})},'Rotations vérifiées');
        if(ok)openAdminSection('rotations');
    }
    function adminBackButton'''
s=s[:m.start()]+replacement+s[m.end():]
print('made stale save action authoritative')

p.write_text(s,encoding='utf-8')
print('WFGG_TRAIN_ROSTER_INTEGRATION_UI_V1 applied')
