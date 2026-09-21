#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
TRANSPORT = ROOT / 'src/game/remote-transport.js'
WORKER = ROOT / 'src/worker.js'
UI = ROOT / 'public/live-radar.html'

def replace_once(text, old, new, label):
    count=text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return text.replace(old,new,1)

# ---------------------------------------------------------------------------
# Transport / Worker: keep the public UI API stable, but route it to V6.21.
# ---------------------------------------------------------------------------
transport=TRANSPORT.read_text(encoding='utf-8')
if 'WFGG_RADAR_PLAYER_INTELLIGENCE_TRANSPORT_V621' not in transport:
    anchor="""  collectorPlayerIntelligence(filters = {}) {
    return this.request('/v1/collector/intelligence/search', { body: filters || {} });
  }
"""
    addition="""  // WFGG_RADAR_PLAYER_INTELLIGENCE_TRANSPORT_V621
  collectorPlayerIntelligenceV621(filters = {}) {
    return this.request('/v1/collector/intelligence/search-v621', { body: filters || {} });
  }
"""
    transport=replace_once(transport,anchor,anchor+addition,'V621 transport anchor')
TRANSPORT.write_text(transport,encoding='utf-8')

worker=WORKER.read_text(encoding='utf-8')
if 'WFGG_RADAR_RECRUITMENT_UX_WORKER_V621' not in worker:
    anchor="""      // WFGG_RADAR_PLAYER_INTELLIGENCE_WORKER_V620
      if (url.pathname === '/api/radar/intelligence/search' && request.method === 'POST') {
"""
    replacement="""      // WFGG_RADAR_PLAYER_INTELLIGENCE_WORKER_V620
      // WFGG_RADAR_RECRUITMENT_UX_WORKER_V621
      if (url.pathname === '/api/radar/intelligence/search' && request.method === 'POST') {
"""
    worker=replace_once(worker,anchor,replacement,'V621 worker marker')
    old="const result = await transport.collectorPlayerIntelligence(filters);"
    new="const result = await transport.collectorPlayerIntelligenceV621(filters);"
    worker=replace_once(worker,old,new,'V621 worker transport')
WORKER.write_text(worker,encoding='utf-8')

