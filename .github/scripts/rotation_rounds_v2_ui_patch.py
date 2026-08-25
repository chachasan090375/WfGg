from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Train: manual planning remains in Train and becomes a 14-day rolling window.
# ---------------------------------------------------------------------------
train_path = Path('frontend/train-native/app.v14.live.js')
train = train_path.read_text(encoding='utf-8')
train = replace_once(
    train,
    """        if (section === 'manual') {\n            const base = mondayOf(new Date());\n            const days = [0, 1, 2, 3, 4, 5, 6].map(i => addDays(base, i));\n            const sched = schedule(), all = ROSTER.filter(p => p.active);\n            el.innerHTML = `${adminBackButton()}\n      <div class=\"section-title\"><h2>✍️ Planning manuel</h2><p>Semaine en cours</p></div>""",
    """        if (section === 'manual') {\n            /* WFGG_TRAIN_MANUAL_14_DAYS_V1\n               L'édition reste exclusivement dans Train et s'appuie sur le\n               planning serveur déjà synchronisé. Aucun planning n'est recalculé\n               côté Portail. La fenêtre couvre aujourd'hui + 13 jours. */\n            const base = new Date();\n            base.setHours(0, 0, 0, 0);\n            const days = Array.from({ length: 14 }, (_, i) => addDays(base, i));\n            const sched = schedule(), all = ROSTER.filter(p => p.active);\n            el.innerHTML = `${adminBackButton()}\n      <div class=\"section-title\"><h2>✍️ Planning manuel</h2><p>14 prochains jours</p></div>""",
    'Train manual 14-day block'
)
train = replace_once(
    train,
    '<span>✍️</span><div><b>Planning manuel</b><small>Corriger exceptionnellement une journée</small></div><i>→</i>',
    '<span>✍️</span><div><b>Planning manuel</b><small>Préparer et corriger les 14 prochains jours</small></div><i>→</i>',
    'Train manual dashboard description'
)
train_path.write_text(train, encoding='utf-8')

# ---------------------------------------------------------------------------
# Portal: read-only Train rotation summary on home + R4/R5 per-player section.
# ---------------------------------------------------------------------------
portal_path = Path('frontend/portal-v070.js')
portal = portal_path.read_text(encoding='utf-8')

portal = replace_once(
    portal,
    "const state={user:null,membership:null,alliance:null,system:null,permissions:null,portalSettings:{},lang:initialLanguage(),members:[],filters:new Set(),search:'',settingsTab:'profile',sessions:[]};",
    "const state={user:null,membership:null,alliance:null,system:null,permissions:null,portalSettings:{},lang:initialLanguage(),members:[],filters:new Set(),search:'',settingsTab:'profile',sessions:[],trainRotationSummary:null,trainRotationLoading:false};",
    'Portal state rotation summary'
)
portal = replace_once(
    portal,
    "function clearSession(){localStorage.removeItem(TOKEN_KEY);Object.assign(state,{user:null,membership:null,alliance:null,system:null,permissions:null,portalSettings:{},members:[],sessions:[]});}",
    "function clearSession(){localStorage.removeItem(TOKEN_KEY);Object.assign(state,{user:null,membership:null,alliance:null,system:null,permissions:null,portalSettings:{},members:[],sessions:[],trainRotationSummary:null,trainRotationLoading:false});}",
    'Portal clearSession rotation summary'
)

anchor = """function paintAllianceIdentity(){\n  const allianceName=state.alliance?.name||'WfGg';"""
if anchor not in portal:
    raise SystemExit('Portal paintAllianceIdentity anchor missing')

