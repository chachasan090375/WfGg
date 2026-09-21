#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
TRANSPORT = ROOT / 'src/game/remote-transport.js'
WORKER = ROOT / 'src/worker.js'
UI = ROOT / 'public/live-radar.html'

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)

transport = TRANSPORT.read_text(encoding='utf-8')
if 'WFGG_RADAR_PLAYER_INTELLIGENCE_TRANSPORT_V620' not in transport:
    anchor = "  cartographerTick(token) { return this.request('/v1/cartographer/tick', { body: { token } }); }\n"
    addition = """  // WFGG_RADAR_PLAYER_INTELLIGENCE_TRANSPORT_V620
  collectorPlayerIntelligence(filters = {}) {
    return this.request('/v1/collector/intelligence/search', { body: filters || {} });
  }
"""
    transport = replace_once(transport, anchor, addition + anchor, 'V620 transport anchor')
TRANSPORT.write_text(transport, encoding='utf-8')

worker = WORKER.read_text(encoding='utf-8')
if 'WFGG_RADAR_PLAYER_INTELLIGENCE_WORKER_V620' not in worker:
    anchor = "      // WFGG_RADAR_RICH_PROFILE_WORKER_V6191\n"
    route = r'''      // WFGG_RADAR_PLAYER_INTELLIGENCE_WORKER_V620
      if (url.pathname === '/api/radar/intelligence/search' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const filters = await request.json().catch(() => null);
        if (!filters || typeof filters !== 'object' || Array.isArray(filters)) {
          throw Object.assign(new Error('PLAYER_INTELLIGENCE_REQUEST_INVALID_V620'), { status: 400 });
        }
        const transport = new RemoteLastWarTransport({
          baseUrl: env.RADAR_CONNECTOR_URL,
          sharedKey: env.RADAR_CONNECTOR_SHARED_KEY,
          timeoutMs: 30000
        });
        try {
          const result = await transport.collectorPlayerIntelligence(filters);
          return json({ ...result, gameReadonly: true, gameMutation: false, tokenUsed: false });
        } finally {
          await transport.close().catch(() => {});
        }
      }

'''
    worker = replace_once(worker, anchor, route + anchor, 'V620 worker route anchor')
WORKER.write_text(worker, encoding='utf-8')