# ---------------------------------------------------------------------------
# UI: mobile-first filter panel with chips, include/exclude and game-origin
# country values only.
# ---------------------------------------------------------------------------
ui=UI.read_text(encoding='utf-8')
if 'WFGG_RADAR_RECRUITMENT_UX_UI_V621' not in ui:
    css=r'''
/* WFGG_RADAR_RECRUITMENT_UX_UI_V621 */
.filter-v621-note{font:9px ui-monospace,monospace;color:#7f9275;line-height:1.45;margin:8px 0 12px}
.filter-v621-warning{display:none;border:1px solid #8f7b35;background:#251f0b;color:#ead58b;border-radius:10px;padding:9px 10px;font:10px ui-monospace,monospace;line-height:1.4;margin:8px 0}
.filter-v621-warning.show{display:block}
.filter-v621-summary{border:1px solid #34492b;background:#091107;border-radius:12px;padding:10px;margin:8px 0 12px;font:10px ui-monospace,monospace;color:#a8bf96;line-height:1.45}
.filter-section{border:1px solid #304427;border-radius:13px;background:#091107;margin:8px 0;overflow:hidden}
.filter-section>summary{cursor:pointer;list-style:none;padding:12px 13px;font:900 10px ui-monospace,monospace;color:#c8ee9c;letter-spacing:.06em;display:flex;align-items:center;justify-content:space-between}
.filter-section>summary::-webkit-details-marker{display:none}
.filter-section>summary:after{content:'+';font-size:16px;color:#809b57}
.filter-section[open]>summary:after{content:'−'}
.filter-section-body{padding:0 11px 12px}
.filter-v621-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.filter-v621-field{display:grid;gap:5px}
.filter-v621-field.wide{grid-column:1/-1}
.filter-v621-field label{font:900 9px ui-monospace,monospace;color:#879c78}
.filter-v621-field input,.filter-v621-field select{width:100%;box-sizing:border-box;border:1px solid #405632;border-radius:10px;background:#050d04;color:#dfedcf;padding:10px;font:11px ui-monospace,monospace;min-height:42px}
.filter-v621-field input:disabled,.filter-v621-field select:disabled{opacity:.45}
.token-editor{border:1px solid #344a2a;border-radius:12px;padding:9px;margin:8px 0;background:#071006}
.token-editor-title{font:900 9px ui-monospace,monospace;color:#95ab84;margin-bottom:7px}
.token-mode{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:7px}
.token-mode button{border:1px solid #455d34;background:#101b0d;color:#9dad90;border-radius:8px;padding:7px;font:900 9px ui-monospace,monospace}
.token-mode button.active{background:#698a2d;color:#efffc6;border-color:#a7c75a}
.token-mode button[data-mode="exclude"].active{background:#572a1f;border-color:#9b5e4b;color:#ffd0c1}
.token-entry{display:grid;grid-template-columns:minmax(0,1fr) 42px;gap:6px}
.token-entry input{width:100%;box-sizing:border-box;border:1px solid #425a32;border-radius:9px;background:#050d04;color:#e5efd9;padding:9px;font:11px ui-monospace,monospace}
.token-entry button{border:1px solid #6e873d;border-radius:9px;background:#18260e;color:#d9f39b;font:900 18px ui-monospace,monospace}
.token-chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px;min-height:4px}
.token-chip{border:1px solid #61773f;border-radius:999px;background:#14200d;color:#d9eba9;padding:5px 8px;font:900 9px ui-monospace,monospace;display:inline-flex;align-items:center;gap:5px}
.token-chip.exclude{border-color:#844c3c;background:#24120d;color:#f2bbaa}
.token-chip button{border:0;background:transparent;color:inherit;padding:0;font:900 12px ui-monospace,monospace}
.filter-actions-v621{position:sticky;bottom:-14px;background:#0b1409ee;backdrop-filter:blur(8px);padding:10px 0 2px;display:grid;grid-template-columns:1fr 1.4fr;gap:8px;margin-top:12px}
.filter-actions-v621 button{border:1px solid #63783b;border-radius:11px;background:#14200d;color:#d8ed9f;padding:11px;font:900 10px ui-monospace,monospace}
.filter-actions-v621 .primary{background:linear-gradient(#b7dc4f,#718c29);color:#101806}
.filter-actions-v621 .preset{grid-column:1/-1;border-color:#496c8b;background:#0e1b25;color:#b9ddff}
@media(max-width:520px){.filter-v621-grid{grid-template-columns:1fr 1fr}.filter-v621-field.wide{grid-column:1/-1}.intel-modal{padding:10px}.filter-section>summary{padding:11px}.filter-section-body{padding:0 9px 10px}}
'''
    ui=replace_once(ui,'</style>',css+'\n</style>','V621 css')

    start=ui.find('<div id="filterOverlay" class="intel-overlay"')
    end=ui.find('\n<script>',start)
    if start<0 or end<0:
        raise SystemExit(f'V621_FILTER_OVERLAY_RANGE={start}/{end}')
    overlay=r'''<div id="filterOverlay" class="intel-overlay" aria-hidden="true">
  <div class="intel-modal" role="dialog" aria-modal="true" aria-labelledby="filterTitle">
    <div class="intel-head"><div id="filterTitle" class="intel-title">FILTRES DE RECRUTEMENT · V6.21</div><button id="filterClose" class="intel-close" type="button">FERMER</button></div>
    <div id="filterV621Warning" class="filter-v621-warning"></div>
    <div id="filterV621Summary" class="filter-v621-summary">Aucun filtre actif.</div>

    <details class="filter-section" open>
      <summary>PROFIL</summary>
      <div class="filter-section-body">
        <div class="filter-v621-grid">
          <div class="filter-v621-field wide"><label>PAYS PROPOSÉS PAR LAST WAR</label><select id="fCountry"><option value="">Chargement des pays du jeu…</option></select></div>
          <div class="filter-v621-field"><label>PUISSANCE MIN</label><input id="fMinPower" inputmode="decimal" placeholder="ex. 100M"></div>
          <div class="filter-v621-field"><label>PUISSANCE MAX</label><input id="fMaxPower" inputmode="decimal" placeholder="ex. 300M"></div>
          <div class="filter-v621-field"><label>HQ MIN</label><input id="fMinHQ" inputmode="numeric" placeholder="28"></div>
          <div class="filter-v621-field"><label>HQ MAX</label><input id="fMaxHQ" inputmode="numeric" placeholder="31"></div>
        </div>
        <div class="filter-v621-note">La liste Pays est construite uniquement avec les valeurs réellement fournies par Last War aux profils collectés. Aucune liste mondiale générique n’est ajoutée.</div>
      </div>
    </details>

    <details class="filter-section" open>
      <summary>CIBLAGE</summary>
      <div class="filter-section-body">
        <div class="token-editor" data-kind="servers">
          <div class="token-editor-title">SERVEURS</div>
          <div class="token-mode"><button type="button" class="active" data-mode="include">INCLURE</button><button type="button" data-mode="exclude">EXCLURE</button></div>
          <div class="token-entry"><input id="fServerToken" inputmode="numeric" placeholder="ex. 992 ou S992"><button type="button" data-add="+">+</button></div>
          <div id="fServerChips" class="token-chips"></div>
        </div>
        <div class="token-editor" data-kind="alliances">
          <div class="token-editor-title">ALLIANCES</div>
          <div class="token-mode"><button type="button" class="active" data-mode="include">INCLURE</button><button type="button" data-mode="exclude">EXCLURE</button></div>
          <div class="token-entry"><input id="fAllianceToken" placeholder="Tag, nom ou ID"><button type="button" data-add="+">+</button></div>
          <div id="fAllianceChips" class="token-chips"></div>
        </div>
        <div class="token-editor" data-kind="players">
          <div class="token-editor-title">JOUEURS</div>
          <div class="token-mode"><button type="button" class="active" data-mode="include">INCLURE</button><button type="button" data-mode="exclude">EXCLURE</button></div>
          <div class="token-entry"><input id="fPlayerToken" placeholder="Pseudo, ancien pseudo ou UID"><button type="button" data-add="+">+</button></div>
          <div id="fPlayerChips" class="token-chips"></div>
        </div>
      </div>
    </details>

    <details class="filter-section">
      <summary>ACTIVITÉ OBSERVÉE</summary>
      <div class="filter-section-body">
        <div class="filter-v621-grid">
          <div class="filter-v621-field"><label>OBSERVÉ DANS LES X DERNIERS JOURS</label><input id="fWithinDays" inputmode="numeric" placeholder="7"></div>
          <div class="filter-v621-field"><label>NON OBSERVÉ DEPUIS AU MOINS X JOURS</label><input id="fOlderDays" inputmode="numeric" placeholder="30"></div>
        </div>
        <div class="filter-v621-note">Il s’agit de l’activité observée par Radar, pas de la dernière connexion Last War.</div>
      </div>
    </details>

    <details class="filter-section">
      <summary>OPTIONS AVANCÉES & TRI</summary>
      <div class="filter-section-body">
        <div class="filter-v621-grid">
          <div class="filter-v621-field"><label>ARMY POWER MIN</label><input id="fMinArmyPower" inputmode="decimal" placeholder="si disponible"></div>
          <div class="filter-v621-field"><label>KILLS MIN</label><input id="fMinKills" inputmode="decimal" placeholder="si disponible"></div>
          <div class="filter-v621-field"><label>SVIP MIN</label><input id="fMinSVIP" inputmode="numeric" placeholder="si disponible"></div>
          <div class="filter-v621-field"><label>TRI</label><select id="fSort"><option value="power_desc">Puissance ↓</option><option value="power_asc">Puissance ↑</option><option value="hq_desc">HQ ↓</option><option value="observed_desc">Observation récente</option><option value="army_desc">Army Power ↓</option><option value="kills_desc">Kills ↓</option><option value="pseudo_asc">Pseudo A→Z</option></select></div>
        </div>
      </div>
    </details>

    <div class="filter-actions-v621">
      <button id="filterPresetFR" class="preset" type="button">🇫🇷 RECRUTEMENT FR</button>
      <button id="filterClear" type="button">RÉINITIALISER</button>
      <button id="filterApply" class="primary" type="button">APPLIQUER</button>
    </div>
  </div>
</div>'''
    ui=ui[:start]+overlay+ui[end:]

    # Insert overriding V6.21 behavior before the existing V6.20 event bindings.
    event_anchor="\n$('filterButton').addEventListener('click',()=>intelOpen('filterOverlay'));"
    if ui.count(event_anchor)!=1:
        raise SystemExit(f'V621_EVENT_ANCHOR_COUNT={ui.count(event_anchor)}')

    js=r'''
/* WFGG_RADAR_RECRUITMENT_UX_UI_V621 */
let v621Tokens={
  servers:{mode:'include',include:[],exclude:[]},
  alliances:{mode:'include',include:[],exclude:[]},
  players:{mode:'include',include:[],exclude:[]}
};
let v621CountryOptionsLoaded=false;
let v621LatestWarnings=[];

function v621HumanWarning(code){
  const map={
    country_unavailable:'Le filtre Pays n’est pas encore disponible dans les profils actuellement collectés.',
    server_unavailable:'Le filtre Serveur n’est pas disponible avec les données actuelles.',
    alliance_unavailable:'Le filtre Alliance n’est pas disponible avec les données actuelles.',
    hq_unavailable:'Le filtre HQ n’est pas disponible avec les données actuelles.',
    power_unavailable:'Le filtre Puissance n’est pas disponible avec les données actuelles.',
    lastSeen_unavailable:'Le filtre d’activité observée n’est pas disponible avec les données actuelles.',
    activity_unavailable:'Le filtre d’activité observée n’est pas disponible avec les données actuelles.',
    armyPower_unavailable:'Army Power n’est pas disponible avec les données actuelles.',
    kills_unavailable:'Kills n’est pas disponible avec les données actuelles.',
    svip_unavailable:'SVIP n’est pas disponible avec les données actuelles.'
  };
  return map[String(code||'')]||'Un critère indisponible a été ignoré sans interrompre la recherche.';
}
function v621HumanError(err){
  const s=String(err&&err.message||err||'');
  if(s.includes('COLLECTOR_DB_UNAVAILABLE'))return 'La base Radar est momentanément indisponible.';
  if(s.includes('PLAYER_INDEX_UNAVAILABLE'))return 'L’index joueurs Radar n’est pas encore disponible.';
  if(s.includes('REQUEST_INVALID')||s.includes('FILTER_TOO_LONG')||s.includes('PAGE_INVALID'))return 'Vérifie les critères de recherche.';
  if(s.includes('TIMEOUT'))return 'La recherche a pris trop de temps. Réessaie.';
  return 'La recherche n’a pas pu être exécutée.';
}
function v621SetWarning(messages){
  const box=$('filterV621Warning'); if(!box)return;
  const list=(messages||[]).filter(Boolean);
  box.textContent=list.join(' · ');
  box.classList.toggle('show',list.length>0);
}
function v621CountryFlag(code){
  const s=String(code||'').toUpperCase();
  if(!/^[A-Z]{2}$/.test(s))return '';
  return String.fromCodePoint(...[...s].map(ch=>127397+ch.charCodeAt(0)));
}
function v621CountryLabel(raw){
  const s=String(raw||'').trim();
  if(/^[A-Za-z]{2}$/.test(s)){
    const code=s.toUpperCase(); let label='';
    try{label=new Intl.DisplayNames(['fr'],{type:'region'}).of(code)||''}catch(_){}
    return [v621CountryFlag(code),label||code].filter(Boolean).join(' ');
  }
  return s;
}
function v621NormalizeToken(kind,value){
  let s=String(value||'').trim();
  if(!s)return '';
  if(kind==='servers'&&/^s\d+$/i.test(s))s=s.slice(1);
  if(kind==='alliances'){s=s.replace(/^\[+|\]+$/g,'').trim(); if(s)s=s.toUpperCase()}
  return s;
}
function v621InputId(kind){return kind==='servers'?'fServerToken':kind==='alliances'?'fAllianceToken':'fPlayerToken'}
function v621ChipId(kind){return kind==='servers'?'fServerChips':kind==='alliances'?'fAllianceChips':'fPlayerChips'}
function v621RenderChips(kind){
  const host=$(v621ChipId(kind)); if(!host)return; host.replaceChildren();
  for(const mode of ['include','exclude']){
    for(const value of v621Tokens[kind][mode]){
      const chip=document.createElement('span'); chip.className='token-chip '+(mode==='exclude'?'exclude':'include');
      const sign=document.createElement('span'); sign.textContent=mode==='exclude'?'−':'+';
      const label=document.createElement('span'); label.textContent=value;
      const del=document.createElement('button'); del.type='button'; del.textContent='×'; del.setAttribute('aria-label','Retirer '+value);
      del.addEventListener('click',()=>{v621Tokens[kind][mode]=v621Tokens[kind][mode].filter(x=>x!==value);v621RenderChips(kind);updateFilterBadge()});
      chip.append(sign,label,del);host.appendChild(chip);
    }
  }
}
function v621AddToken(kind){
  const input=$(v621InputId(kind)),state=v621Tokens[kind]; if(!input||!state)return;
  const value=v621NormalizeToken(kind,input.value); if(!value)return;
  const key=value.toLocaleLowerCase();
  for(const mode of ['include','exclude'])state[mode]=state[mode].filter(x=>x.toLocaleLowerCase()!==key);
  state[state.mode].push(value);input.value='';v621RenderChips(kind);updateFilterBadge();
}
function v621ParseMetric(value){
  let s=String(value==null?'':value).trim().toUpperCase().replace(/\s/g,'').replace(',','.');
  if(!s)return null;
  const m=s.match(/^([0-9]+(?:\.[0-9]+)?)([KMBG])?$/); if(!m)return NaN;
  const mult={K:1e3,M:1e6,B:1e9,G:1e9}[m[2]]||1;
  return Math.round(Number(m[1])*mult);
}
function v621ParseInt(value){const s=String(value==null?'':value).trim();if(!s)return null;const n=Number(s);return Number.isFinite(n)?Math.trunc(n):NaN}
function v621FieldMetric(id){const e=$(id),n=v621ParseMetric(e&&e.value);if(Number.isNaN(n)){if(e)e.setAttribute('aria-invalid','true');v621SetWarning(['Vérifie les valeurs numériques indiquées. Formats acceptés : 100M, 1.2B ou un nombre complet.']);return null}if(e)e.removeAttribute('aria-invalid');return n}
function v621FieldInt(id){const e=$(id),n=v621ParseInt(e&&e.value);if(Number.isNaN(n)){if(e)e.setAttribute('aria-invalid','true');v621SetWarning(['Vérifie les valeurs numériques indiquées.']);return null}if(e)e.removeAttribute('aria-invalid');return n}

function filtersFromUI(){
  return {
    country:$('fCountry').disabled?'':$('fCountry').value,
    includeServers:[...v621Tokens.servers.include],excludeServers:[...v621Tokens.servers.exclude],
    includeAlliances:[...v621Tokens.alliances.include],excludeAlliances:[...v621Tokens.alliances.exclude],
    includePlayers:[...v621Tokens.players.include],excludePlayers:[...v621Tokens.players.exclude],
    minPower:v621FieldMetric('fMinPower'),maxPower:v621FieldMetric('fMaxPower'),
    minHQ:v621FieldInt('fMinHQ'),maxHQ:v621FieldInt('fMaxHQ'),
    observedWithinDays:v621FieldInt('fWithinDays'),observedOlderDays:v621FieldInt('fOlderDays'),
    minArmyPower:v621FieldMetric('fMinArmyPower'),minKills:v621FieldMetric('fMinKills'),
    minSVIP:v621FieldInt('fMinSVIP'),sort:$('fSort').value||'power_desc'
  };
}
function clearFilterUI(){
  for(const id of ['fMinPower','fMaxPower','fMinHQ','fMaxHQ','fWithinDays','fOlderDays','fMinArmyPower','fMinKills','fMinSVIP']){const e=$(id);if(e)e.value=''}
  if($('fCountry'))$('fCountry').value='';
  if($('fSort'))$('fSort').value='power_desc';
  v621Tokens={servers:{mode:'include',include:[],exclude:[]},alliances:{mode:'include',include:[],exclude:[]},players:{mode:'include',include:[],exclude:[]}};
  for(const kind of ['servers','alliances','players'])v621RenderChips(kind);
  v621LatestWarnings=[];v621SetWarning([]);v621RefreshModeButtons();updateFilterBadge();
}
function v621PopulateCountries(options,caps){
  const sel=$('fCountry');if(!sel)return;
  const current=sel.value;sel.replaceChildren();
  const blank=document.createElement('option');blank.value='';blank.textContent='Tous les pays disponibles';sel.appendChild(blank);
  const countries=Array.isArray(options&&options.countries)?options.countries:[];
  for(const raw of countries){
    const opt=document.createElement('option');opt.value=String(raw);opt.textContent=v621CountryLabel(raw);sel.appendChild(opt);
  }
  const available=Boolean(caps&&caps.country&&countries.length);
  sel.disabled=!available;
  if(!available){blank.textContent='Pays indisponible dans les profils collectés';sel.value=''}
  else if([...sel.options].some(o=>o.value===current))sel.value=current;
  v621CountryOptionsLoaded=true;
}
function applyIntelCapabilities(caps,options,warnings){
  intelligenceCapabilities=caps||{};
  v621PopulateCountries(options||{},intelligenceCapabilities);
  for(const [id,key] of [['fWithinDays','lastSeen'],['fOlderDays','lastSeen'],['fMinPower','power'],['fMaxPower','power'],['fMinHQ','hq'],['fMaxHQ','hq'],['fMinArmyPower','armyPower'],['fMinKills','kills'],['fMinSVIP','svip']]){
    const e=$(id);if(e&&Object.prototype.hasOwnProperty.call(intelligenceCapabilities,key))e.disabled=!intelligenceCapabilities[key];
  }
  if(Array.isArray(warnings)&&warnings.length){v621LatestWarnings=warnings;v621SetWarning(warnings.map(v621HumanWarning))}
}
async function intelligenceSearch(query,extra){
  const payload=Object.assign({query:String(query||'').trim(),limit:50,offset:0},intelligenceFilters,extra||{});
  const d=await api('/api/radar/intelligence/search',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});
  applyIntelCapabilities(d&&d.capabilities||{},d&&d.options||{},d&&d.warnings||[]);
  return d;
}
async function v621LoadMetadata(){
  try{
    const d=await api('/api/radar/intelligence/search',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({mode:'metadata',limit:1})});
    applyIntelCapabilities(d&&d.capabilities||{},d&&d.options||{},d&&d.warnings||[]);
    updateFilterBadge();
  }catch(err){v621SetWarning([v621HumanError(err)])}
}
function activeIntelFilterCount(){
  let n=0;
  if($('fCountry')&&!$('fCountry').disabled&&$('fCountry').value)n++;
  for(const kind of ['servers','alliances','players'])n+=v621Tokens[kind].include.length+v621Tokens[kind].exclude.length;
  for(const id of ['fMinPower','fMaxPower','fMinHQ','fMaxHQ','fWithinDays','fOlderDays','fMinArmyPower','fMinKills','fMinSVIP']){const e=$(id);if(e&&!e.disabled&&String(e.value||'').trim())n++}
  return n;
}
function v621FilterSummaryText(){
  const parts=[];
  if($('fCountry')&&!$('fCountry').disabled&&$('fCountry').value)parts.push(v621CountryLabel($('fCountry').value));
  const names={servers:'Serveur',alliances:'Alliance',players:'Joueur'};
  for(const kind of ['servers','alliances','players']){
    for(const value of v621Tokens[kind].include)parts.push(names[kind]+' +'+value);
    for(const value of v621Tokens[kind].exclude)parts.push(names[kind]+' −'+value);
  }
  const min=v621ParseMetric($('fMinPower')&&$('fMinPower').value);if(Number.isFinite(min))parts.push('Puissance ≥ '+fmt(min));
  const max=v621ParseMetric($('fMaxPower')&&$('fMaxPower').value);if(Number.isFinite(max))parts.push('Puissance ≤ '+fmt(max));
  const hq=v621ParseInt($('fMinHQ')&&$('fMinHQ').value);if(Number.isFinite(hq))parts.push('HQ ≥ '+hq);
  const within=v621ParseInt($('fWithinDays')&&$('fWithinDays').value);if(Number.isFinite(within))parts.push('Observé < '+within+' j');
  return parts.length?parts.slice(0,7).join(' · ')+(parts.length>7?' · …':''):'Aucun filtre actif.';
}
function updateFilterBadge(){
  const n=activeIntelFilterCount(),b=$('filterButton');if(b){b.textContent=n?'FILTRES · '+n:'FILTRES';b.classList.toggle('active',n>0)}
  const s=$('filterV621Summary');if(s)s.textContent=v621FilterSummaryText();
}
function v621RefreshModeButtons(){
  document.querySelectorAll('.token-editor').forEach(editor=>{
    const kind=editor.dataset.kind,state=v621Tokens[kind];if(!state)return;
    editor.querySelectorAll('.token-mode button').forEach(btn=>btn.classList.toggle('active',btn.dataset.mode===state.mode));
  });
}
function v621ApplyFRPreset(){
  const sel=$('fCountry');let found='';
  if(sel&&!sel.disabled){
    for(const opt of sel.options){
      const raw=String(opt.value||'').trim().toUpperCase();
      const label=String(opt.textContent||'').toLocaleLowerCase();
      if(raw==='FR'||raw==='FRA'||raw==='FRANCE'||label.includes('france')){found=opt.value;break}
    }
  }
  if(found){sel.value=found;v621SetWarning([])}
  else v621SetWarning(['Le pays France n’est pas encore disponible dans les valeurs Last War actuellement collectées. Les autres critères du preset restent utilisables.']);
  if($('fWithinDays')&&!$('fWithinDays').disabled)$('fWithinDays').value='7';
  if($('fSort'))$('fSort').value='power_desc';
  updateFilterBadge();
}
async function executeIntelligenceSearch(query){
  const q=String(query||'').trim();
  if(!q&&!activeIntelFilterCount()){intelOpen('filterOverlay');if(!v621CountryOptionsLoaded)v621LoadMetadata();return}
  startScan(q||'FILTRES DE RECRUTEMENT');setStatus('RECHERCHE JOUEURS','Analyse locale du Collector · aucun scan Last War');
  try{
    const d=await intelligenceSearch(q),players=Array.isArray(d&&d.players)?d.players:[];
    stopScan();screen.classList.remove('found');steps(4);
    const warnings=(d&&d.warnings||[]).map(v621HumanWarning);if(warnings.length)v621SetWarning(warnings);
    if(players.length===1&&Number(d&&d.total||1)===1){showPlayer(players[0],{fastLookup:{status:'intelligence',route:'PLAYER_INTELLIGENCE_V621'}},q||players[0].pseudo);applyRichProfile(players[0])}
    else{renderIntelligenceResults(d,q);setStatus(players.length?'RÉSULTATS TROUVÉS':'AUCUNE CIBLE',fmt(d&&d.total||0)+' joueur(s)'+(warnings.length?' · '+warnings[0]:''),players.length?'ok':'error')}
  }catch(err){
    const manualStopped=err&&err.name==='AbortError'||String(err&&err.message||'')==='MANUAL_SEARCH_STOPPED';stopScan();screen.classList.remove('found');
    if(manualStopped){steps(0);setStatus('RADAR ARRÊTÉ','Recherche manuelle interrompue','ok')}
    else if(err.status===401){login.classList.add('show');setStatus('SESSION REQUISE','Connecte le Radar puis relance la recherche','error')}
    else if(isLastWarAuthError(err)){showReauthRequired(err.message)}
    else{const msg=v621HumanError(err);v621SetWarning([msg]);setStatus('RECHERCHE INDISPONIBLE',msg,'error')}
  }
}
function v621BindFilterUX(){
  document.querySelectorAll('.token-editor').forEach(editor=>{
    const kind=editor.dataset.kind,state=v621Tokens[kind];if(!state)return;
    editor.querySelectorAll('.token-mode button').forEach(btn=>btn.addEventListener('click',()=>{state.mode=btn.dataset.mode;v621RefreshModeButtons()}));
    const add=editor.querySelector('[data-add]'),input=$(v621InputId(kind));
    if(add)add.addEventListener('click',()=>v621AddToken(kind));
    if(input)input.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===','){e.preventDefault();v621AddToken(kind)}});
  });
  for(const id of ['fCountry','fMinPower','fMaxPower','fMinHQ','fMaxHQ','fWithinDays','fOlderDays','fMinArmyPower','fMinKills','fMinSVIP','fSort']){
    const e=$(id);if(e)e.addEventListener('input',updateFilterBadge);
  }
  v621RefreshModeButtons();updateFilterBadge();
}
'''
    ui=replace_once(ui,event_anchor,'\n'+js+event_anchor,'V621 JS insertion')

    # Existing V6.20 buttons keep their IDs. Add V6.21 listeners after them.
    post_anchor="updateFilterBadge();\n\nhealth();"
    if ui.count(post_anchor)!=1:
        raise SystemExit(f'V621_POST_EVENT_ANCHOR_COUNT={ui.count(post_anchor)}')
    extra=r'''updateFilterBadge();
v621BindFilterUX();
$('filterButton').addEventListener('click',()=>{if(!v621CountryOptionsLoaded)v621LoadMetadata()});
$('filterPresetFR').addEventListener('click',v621ApplyFRPreset);

health();'''
    ui=ui.replace(post_anchor,extra,1)

    # The legacy preset handler would set "FR" blindly. Neutralize only that
    # one line; the V6.21 handler selects from actual Last War values.
    legacy="$('filterPresetFR').addEventListener('click',()=>{$('fCountry').value='FR';$('fWithinDays').value='7';$('fSort').value='power_desc'});"
    if legacy in ui:
        ui=ui.replace(legacy,"$('filterPresetFR').addEventListener('click',()=>{});",1)

UI.write_text(ui,encoding='utf-8')
print('RADAR_V621_RECRUITMENT_UX_UI_WORKER=READY')
