from pathlib import Path
import re

worker_path = Path('frontend/_worker.js')
portal_js_path = Path('frontend/portal-v070.js')
portal_css_path = Path('frontend/portal-v070.css')

worker = worker_path.read_text(encoding='utf-8')
portal = portal_js_path.read_text(encoding='utf-8')
css = portal_css_path.read_text(encoding='utf-8')

# ---------------------------------------------------------------------------
# Train: native vector logo + clear ownership boundary for administration.
# ---------------------------------------------------------------------------
if 'WFGG_TRAIN_VECTOR_LOGO_V1' not in worker:
    anchor = "      /* WFGG_TRAIN_RELATIVE_APP_CACHE_BUST_V1"
    block = """      /* WFGG_TRAIN_VECTOR_LOGO_V1
         Le Train intégré réutilise le logo vectoriel du Portail au lieu de
         l'ancien PNG historique. Le lien brandHome conserve son rôle de retour
         vers l'accueil général WfGg.
      */
      if (
        this.prefix === '/train' &&
        attr === 'src' &&
        /^(?:\\.\\/)?assets\\/wfgg-logo\\.png(?:[?#]|$)/i.test(value)
      ) {
        element.setAttribute(attr, '/assets/wfgg-logo-vector.svg');
        continue;
      }

"""
    if anchor not in worker:
        raise SystemExit('missing Train relative asset anchor')
    worker = worker.replace(anchor, block + anchor, 1)

if 'WFGG_TRAIN_ADMIN_OWNERSHIP_V1' not in worker:
    anchor = "    /* WFGG_TRAIN_INIT_DOM_GUARD_V1"
    block = r'''    /* WFGG_TRAIN_ADMIN_OWNERSHIP_V1
       Le Portail est l'unique propriétaire de l'identité alliance : joueurs,
       codes d'accès, activité des joueurs, page d'accueil et ressources
       globales. Train ne conserve que les réglages et statistiques propres au
       train (messages, horaires, rotations, planning, équité, historique).
    */
    rewritten = rewritten.replace(
      /\n\s*<button class="admin-menu-card (?:players|access|portal|help)"[\s\S]*?<\/button>/g,
      ''
    );
    rewritten = rewritten.replace(
      /\n\s*<button class="analytics-icon-card (?:activity|settings|history)"[\s\S]*?<\/button>/g,
      ''
    );
    rewritten = rewritten
      .replaceAll('Statistiques & historique', 'Statistiques du train')
      .replaceAll(
        'Rotations, activité des joueurs et journal des changements',
        'Rotations, équité et historique des passages'
      );

'''
    if anchor not in worker:
        raise SystemExit('missing Train DOM guard anchor')
    worker = worker.replace(anchor, block + anchor, 1)

worker = worker.replace('wfgg_bridge=v9', 'wfgg_bridge=v10')
worker = worker.replace("wfgg_fresh','v9'", "wfgg_fresh','v10'")

# ---------------------------------------------------------------------------
# Portal: dedicated Players & Access + Player Statistics administration tabs.
# ---------------------------------------------------------------------------
if 'WFGG_PORTAL_TRAIN_ADMIN_API_V1' not in portal:
    anchor = 'function clearSession()'
    block = """const PORTAL_TRAIN_ADMIN_API='https://portal-auth-phase1-wfgg-train.chachasan090375.workers.dev';
/* WFGG_PORTAL_TRAIN_ADMIN_API_V1
   Les données d'activité restent produites par Train, mais leur administration
   appartient au Portail. Le token Portail est envoyé uniquement par header.
*/
async function trainAdminApi(path,options={}){
  const h=new Headers(options.headers||{}),tk=token();
  if(!tk)throw new Error('NO_PORTAL_SESSION');
  h.set('X-WfGg-Portal-Token',tk);
  if(options.body&&!h.has('Content-Type'))h.set('Content-Type','application/json');
  const r=await fetch(`${PORTAL_TRAIN_ADMIN_API}${path}`,{...options,headers:h,cache:'no-store',credentials:'omit',mode:'cors'});
  let d=null;try{d=await r.json()}catch{}
  if(!r.ok)throw new Error(d?.error||`HTTP_${r.status}`);
  return d;
}
"""
    if anchor not in portal:
        raise SystemExit('missing portal clearSession anchor')
    portal = portal.replace(anchor, block + anchor, 1)