helper_block = r'''
/* WFGG_PORTAL_TRAIN_ROTATION_READONLY_V1
   Le Portail ne génère jamais le planning Train. Il lit uniquement le snapshot
   autoritatif fourni par Train puis en extrait les passages déjà programmés. */
function trainRotationLabels(){
  const all={
    fr:{title:'Ma rotation Train',driverA:'Conducteur A',driverB:'Conducteur B',vip:'VIP',total:'Total',last:'Dernier',next:'Prochain',none:'—',statsTitle:'Rotations par joueur',statsDesc:'Historique et prochains passages issus directement du planning Train.'},
    it:{title:'La mia rotazione Treno',driverA:'Conducente A',driverB:'Conducente B',vip:'VIP',total:'Totale',last:'Ultimo',next:'Prossimo',none:'—',statsTitle:'Rotazioni per giocatore',statsDesc:'Storico e prossimi turni letti direttamente dal calendario Treno.'},
    en:{title:'My Train rotation',driverA:'Driver A',driverB:'Driver B',vip:'VIP',total:'Total',last:'Last',next:'Next',none:'—',statsTitle:'Rotations by player',statsDesc:'History and upcoming turns read directly from the Train schedule.'},
    es:{title:'Mi rotación del Tren',driverA:'Conductor A',driverB:'Conductor B',vip:'VIP',total:'Total',last:'Último',next:'Próximo',none:'—',statsTitle:'Rotaciones por jugador',statsDesc:'Historial y próximos turnos leídos directamente del calendario del Tren.'}
  };
  return all[state.lang]||all.fr;
}
function trainLocalISO(d=new Date()){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function trainHistoryKey(v){return String(v||'').trim().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'')}
function trainManualBase(snapshot,user,role){
  const mh=snapshot?.state?.manualHistory||{},counts=mh?.counts?.[role]||{},links=mh?.links||{};
  const linked=links[user?.id];
  if(linked&&counts[linked])return counts[linked];
  const key=trainHistoryKey(user?.pseudo||user?.display_name||user?.player_name||'');
  return Object.values(counts).find(x=>trainHistoryKey(x?.name)===key)||{count:0,last:null};
}
function trainRotationForUser(snapshot,user){
  const schedule=Array.isArray(snapshot?.schedule)?snapshot.schedule:[],today=trainLocalISO(),mh=snapshot?.state?.manualHistory||{};
  const cutoff=String(mh.cutoff||'0000-00-00'),id=String(user?.id||'');
  const baseDriver=trainManualBase(snapshot,user,'driver'),baseVip=trainManualBase(snapshot,user,'vip');
  const past=schedule.filter(x=>x?.date>cutoff&&x.date<today);
  const pastDriver=past.filter(x=>String(x.driverId||'')===id),pastVip=past.filter(x=>String(x.vipId||'')===id);
  const nextDriver=schedule.find(x=>x?.date>=today&&String(x.driverId||'')===id)||null;
  const nextVip=schedule.find(x=>x?.date>=today&&String(x.vipId||'')===id)||null;
  const lastDriver=pastDriver.length?pastDriver[pastDriver.length-1].date:(baseDriver.last||null);
  const lastVip=pastVip.length?pastVip[pastVip.length-1].date:(baseVip.last||null);
  const rank=String(user?.rank||'').toUpperCase();
  const driverRole=nextDriver?.driverClass==='officer'||['R4','R5'].includes(rank)?'A':'B';
  return {id:user?.id,pseudo:user?.pseudo||user?.display_name||user?.player_name||'',rank,
    driver:Number(baseDriver.count||0)+pastDriver.length,driverLast:lastDriver,driverNext:nextDriver?.date||null,driverRole,
    vip:Number(baseVip.count||0)+pastVip.length,vipLast:lastVip,vipNext:nextVip?.date||null};
}
function trainDateLabel(ds){if(!ds)return trainRotationLabels().none;try{return new Date(`${ds}T12:00:00`).toLocaleDateString(state.lang==='en'?'en-GB':state.lang==='it'?'it-IT':state.lang==='es'?'es-ES':'fr-FR',{day:'2-digit',month:'2-digit',year:'2-digit'});}catch{return ds}}
function renderHomeTrainRotationCard(){
  const grid=document.querySelector('.module-grid');if(!grid)return;
  let card=$('homeTrainRotationCard');
  if(!card){card=document.createElement('section');card.id='homeTrainRotationCard';card.className='glass-card settings-card-block';grid.parentNode.insertBefore(card,grid);}
  const x=trainRotationLabels(),r=state.trainRotationSummary;
  if(!r){card.innerHTML=`<div class="section-heading"><h3>🚂 ${esc(x.title)}</h3></div><span class="muted">…</span>`;return;}
  const driverLabel=r.driverRole==='A'?x.driverA:x.driverB;
  card.innerHTML=`<div class="section-heading"><h3>🚂 ${esc(x.title)}</h3></div><div class="readonly-grid"><div><small>${esc(driverLabel)} · ${esc(x.total)}</small><strong>${r.driver||0}</strong><small>${esc(x.last)} : ${esc(trainDateLabel(r.driverLast))}<br>${esc(x.next)} : ${esc(trainDateLabel(r.driverNext))}</small></div><div><small>⭐ ${esc(x.vip)} · ${esc(x.total)}</small><strong>${r.vip||0}</strong><small>${esc(x.last)} : ${esc(trainDateLabel(r.vipLast))}<br>${esc(x.next)} : ${esc(trainDateLabel(r.vipNext))}</small></div></div>`;
}
async function loadHomeTrainRotation(){
  if(!state.user||state.trainRotationLoading)return;
  state.trainRotationLoading=true;renderHomeTrainRotationCard();
  try{const snap=await trainAdminApi('/api/snapshot',{method:'GET'});state.trainRotationSummary=trainRotationForUser(snap,snap.me||{});}catch(_){state.trainRotationSummary=null;}finally{state.trainRotationLoading=false;renderHomeTrainRotationCard();}
}
function buildPlayerRotationRows(analytics,snapshot){
  const users=(snapshot?.roster||[]).filter(x=>x&&x.active!==false),baseline=Object.fromEntries((analytics?.historyActive||[]).map(x=>[String(x.id),x]));
  const today=trainLocalISO(),cutoff=String(snapshot?.state?.manualHistory?.cutoff||'0000-00-00'),schedule=Array.isArray(snapshot?.schedule)?snapshot.schedule:[];
  return users.map(u=>{
    const b=baseline[String(u.id)]||{driver:0,driverLast:null,vip:0,vipLast:null};
    const past=schedule.filter(x=>x?.date>cutoff&&x.date<today),pd=past.filter(x=>String(x.driverId||'')===String(u.id)),pv=past.filter(x=>String(x.vipId||'')===String(u.id));
    const nd=schedule.find(x=>x?.date>=today&&String(x.driverId||'')===String(u.id)),nv=schedule.find(x=>x?.date>=today&&String(x.vipId||'')===String(u.id));
    const rank=String(u.rank||'').toUpperCase(),driverRole=nd?.driverClass==='officer'||['R4','R5'].includes(rank)?'A':'B';
    return {id:u.id,pseudo:u.pseudo,rank,driver:Number(b.driver||0)+pd.length,driverLast:pd.length?pd[pd.length-1].date:b.driverLast,driverNext:nd?.date||null,driverRole,vip:Number(b.vip||0)+pv.length,vipLast:pv.length?pv[pv.length-1].date:b.vipLast,vipNext:nv?.date||null};
  }).sort((a,b)=>({R5:1,R4:2,R3:3,R2:4,R1:5}[a.rank]||9)-({R5:1,R4:2,R3:3,R2:4,R1:5}[b.rank]||9)||String(a.pseudo).localeCompare(String(b.pseudo)));
}
'''
portal = portal.replace(anchor, helper_block + '\n' + anchor, 1)