ui = UI.read_text(encoding='utf-8')
if 'WFGG_RADAR_PLAYER_INTELLIGENCE_UI_V620' not in ui:
    css = r'''
/* WFGG_RADAR_PLAYER_INTELLIGENCE_UI_V620 */
.controls{display:grid!important;grid-template-columns:minmax(0,1fr) auto auto!important;gap:8px!important}
.filterbtn{border:1px solid #6e8339;border-radius:12px;background:linear-gradient(#2b3a18,#15210d);color:#d8f09b;font:900 10px ui-monospace,monospace;letter-spacing:.06em;padding:0 12px;min-height:52px}
.filterbtn.active{background:linear-gradient(#b7dc4f,#78972c);color:#101806;box-shadow:0 0 16px #b8e14b44}
.intel-overlay{position:fixed;inset:0;z-index:5000;background:#000c;display:none;align-items:flex-end;justify-content:center;padding:12px}
.intel-overlay.show{display:flex}
.intel-modal{width:min(680px,100%);max-height:88vh;overflow:auto;background:linear-gradient(180deg,#10190d,#071006);border:1px solid #63773b;border-radius:20px 20px 12px 12px;box-shadow:0 22px 70px #000;padding:14px;color:#d9e8c8}
.intel-head{position:sticky;top:-14px;z-index:2;background:#0c1509ee;backdrop-filter:blur(8px);display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 4px;border-bottom:1px solid #34462a}
.intel-title{font:900 13px ui-monospace,monospace;color:#c7f3a6;letter-spacing:.05em}
.intel-close{border:1px solid #687842;background:#17220e;color:#d9eca9;border-radius:10px;padding:8px 12px;font-weight:900}
.intel-summary{font:11px ui-monospace,monospace;color:#94aa87;padding:10px 2px}
.intel-list{display:grid;gap:8px}
.intel-card{display:grid;grid-template-columns:48px minmax(0,1fr) auto;gap:10px;align-items:center;border:1px solid #36492b;border-radius:14px;background:#0a1208;padding:10px;text-align:left;color:#dfead6;width:100%}
.intel-card:active{transform:scale(.99);background:#111d0d}
.intel-avatar{width:48px;height:48px;border-radius:50%;object-fit:cover;border:1px solid #71854c;background:#18220f;display:grid;place-items:center;font:900 15px ui-monospace,monospace;color:#cbea85}
.intel-name{font:900 13px ui-monospace,monospace;color:#dfffb6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.intel-meta,.intel-sub{font:10px ui-monospace,monospace;color:#8fa787;margin-top:3px}
.intel-power{font:900 11px ui-monospace,monospace;color:#d8ef81;text-align:right}
.filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.filter-field{display:grid;gap:5px}.filter-field.wide{grid-column:1/-1}
.filter-field label{font:900 9px ui-monospace,monospace;color:#91a87c;letter-spacing:.05em}
.filter-field input,.filter-field select{width:100%;box-sizing:border-box;border:1px solid #425832;border-radius:10px;background:#071006;color:#dcebcf;padding:10px;font:11px ui-monospace,monospace}
.filter-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}
.filter-actions button{border:1px solid #63783b;border-radius:11px;background:#14200d;color:#d8ed9f;padding:11px;font:900 10px ui-monospace,monospace}
.filter-actions .primary{background:linear-gradient(#b7dc4f,#718c29);color:#101806}
.preset-fr{grid-column:1/-1;border-color:#496c8b!important;background:#0e1b25!important;color:#b9ddff!important}
.filter-note{font:9px ui-monospace,monospace;color:#71806c;margin-top:10px;line-height:1.45}
@media(max-width:520px){.controls{grid-template-columns:minmax(0,1fr) auto!important}.filterbtn{grid-column:1/-1;min-height:42px}.filter-grid{grid-template-columns:1fr}.filter-field.wide{grid-column:auto}.intel-overlay{padding:6px}.intel-modal{max-height:92vh}}
'''
    ui = replace_once(ui, '</style>', css + '\n</style>', 'V620 UI css')

    form_old = '''      <button id="go" class="go" type="submit">RECHERCHER</button>
    </form>'''
    form_new = '''      <button id="go" class="go" type="submit">RECHERCHER</button>
      <button id="filterButton" class="filterbtn" type="button">FILTRES</button>
    </form>'''
    ui = replace_once(ui, form_old, form_new, 'V620 filter button')

    ui = replace_once(ui, 'AUTOPILOT V6.19.17 · ARRÊTÉ', 'AUTOPILOT V6.20.0 · ARRÊTÉ', 'V620 UI version')

    uid_field = '<div class="field"><div class="k">UID</div><div id="ruid" class="v">—</div></div>'
    ui = replace_once(ui, uid_field, uid_field + '<div class="field"><div class="k">ANCIENS PSEUDOS</div><div id="raliases" class="v">—</div></div>', 'V620 alias field')

    overlay_anchor = '</div>\n<script>'
    overlays = r'''</div>
<div id="intelOverlay" class="intel-overlay" aria-hidden="true">
  <div class="intel-modal" role="dialog" aria-modal="true" aria-labelledby="intelTitle">
    <div class="intel-head"><div id="intelTitle" class="intel-title">RÉSULTATS JOUEURS</div><button id="intelClose" class="intel-close" type="button">FERMER</button></div>
    <div id="intelSummary" class="intel-summary"></div><div id="intelList" class="intel-list"></div>
  </div>
</div>
<div id="filterOverlay" class="intel-overlay" aria-hidden="true">
  <div class="intel-modal" role="dialog" aria-modal="true" aria-labelledby="filterTitle">
    <div class="intel-head"><div id="filterTitle" class="intel-title">FILTRES DE RECRUTEMENT</div><button id="filterClose" class="intel-close" type="button">FERMER</button></div>
    <div class="filter-grid">
      <div class="filter-field"><label>PAYS (champ Last War)</label><input id="fCountry" placeholder="FR"></div>
      <div class="filter-field"><label>ALLIANCE À INCLURE</label><input id="fAlliance" placeholder="Tag ou ID"></div>
      <div class="filter-field wide"><label>SERVEUR(S) À INCLURE</label><input id="fServers" placeholder="8117, 8118, 8120"></div>
      <div class="filter-field wide"><label>SERVEUR(S) À EXCLURE</label><input id="fExcludeServers" placeholder="8121, 8122"></div>
      <div class="filter-field wide"><label>ALLIANCE(S) À EXCLURE</label><input id="fExcludeAlliances" placeholder="WFGG, ABC, XYZ"></div>
      <div class="filter-field wide"><label>JOUEUR(S) À EXCLURE</label><input id="fExcludePlayers" placeholder="Pseudo ou UID, séparés par virgule"></div>
      <div class="filter-field"><label>PUISSANCE MIN</label><input id="fMinPower" inputmode="numeric" placeholder="100000000"></div>
      <div class="filter-field"><label>PUISSANCE MAX</label><input id="fMaxPower" inputmode="numeric" placeholder="300000000"></div>
      <div class="filter-field"><label>HQ MIN</label><input id="fMinHQ" inputmode="numeric" placeholder="28"></div>
      <div class="filter-field"><label>HQ MAX</label><input id="fMaxHQ" inputmode="numeric" placeholder="31"></div>
      <div class="filter-field"><label>OBSERVÉ DEPUIS MOINS DE (J)</label><input id="fWithinDays" inputmode="numeric" placeholder="7"></div>
      <div class="filter-field"><label>NON OBSERVÉ DEPUIS AU MOINS (J)</label><input id="fOlderDays" inputmode="numeric" placeholder="30"></div>
      <div class="filter-field"><label>ARMY POWER MIN</label><input id="fMinArmyPower" inputmode="numeric" placeholder="si disponible"></div>
      <div class="filter-field"><label>KILLS MIN</label><input id="fMinKills" inputmode="numeric" placeholder="si disponible"></div>
      <div class="filter-field"><label>SVIP MIN</label><input id="fMinSVIP" inputmode="numeric" placeholder="si disponible"></div>
      <div class="filter-field"><label>TRI</label><select id="fSort"><option value="power_desc">Puissance ↓</option><option value="hq_desc">HQ ↓</option><option value="observed_desc">Dernière observation ↓</option><option value="army_desc">Army Power ↓</option><option value="kills_desc">Kills ↓</option><option value="pseudo_asc">Pseudo A→Z</option></select></div>
    </div>
    <div class="filter-actions"><button id="filterPresetFR" class="preset-fr" type="button">🇫🇷 PRESET RECRUTEMENT FR</button><button id="filterClear" type="button">EFFACER</button><button id="filterApply" class="primary" type="button">APPLIQUER</button></div>
    <div class="filter-note">« Activité » = dernière observation Radar, pas dernière connexion Last War. Les champs Army Power, kills, SVIP, pays et avatar ne sont utilisés que s’ils existent réellement dans le Collector.</div>
  </div>
</div>
<script>'''
    ui = replace_once(ui, overlay_anchor, overlays, 'V620 overlays')

    alias_js_anchor = "$('ruid').textContent=fmt(uid);"
    ui = replace_once(ui, alias_js_anchor, alias_js_anchor + "const aliases=Array.isArray(p.aliases)?p.aliases:[];$('raliases').textContent=aliases.length?aliases.join(' · '):'—';", 'V620 aliases JS')

    source_old = "fast?.status==='fuzzy-hit'?'INDEX COLLECTOR':'RADAR'"
    if source_old in ui:
        ui = ui.replace(source_old, "fast?.status==='intelligence'?'PLAYER INTEL':fast?.status==='fuzzy-hit'?'INDEX COLLECTOR':'RADAR'", 1)

    api_old = "String(path).startsWith('/api/radar/search?')"
    if api_old in ui:
        ui = ui.replace(api_old, "(String(path).startsWith('/api/radar/search?')||String(path)==='/api/radar/intelligence/search')", 1)

    js_anchor = 'async function api(path,opt={})'
    js_pos = ui.find(js_anchor)
    if js_pos < 0:
        raise SystemExit('V620 intelligence JS anchor missing')
    intelligence_js = r'''
/* WFGG_RADAR_PLAYER_INTELLIGENCE_UI_V620 */
let intelligenceFilters={},intelligenceCapabilities={},intelSuggestTimer=null;
const intelCSV=v=>String(v||'').split(',').map(x=>x.trim()).filter(Boolean);
const intelNumber=v=>{const s=String(v==null?'':v).trim();if(!s)return null;const n=Number(s.replace(/\s/g,''));return Number.isFinite(n)?Math.trunc(n):null};
function intelOpen(id){const e=$(id);if(e){e.classList.add('show');e.setAttribute('aria-hidden','false')}}
function intelClose(id){const e=$(id);if(e){e.classList.remove('show');e.setAttribute('aria-hidden','true')}}
function activeIntelFilterCount(){return Object.entries(intelligenceFilters).filter(x=>x[0]!=='sort'&&((Array.isArray(x[1])&&x[1].length)||(!Array.isArray(x[1])&&x[1]!==null&&x[1]!==undefined&&x[1]!==''))).length}
function updateFilterBadge(){const n=activeIntelFilterCount(),b=$('filterButton');if(!b)return;b.textContent=n?'FILTRES · '+n:'FILTRES';b.classList.toggle('active',n>0)}
function filtersFromUI(){return{country:$('fCountry').value.trim(),alliance:$('fAlliance').value.trim(),servers:intelCSV($('fServers').value),excludeServers:intelCSV($('fExcludeServers').value),excludeAlliances:intelCSV($('fExcludeAlliances').value),excludePlayers:intelCSV($('fExcludePlayers').value),minPower:intelNumber($('fMinPower').value),maxPower:intelNumber($('fMaxPower').value),minHQ:intelNumber($('fMinHQ').value),maxHQ:intelNumber($('fMaxHQ').value),observedWithinDays:intelNumber($('fWithinDays').value),observedOlderDays:intelNumber($('fOlderDays').value),minArmyPower:intelNumber($('fMinArmyPower').value),minKills:intelNumber($('fMinKills').value),minSVIP:intelNumber($('fMinSVIP').value),sort:$('fSort').value||'power_desc'}}
function clearFilterUI(){for(const id of ['fCountry','fAlliance','fServers','fExcludeServers','fExcludeAlliances','fExcludePlayers','fMinPower','fMaxPower','fMinHQ','fMaxHQ','fWithinDays','fOlderDays','fMinArmyPower','fMinKills','fMinSVIP'])$(id).value='';$('fSort').value='power_desc'}
function applyIntelCapabilities(caps){intelligenceCapabilities=caps||{};for(const pair of [['fCountry','country'],['fWithinDays','lastSeen'],['fOlderDays','lastSeen'],['fMinArmyPower','armyPower'],['fMinKills','kills'],['fMinSVIP','svip']]){const e=$(pair[0]),key=pair[1];if(e&&Object.prototype.hasOwnProperty.call(intelligenceCapabilities,key)){e.disabled=!intelligenceCapabilities[key];e.title=intelligenceCapabilities[key]?'':'Champ absent du Collector actuel'}}}
async function intelligenceSearch(query,extra){const payload=Object.assign({query:String(query||'').trim(),limit:50,offset:0},intelligenceFilters,extra||{});const d=await api('/api/radar/intelligence/search',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});applyIntelCapabilities(d&&d.capabilities||{});return d}
function intelAvatarNode(p){const ref=String(p&&p.avatarRef||'').trim();if(/^https?:\/\//i.test(ref)){const img=document.createElement('img');img.className='intel-avatar';img.alt='';img.src=ref;return img}const d=document.createElement('div');d.className='intel-avatar';d.textContent=String(p&&p.pseudo||'?').trim().slice(0,2).toUpperCase()||'?';return d}
function renderIntelligenceResults(d,query){const list=$('intelList');list.replaceChildren();const players=Array.isArray(d&&d.players)?d.players:[],alls=Array.isArray(d&&d.alliances)?d.alliances:[],alliance=alls.length===1?alls[0]:null;$('intelTitle').textContent=alliance?'ALLIANCE '+(alliance.allianceTag||alliance.allianceId||query):'RÉSULTATS JOUEURS';$('intelSummary').textContent=fmt(d&&d.total||players.length)+' joueur(s) · source Collector locale · READ-ONLY';for(const p of players){const card=document.createElement('button');card.type='button';card.className='intel-card';card.appendChild(intelAvatarNode(p));const body=document.createElement('div'),name=document.createElement('div');name.className='intel-name';name.textContent=p.pseudo||'—';body.appendChild(name);const meta=document.createElement('div');meta.className='intel-meta';meta.textContent='S'+(p.serverId||'—')+' · '+(p.allianceTag||p.allianceId||'sans alliance')+' · HQ '+(p.hqLevel==null?'—':p.hqLevel);body.appendChild(meta);const sub=document.createElement('div');sub.className='intel-sub';const alias=p.matchedBy==='alias'&&p.matchedAlias?'Ancien pseudo : '+p.matchedAlias:(Array.isArray(p.aliases)&&p.aliases.length?'Alias : '+p.aliases.slice(0,2).join(' · '):'');sub.textContent=[alias,p.country?'Pays '+p.country:'',p.observedAt?'Vu '+p.observedAt:''].filter(Boolean).join(' · ');body.appendChild(sub);card.appendChild(body);const power=document.createElement('div');power.className='intel-power';power.textContent=p.power!=null?fmt(p.power):'—';card.appendChild(power);card.addEventListener('click',()=>{intelClose('intelOverlay');showPlayer(p,{fastLookup:{status:'intelligence',route:'PLAYER_INTELLIGENCE_V620'}},query||p.pseudo);applyRichProfile(p)});list.appendChild(card)}if(!players.length){const empty=document.createElement('div');empty.className='intel-summary';empty.textContent='Aucun joueur ne correspond à cette recherche et à ces filtres.';list.appendChild(empty)}intelOpen('intelOverlay')}
async function executeIntelligenceSearch(query){const q=String(query||'').trim();if(!q&&!activeIntelFilterCount()){intelOpen('filterOverlay');return}startScan(q||'FILTRES DE RECRUTEMENT');setStatus('RECHERCHE JOUEURS','Analyse locale du Collector · aucun scan Last War');try{const d=await intelligenceSearch(q),players=Array.isArray(d&&d.players)?d.players:[];stopScan();screen.classList.remove('found');steps(4);if(players.length===1&&Number(d&&d.total||1)===1){showPlayer(players[0],{fastLookup:{status:'intelligence',route:'PLAYER_INTELLIGENCE_V620'}},q||players[0].pseudo);applyRichProfile(players[0])}else{renderIntelligenceResults(d,q);setStatus(players.length?'RÉSULTATS TROUVÉS':'AUCUNE CIBLE',fmt(d&&d.total||0)+' joueur(s)',players.length?'ok':'error')}}catch(err){const manualStopped=err&&err.name==='AbortError'||String(err&&err.message||'')==='MANUAL_SEARCH_STOPPED';stopScan();screen.classList.remove('found');if(manualStopped){steps(0);setStatus('RADAR ARRÊTÉ','Recherche manuelle interrompue','ok')}else if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar puis relance la recherche','error')}else if(isLastWarAuthError(err)){showReauthRequired(err.message)}else setStatus('ERREUR FILTRES',String(err.message||err),'error')}}
'''
    ui = ui[:js_pos] + intelligence_js + '\n' + ui[js_pos:]

    start_marker = "/* WFGG_RADAR_FAST_LOOKUP_UI_V611 */\n$('searchForm').onsubmit=async e=>{"
    start = ui.find(start_marker)
    end = ui.find('\nhealth();session();', start)
    if start < 0 or end < 0:
        raise SystemExit(f'V620 submit range missing {start}/{end}')
    submit = r'''/* WFGG_RADAR_FAST_LOOKUP_UI_V611 */
/* WFGG_RADAR_PLAYER_INTELLIGENCE_SEARCH_V620 */
$('searchForm').onsubmit=async e=>{e.preventDefault();if(manualSearchRunning){await requestManualSearchStop();return}const q=$('q').value.trim(),federated=/^@federated:(?:APS)?\d+/i.test(q);if(!federated){await executeIntelligenceSearch(q);return}if(!q)return;startScan(q);try{const d=await runCollectorSearch(q),p=playerFrom(d);stopScan();if(p)showPlayer(p,d,q);else{screen.classList.remove('found');result.classList.remove('show');steps(4)}}catch(err){const manualStopped=err&&err.name==='AbortError'||String(err&&err.message||'')==='MANUAL_SEARCH_STOPPED';stopScan();screen.classList.remove('found');if(manualStopped){steps(0);setStatus('RADAR ARRÊTÉ','Recherche manuelle interrompue','ok');$('federatedTitle').textContent='COLLECTOR FÉDÉRÉ · ARRÊTÉ';$('federatedMeta').textContent='Recherche manuelle interrompue par l’utilisateur.';tone(300,.06,.018)}else if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar puis relance la recherche','error')}else if(isLastWarAuthError(err)){showReauthRequired(err.message)}else setStatus('ERREUR RADAR',err.message,'error')}};
'''
    ui = ui[:start] + submit + ui[end:]

    event_anchor = '\nhealth();session();'
    events = r'''
$('filterButton').addEventListener('click',()=>intelOpen('filterOverlay'));
$('filterClose').addEventListener('click',()=>intelClose('filterOverlay'));
$('intelClose').addEventListener('click',()=>intelClose('intelOverlay'));
$('filterClear').addEventListener('click',()=>{clearFilterUI();intelligenceFilters={};updateFilterBadge()});
$('filterPresetFR').addEventListener('click',()=>{$('fCountry').value='FR';$('fWithinDays').value='7';$('fSort').value='power_desc'});
$('filterApply').addEventListener('click',async()=>{intelligenceFilters=filtersFromUI();updateFilterBadge();intelClose('filterOverlay');await executeIntelligenceSearch($('q').value.trim())});
$('intelOverlay').addEventListener('click',e=>{if(e.target===$('intelOverlay'))intelClose('intelOverlay')});
$('filterOverlay').addEventListener('click',e=>{if(e.target===$('filterOverlay'))intelClose('filterOverlay')});
$('q').addEventListener('input',()=>{clearTimeout(intelSuggestTimer);const q=$('q').value.trim();if(q.length<3||manualSearchRunning)return;intelSuggestTimer=setTimeout(async()=>{if($('q').value.trim()!==q||manualSearchRunning)return;try{const d=await intelligenceSearch(q,{limit:20});if($('q').value.trim()===q&&(Number(d&&d.total||0)>1||(Array.isArray(d&&d.alliances)&&d.alliances.length)))renderIntelligenceResults(d,q)}catch(_){}},350)});
updateFilterBadge();
'''
    ui = replace_once(ui, event_anchor, '\n' + events + event_anchor, 'V620 event anchor')

UI.write_text(ui, encoding='utf-8')
print('RADAR_V620_PLAYER_INTELLIGENCE_UI_WORKER=READY')