portal = re.sub(
    r"const tabDefs=\(\)=>[^\n]+;",
    "const tabDefs=()=>[{id:'profile',label:t('settings.profile')},...(isAdmin()?[{id:'alliance',label:t('settings.alliance')},{id:'members',label:portalAdminLabels().membersTab},{id:'statistics',label:portalAdminLabels().statsTab},{id:'application',label:t('settings.application')},{id:'rights',label:t('settings.rights')}]:[])];",
    portal,
    count=1,
)

portal = re.sub(
    r"function renderSettingsContent\(\)\{[^\n]+\}",
    "function renderSettingsContent(){const c=$('settingsContent');if(state.settingsTab==='profile')c.innerHTML=profileSettingsHtml();else if(state.settingsTab==='alliance'&&isAdmin())c.innerHTML=allianceSettingsHtml();else if(state.settingsTab==='members'&&isAdmin())c.innerHTML=membersSettingsHtml();else if(state.settingsTab==='statistics'&&isAdmin())c.innerHTML=playerStatisticsHtml();else if(state.settingsTab==='application'&&isAdmin())c.innerHTML=applicationSettingsHtml();else if(state.settingsTab==='rights'&&isAdmin())c.innerHTML=rightsHtml();else{state.settingsTab='profile';c.innerHTML=profileSettingsHtml()}bindSettingsForms();}",
    portal,
    count=1,
)

# Alliance tab now only contains alliance identity settings.
portal = re.sub(
    r"function allianceSettingsHtml\(\)\{.*?\}\nfunction applicationSettingsHtml",
    "function allianceSettingsHtml(){return `<div class=\"settings-section\"><form id=\"allianceForm\" class=\"settings-form\"><div class=\"settings-card-block\"><h3>🏰 Alliance</h3><label class=\"field-label\">Nom</label><input id=\"allianceName\" maxlength=\"50\" value=\"${esc(state.alliance?.name||'')}\"><label class=\"field-label\">Serveur</label><input id=\"allianceServer\" maxlength=\"30\" value=\"${esc(state.alliance?.server||'')}\"><label class=\"field-label\">Logo (URL)</label><input id=\"allianceLogo\" maxlength=\"500\" value=\"${esc(state.alliance?.logo_url||'')}\"><button class=\"primary-button\" type=\"submit\">${esc(t('settings.save'))}</button><div id=\"allianceMessage\" class=\"hidden\"></div></div></form></div>`}\nfunction applicationSettingsHtml",
    portal,
    count=1,
    flags=re.S,
)