portal = replace_once(
    portal,
    "  refreshModuleLinks();\n}",
    "  refreshModuleLinks();\n  renderHomeTrainRotationCard();\n  if(!state.trainRotationLoading)loadHomeTrainRotation();\n}",
    'Portal renderHome train card'
)

# Update portal player-statistics copy in four languages.
replacements = {
"statsDesc:'Activité des joueurs sur les 30 derniers jours. Les statistiques de rotations restent dans Train.'":"statsDesc:'Activité des joueurs sur les 30 derniers jours et synthèse des rotations issue de Train.'",
"statsDesc:'Attività dei giocatori negli ultimi 30 giorni. Le statistiche delle rotazioni restano in Treno.'":"statsDesc:'Attività dei giocatori negli ultimi 30 giorni e sintesi delle rotazioni proveniente dal Treno.'",
"statsDesc:'Player activity over the last 30 days. Rotation statistics remain in Train.'":"statsDesc:'Player activity over the last 30 days and a rotation summary read from Train.'",
"statsDesc:'Actividad de jugadores durante los últimos 30 días. Las estadísticas de rotación permanecen en Tren.'":"statsDesc:'Actividad de jugadores durante los últimos 30 días y resumen de rotaciones leído del Tren.'"
}
for old,new in replacements.items():
    portal = replace_once(portal, old, new, f'Portal stats description {old[:20]}')