if 'WFGG_PORTAL_PLAYER_STATS_V1' not in portal:
    anchor = 'function applicationSettingsHtml'
    block = """/* WFGG_PORTAL_PLAYER_STATS_V1 */
function portalAdminLabels(){
  const all={
    fr:{membersTab:'Joueurs & accès',statsTab:'Statistiques joueurs',membersTitle:'Joueurs & accès',membersDesc:'Profils, rangs, fonctions R4, activation et réinitialisation des codes.',manage:'Gérer les joueurs',statsTitle:'Statistiques joueurs',statsDesc:'Activité des joueurs sur les 30 derniers jours. Les statistiques de rotations restent dans Train.',refresh:'Actualiser',loading:'Chargement…',empty:'Aucune activité enregistrée sur cette période.',actions7:'Actions · 7 j',actions30:'Actions · 30 j',active:'Joueurs actifs',actions:'actions',profile:'Profil',exchanges:'Échanges',members:'Admin joueurs',settings:'Réglages'},
    it:{membersTab:'Giocatori e accessi',statsTab:'Statistiche giocatori',membersTitle:'Giocatori e accessi',membersDesc:'Profili, gradi, funzioni R4, attivazione e reimpostazione dei codici.',manage:'Gestisci giocatori',statsTitle:'Statistiche giocatori',statsDesc:'Attività dei giocatori negli ultimi 30 giorni. Le statistiche delle rotazioni restano in Treno.',refresh:'Aggiorna',loading:'Caricamento…',empty:'Nessuna attività registrata in questo periodo.',actions7:'Azioni · 7 g',actions30:'Azioni · 30 g',active:'Giocatori attivi',actions:'azioni',profile:'Profilo',exchanges:'Scambi',members:'Admin giocatori',settings:'Impostazioni'},
    en:{membersTab:'Players & access',statsTab:'Player statistics',membersTitle:'Players & access',membersDesc:'Profiles, ranks, R4 roles, activation and access-code resets.',manage:'Manage players',statsTitle:'Player statistics',statsDesc:'Player activity over the last 30 days. Rotation statistics remain in Train.',refresh:'Refresh',loading:'Loading…',empty:'No activity recorded in this period.',actions7:'Actions · 7d',actions30:'Actions · 30d',active:'Active players',actions:'actions',profile:'Profile',exchanges:'Swaps',members:'Player admin',settings:'Settings'},
    es:{membersTab:'Jugadores y accesos',statsTab:'Estadísticas jugadores',membersTitle:'Jugadores y accesos',membersDesc:'Perfiles, rangos, funciones R4, activación y restablecimiento de códigos.',manage:'Gestionar jugadores',statsTitle:'Estadísticas jugadores',statsDesc:'Actividad de jugadores durante los últimos 30 días. Las estadísticas de rotación permanecen en Tren.',refresh:'Actualizar',loading:'Cargando…',empty:'No hay actividad registrada en este período.',actions7:'Acciones · 7 d',actions30:'Acciones · 30 d',active:'Jugadores activos',actions:'acciones',profile:'Perfil',exchanges:'Intercambios',members:'Admin jugadores',settings:'Ajustes'}
  };
  return all[state.lang]||all.fr;
}
function membersSettingsHtml(){const x=portalAdminLabels();return `<div class=\"settings-section\"><div class=\"settings-card-block\"><div class=\"section-heading\"><div><h3>👥 ${esc(x.membersTitle)}</h3><p class=\"muted\">${esc(x.membersDesc)}</p></div><button id=\"openMembersButton\" class=\"primary-button\" type=\"button\">${esc(x.manage)}</button></div></div></div>`}
function playerStatisticsHtml(){const x=portalAdminLabels();return `<div class=\"settings-section\"><div class=\"settings-card-block\"><div class=\"section-heading\"><div><h3>📊 ${esc(x.statsTitle)}</h3><p class=\"muted\">${esc(x.statsDesc)}</p></div><button id=\"refreshPlayerStats\" class=\"secondary-button\" type=\"button\">${esc(x.refresh)}</button></div><div id=\"playerStatsHost\" class=\"portal-player-stats\"><span class=\"muted\">${esc(x.loading)}</span></div></div></div>`}
async function loadPlayerStatistics(){
  const host=$('playerStatsHost');if(!host||!isAdmin())return;
  const x=portalAdminLabels();host.innerHTML=`<span class=\"muted\">${esc(x.loading)}</span>`;
  try{
    const d=await trainAdminApi('/api/admin/analytics',{method:'GET'}),s=d.summary||{};
    const rows=[...(d.activityByActor||[])].sort((a,b)=>(b.total||0)-(a.total||0)||String(a.pseudo||'').localeCompare(String(b.pseudo||'')));
    if(!$('playerStatsHost'))return;
    host.innerHTML=`<div class=\"portal-stats-kpis\"><div><small>${esc(x.actions7)}</small><strong>${s.actions7||0}</strong></div><div><small>${esc(x.actions30)}</small><strong>${s.actions30||0}</strong></div><div><small>${esc(x.active)}</small><strong>${s.activeMembers||0}</strong></div></div><div class=\"portal-player-stats-list\">${rows.length?rows.map(row=>`<div class=\"portal-player-stat-row\"><div class=\"portal-stat-avatar\">${esc(initials(row.pseudo||'?'))}</div><div class=\"portal-stat-main\"><b>${esc(row.pseudo||'—')}</b><small>${esc(row.rank||'')} · ${row.total||0} ${esc(x.actions)}</small><div class=\"portal-stat-breakdown\"><span>👤 ${esc(x.profile)} ${row.players||0}</span><span>🔄 ${esc(x.exchanges)} ${row.exchanges||0}</span><span>👥 ${esc(x.members)} ${row.members||0}</span><span>⚙️ ${esc(x.settings)} ${row.settings||0}</span></div></div><strong class=\"portal-stat-total\">${row.total||0}</strong></div>`).join(''):`<div class=\"empty-state\">${esc(x.empty)}</div>`}</div>`;
  }catch(error){if($('playerStatsHost'))host.innerHTML=`<div class=\"form-message error\">${esc(error.message)}</div>`;}
}
"""
    if anchor not in portal:
        raise SystemExit('missing portal application settings anchor')
    portal = portal.replace(anchor, block + anchor, 1)