old_loader = """    const d=await trainAdminApi('/api/admin/analytics',{method:'GET'}),s=d.summary||{};\n    const rows=[...(d.activityByActor||[])].sort((a,b)=>(b.total||0)-(a.total||0)||String(a.pseudo||'').localeCompare(String(b.pseudo||'')));\n    if(!$('playerStatsHost'))return;\n    host.innerHTML=`<div class=\"portal-stats-kpis\"><div><small>${esc(x.actions7)}</small><strong>${s.actions7||0}</strong></div><div><small>${esc(x.actions30)}</small><strong>${s.actions30||0}</strong></div><div><small>${esc(x.active)}</small><strong>${s.activeMembers||0}</strong></div></div><div class=\"portal-player-stats-list\">${rows.length?rows.map(row=>`<div class=\"portal-player-stat-row\"><div class=\"portal-stat-avatar\">${esc(initials(row.pseudo||'?'))}</div><div class=\"portal-stat-main\"><b>${esc(row.pseudo||'—')}</b><small>${esc(row.rank||'')} · ${row.total||0} ${esc(x.actions)}</small><div class=\"portal-stat-breakdown\"><span>👤 ${esc(x.profile)} ${row.players||0}</span><span>🔄 ${esc(x.exchanges)} ${row.exchanges||0}</span><span>👥 ${esc(x.members)} ${row.members||0}</span><span>⚙️ ${esc(x.settings)} ${row.settings||0}</span></div></div><strong class=\"portal-stat-total\">${row.total||0}</strong></div>`).join(''):`<div class=\"empty-state\">${esc(x.empty)}</div>`}</div>`;"""
new_loader = """    const [d,snapshot]=await Promise.all([trainAdminApi('/api/admin/analytics',{method:'GET'}),trainAdminApi('/api/snapshot',{method:'GET'})]),s=d.summary||{};\n    const rows=[...(d.activityByActor||[])].sort((a,b)=>(b.total||0)-(a.total||0)||String(a.pseudo||'').localeCompare(String(b.pseudo||'')));\n    const rotations=buildPlayerRotationRows(d,snapshot),rx=trainRotationLabels();\n    if(!$('playerStatsHost'))return;\n    host.innerHTML=`<div class=\"portal-stats-kpis\"><div><small>${esc(x.actions7)}</small><strong>${s.actions7||0}</strong></div><div><small>${esc(x.actions30)}</small><strong>${s.actions30||0}</strong></div><div><small>${esc(x.active)}</small><strong>${s.activeMembers||0}</strong></div></div><div class=\"portal-player-stats-list\">${rows.length?rows.map(row=>`<div class=\"portal-player-stat-row\"><div class=\"portal-stat-avatar\">${esc(initials(row.pseudo||'?'))}</div><div class=\"portal-stat-main\"><b>${esc(row.pseudo||'—')}</b><small>${esc(row.rank||'')} · ${row.total||0} ${esc(x.actions)}</small><div class=\"portal-stat-breakdown\"><span>👤 ${esc(x.profile)} ${row.players||0}</span><span>🔄 ${esc(x.exchanges)} ${row.exchanges||0}</span><span>👥 ${esc(x.members)} ${row.members||0}</span><span>⚙️ ${esc(x.settings)} ${row.settings||0}</span></div></div><strong class=\"portal-stat-total\">${row.total||0}</strong></div>`).join(''):`<div class=\"empty-state\">${esc(x.empty)}</div>`}</div><div class=\"section-heading\" style=\"margin-top:22px\"><div><h3>🚂 ${esc(rx.statsTitle)}</h3><p class=\"muted\">${esc(rx.statsDesc)}</p></div></div><div class=\"portal-player-stats-list\">${rotations.map(r=>{const dl=r.driverRole==='A'?rx.driverA:rx.driverB;return `<div class=\"portal-player-stat-row\"><div class=\"portal-stat-avatar\">${esc(initials(r.pseudo||'?'))}</div><div class=\"portal-stat-main\"><b>${esc(r.pseudo||'—')}</b><small>${esc(r.rank||'')}</small><div class=\"portal-stat-breakdown\"><span>🚂 ${esc(dl)} : <b>${r.driver||0}</b> · ${esc(rx.last)} ${esc(trainDateLabel(r.driverLast))} · ${esc(rx.next)} ${esc(trainDateLabel(r.driverNext))}</span><span>⭐ ${esc(rx.vip)} : <b>${r.vip||0}</b> · ${esc(rx.last)} ${esc(trainDateLabel(r.vipLast))} · ${esc(rx.next)} ${esc(trainDateLabel(r.vipNext))}</span></div></div></div>`}).join('')}</div>`;"""
portal = replace_once(portal, old_loader, new_loader, 'Portal player statistics rotation subsection')

portal_path.write_text(portal, encoding='utf-8')
print('WFGG_ROTATION_ROUNDS_V2_UI=PATCHED')