portal = re.sub(
    r"function bindSettingsForms\(\)\{[^\n]+\}",
    "function bindSettingsForms(){paintAvatar($('settingsAvatar'),state.user);if($('languageSelect'))$('languageSelect').value=state.user?.language||state.lang;$('profileForm')?.addEventListener('submit',saveProfile);$('avatarInput')?.addEventListener('change',uploadAvatar);$('codeForm')?.addEventListener('submit',changeOwnCode);$('refreshSessions')?.addEventListener('click',loadSessions);$('allianceForm')?.addEventListener('submit',saveAlliance);$('applicationForm')?.addEventListener('submit',saveApplication);$('openMembersButton')?.addEventListener('click',openMembers);$('refreshPlayerStats')?.addEventListener('click',loadPlayerStatistics);if(state.settingsTab==='profile')loadSessions();if(state.settingsTab==='statistics')loadPlayerStatistics();}",
    portal,
    count=1,
)

# ---------------------------------------------------------------------------
# Portal styles for the new player statistics ownership tab.
# ---------------------------------------------------------------------------
if 'WFGG_PORTAL_PLAYER_STATS_STYLE_V1' not in css:
    css += r'''

/* WFGG_PORTAL_PLAYER_STATS_STYLE_V1 */
.portal-player-stats{display:grid;gap:14px;margin-top:16px}.portal-stats-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.portal-stats-kpis>div{display:grid;gap:4px;padding:12px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.03)}.portal-stats-kpis small{color:var(--muted);font-size:11px}.portal-stats-kpis strong{font-size:24px}.portal-player-stats-list{display:grid;gap:8px}.portal-player-stat-row{display:grid;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:10px;padding:10px 11px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.025)}.portal-stat-avatar{width:42px;height:42px;border-radius:11px;display:grid;place-items:center;background:var(--accent-soft);border:1px solid rgba(178,150,255,.25);font-weight:900}.portal-stat-main{min-width:0;display:grid;gap:3px}.portal-stat-main>b{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.portal-stat-main>small{color:var(--muted);font-size:12px}.portal-stat-breakdown{display:flex;gap:6px;flex-wrap:wrap;margin-top:3px}.portal-stat-breakdown span{font-size:10px;color:#d7cdea;background:rgba(255,255,255,.045);border-radius:999px;padding:3px 6px}.portal-stat-total{font-size:20px;color:var(--accent2)}
@media(max-width:560px){.portal-stats-kpis{grid-template-columns:1fr 1fr}.portal-player-stat-row{grid-template-columns:38px minmax(0,1fr) auto}.portal-stat-avatar{width:38px;height:38px}.portal-stat-breakdown{gap:4px}.portal-stat-breakdown span{font-size:9px}}
'''

worker_path.write_text(worker, encoding='utf-8')
portal_js_path.write_text(portal, encoding='utf-8')
portal_css_path.write_text(css, encoding='utf-8')

print('PORTAL_TRAIN_ARCHITECTURE_FIX=OK')
print('VECTOR_LOGO=', 'WFGG_TRAIN_VECTOR_LOGO_V1' in worker)
print('TRAIN_OWNERSHIP=', 'WFGG_TRAIN_ADMIN_OWNERSHIP_V1' in worker)
print('PORTAL_STATS=', 'WFGG_PORTAL_PLAYER_STATS_V1' in portal)
