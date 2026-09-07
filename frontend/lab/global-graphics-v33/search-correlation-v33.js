(()=>{
'use strict';

/* Search/result correlation layer for V33 mobile LAB.
   Hero free-text search is intentionally STRICT:
   Murphy / Audie / 50006 are the same hero key, but normal hero search returns only assets with
   direct evidence for that hero (western name, internal alias or numeric hero ID).

   V35 previewability policy:
   - verified preview results are persisted in localStorage;
   - cheap semantic preflight classifies obvious autonomous/non-autonomous assets before selection;
   - the default filter shows only verified or likely-displayable assets;
   - unknown/non-autonomous/unavailable assets remain explorable through the advanced filter.
*/

const PAGE_SIZE=120;
const NAV_PREFETCH_REMAINING=18;
const SCROLL_PREFETCH_VIEWPORTS=2.0;
const AUTO_SKIP_RUNTIME_FAILURES=true;
const PREVIEW_STORE_KEY='wfgg-preview-status-v35';
let generation=0;
let activeController=null;
let loadedOffset=0;
let totalMatches=0;
let sourceTotalMatches=0;
let hasMore=false;
let loadingMore=false;
let queryToken='';
let scrollTimer=0;
let skippedRuntime=new Set();
let skippedRuntimeCount=0;
let autoSkipBusy=false;
let activeHeroQueryId='';
let activeHeroQueryLabel='';
const heroAliasMap=new Map();
let heroRegistryPromise=null;
let previewRegistry={};

function loadPreviewRegistry(){
  try{const x=JSON.parse(localStorage.getItem(PREVIEW_STORE_KEY)||'{}');if(x&&typeof x==='object')previewRegistry=x;}catch{previewRegistry={};}
}
function savePreviewRegistry(){
  try{localStorage.setItem(PREVIEW_STORE_KEY,JSON.stringify(previewRegistry));}catch(e){console.debug('V35_PREVIEW_REGISTRY_SAVE_FAIL',e);}
}
loadPreviewRegistry();

function normPath(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();}
function semanticPreview(a){
  const p=normPath(a),role=String(a?.model_role||'').toLowerCase(),tech=String(a?.tech_kind||'').toLowerCase();
  const dim=String(a?.dimension_class||''),av=String(a?.render_availability||'');
  const local=av==='local-exact'||av==='local-resolved';
  const animation=p.includes('/animation/')||p.endsWith('.anim')||role==='animation'||tech==='animation'||tech==='animationclip';
  if(animation)return {status:'nonautonomous',verified:false,mode:'',reason:'animation-non-autonome'};
  if(av==='global-index-only')return {status:'unavailable',verified:false,mode:'',reason:'bundle-absent'};
  const effectPrefab=(p.includes('/effect/')||p.includes('/effects/')||p.includes('/vfx/')||/(^|\/)(eff_|fx_|vfx_)/.test(p))&&(p.includes('/prefab/')||p.endsWith('.prefab'));
  if(effectPrefab)return {status:'unknown',verified:false,mode:'',reason:'prefab-effet-a-verifier'};
  const rasterLikely=dim==='2D'||/sprite|texture2d|texture|atlas|image|png|jpg|jpeg/.test(tech);
  const geometryLikely=['geometry','geometry-candidate'].includes(role)||(dim==='3D'&&!['material','shader','component','texture'].includes(role));
  const mixedLikely=dim==='Mixte 2D/3D'&&!['material','shader'].includes(role);
  if(local&&(rasterLikely||geometryLikely||mixedLikely))return {status:'likely-visible',verified:false,mode:rasterLikely?'2d':geometryLikely?'3d':'',reason:'preflight-local'};
  return {status:'unknown',verified:false,mode:'',reason:'non-teste'};
}
function previewInfo(a){
  const saved=previewRegistry[String(a?.stable_id||'')];
  if(saved&&saved.status)return {...saved,verified:true};
  return semanticPreview(a);
}
function previewLabel(info){
  if(info.status==='visible')return info.mode==='3d'?'VISIBLE 3D':info.mode==='2d'?'VISIBLE 2D':'VISIBLE';
  if(info.status==='likely-visible')return 'PROBABLE';
  if(info.status==='nonautonomous')return 'NON AUTONOME';
  if(info.status==='unavailable')return 'NON AFFICHABLE';
  return 'À VÉRIFIER';
}
function previewClass(info){
  if(info.status==='visible')return 'preview-good';
  if(info.status==='likely-visible')return 'preview-likely';
  if(info.status==='nonautonomous'||info.status==='unavailable')return 'preview-bad';
  return 'preview-unknown';
}
function currentPreviewFilter(){return document.querySelector('#preview_status')?.value||'previewable';}
function previewMatches(a,mode=currentPreviewFilter()){
  const x=previewInfo(a);
  if(mode==='all')return true;
  if(mode==='previewable')return x.status==='visible'||x.status==='likely-visible';
  if(mode==='verified-visible')return x.status==='visible';
  if(mode==='likely-visible')return x.status==='likely-visible';
  if(mode==='nonvisible')return x.status==='nonautonomous'||x.status==='unavailable';
  if(mode==='nonautonomous')return x.status==='nonautonomous';
  if(mode==='unavailable')return x.status==='unavailable';
  if(mode==='unknown')return x.status==='unknown';
  return true;
}
function recordPreview(a,status,mode='',reason=''){
  const sid=String(a?.stable_id||'');if(!sid)return;
  previewRegistry[sid]={status:String(status||'unknown'),mode:String(mode||''),reason:String(reason||'').slice(0,180),updatedAt:Date.now()};
  savePreviewRegistry();
  a.preview_status=previewRegistry[sid].status;a.preview_mode=previewRegistry[sid].mode;a.preview_verified=true;a.preview_reason=previewRegistry[sid].reason;
  console.debug('V35_PREVIEW_STATUS',sid,status,mode,reason);
}

function installPreviewFilterUI(){
  const body=document.querySelector('#advancedDialog .modal-body');if(!body||document.querySelector('#preview_status'))return;
  const label=document.createElement('label');label.innerHTML='Aperçu<select id="preview_status"><option value="previewable">Affichables / probables</option><option value="verified-visible">Affichables vérifiés</option><option value="likely-visible">Probablement affichables</option><option value="nonvisible">Non affichables connus</option><option value="nonautonomous">Composants non autonomes</option><option value="unavailable">Non affichables vérifiés</option><option value="unknown">À vérifier</option><option value="all">Tous, sans filtre d’aperçu</option></select>';
  body.insertBefore(label,body.firstChild?.nextSibling||body.firstChild);
  label.querySelector('select').addEventListener('change',()=>updateFilterSummary());
  const note=body.querySelector('.modal-note');if(note)note.textContent='Les filtres sont combinés. « Affichables / probables » exclut par défaut les composants non autonomes, les échecs déjà vérifiés et les prefabs d’effets encore inconnus. Choisis « À vérifier » ou « Tous » pour les auditer.';
}
installPreviewFilterUI();

const baseActiveFilters=activeFilters;
activeFilters=function(){
  const out=baseActiveFilters();const el=document.querySelector('#preview_status'),v=el?.value||'previewable';
  if(v!=='previewable')out.unshift({id:'preview_status',label:'Aperçu '+(el?.options[el.selectedIndex]?.textContent||v)});
  return out;
};
const baseUpdateFilterSummary=updateFilterSummary;
updateFilterSummary=function(){
  baseUpdateFilterSummary();
  if(!activeFilters().length){const h=document.querySelector('#filterSummary');if(h)h.innerHTML='<span class="filterchip">Aperçus affichables/probables · rendu local disponible</span>';}
};
const baseResetFilters=resetFilters;
resetFilters=function(run=true){baseResetFilters(false);const p=document.querySelector('#preview_status');if(p)p.value='previewable';updateFilterSummary();if(run)runSearch();};

function heroKey(s){return String(s??'').trim().toLowerCase().replace(/[\s_-]+/g,'');}
function registerHeroKey(key,hero){
  key=heroKey(key);if(!key)return;
  const old=heroAliasMap.get(key);
  if(!old)heroAliasMap.set(key,hero);
  else if(String(old.hero_id)!==String(hero.hero_id))heroAliasMap.set(key,null);
}
async function ensureHeroAliases(){
  if(heroRegistryPromise)return heroRegistryPromise;
  heroRegistryPromise=(async()=>{
    try{
      const r=await fetch(API+'/heroes',{cache:'no-store'});if(!r.ok)return;
      const d=await r.json();
      for(const h of (d.heroes||[])){
        const vals=[h.western_name,h.hero_id,...(h.aliases||[]),...(h.internal_aliases||[]),...(h.auto_link_aliases||[])];
        vals.forEach(v=>registerHeroKey(v,h));
      }
      console.info('V34_HERO_ALIAS_SEARCH ready keys='+heroAliasMap.size);
    }catch(e){console.debug('V34_HERO_ALIAS_SEARCH unavailable',e);}
  })();
  return heroRegistryPromise;
}
function resolveHeroQuery(raw){return heroAliasMap.get(heroKey(raw))||null;}

const baseRenderList=renderList;
renderList=function(){
  baseRenderList();
  const cards=[...document.querySelectorAll('#results .card')];
  cards.forEach((card,i)=>{
    const a=items[i];if(!a)return;
    const pi=previewInfo(a);a.preview_status=pi.status;a.preview_mode=pi.mode;a.preview_verified=!!pi.verified;a.preview_reason=pi.reason;
    const pv=document.createElement('span');pv.className='avail '+previewClass(pi);pv.textContent=previewLabel(pi);card.appendChild(pv);
    let links=(a.hero_links||[]);
    if(activeHeroQueryId)links=links.filter(h=>String(h.hero_id)===String(activeHeroQueryId)&&h.relation==='direct');
    else links=links.filter(h=>h.relation==='direct');
    if(!links.length)return;
    const seen=new Set(),labels=[];
    for(const h of links){const key=String(h.hero_id||'');if(seen.has(key))continue;seen.add(key);labels.push(`${h.western_name||'Héros'} · #${h.hero_id}`);if(labels.length>=2)break;}
    if(labels.length){const s=document.createElement('span');s.className='hero-link-label';s.textContent='Héros : '+labels.join(' · ');card.appendChild(s);}
  });
};

function currentParams(offset=0){
  const p=params();
  // preview_status is intentionally client-side: it combines persistent runtime knowledge with
  // semantic preflight and therefore cannot be represented by the static catalogue SQL alone.
  p.delete('preview_status');
  if(activeHeroQueryId){p.delete('q');p.set('hero_id',String(activeHeroQueryId));p.set('hero_relation','direct');}
  p.set('limit',String(PAGE_SIZE));p.set('offset',String(offset));return p;
}

function showCount(){
  const el=document.querySelector('#resultCount');if(!el)return;
  const pf=currentPreviewFilter();
  if(pf==='all')el.textContent=sourceTotalMatches>items.length?`${items.length}/${sourceTotalMatches}`:String(sourceTotalMatches||items.length||0);
  else el.textContent=hasMore?`${items.length}+`:String(items.length);
  el.title=pf==='all'
    ?(hasMore?`${items.length} résultats chargés sur ${sourceTotalMatches}. Le reste se charge automatiquement.`:`${sourceTotalMatches||items.length||0} résultats dans la sélection.`)
    :`${items.length} résultats correspondant au filtre d’aperçu trouvés après analyse de ${Math.min(loadedOffset,sourceTotalMatches)}/${sourceTotalMatches} assets source${hasMore?' ; la suite se charge automatiquement.':'.'}`;
  if(activeHeroQueryId)el.title+=` Recherche héros stricte: ${activeHeroQueryLabel} (#${activeHeroQueryId}).`;
}

function preparePageItems(raw){
  const mode=currentPreviewFilter();
  return (raw||[]).filter(a=>previewMatches(a,mode));
}
async function fetchPage(offset,gen){
  const controller=new AbortController();
  if(offset===0){try{activeController?.abort();}catch{}activeController=controller;}
  const r=await fetch(API+'/search?'+currentParams(offset),{signal:controller.signal,cache:'no-store'});
  const d=await r.json();if(gen!==generation)return null;if(!r.ok)throw new Error(d.message||d.error||'recherche impossible');
  const raw=d.items||[];d._rawCount=raw.length;d.items=preparePageItems(raw);return d;
}

function preserveStripPosition(fn){
  const strip=document.querySelector('#results'),left=strip?.scrollLeft||0;
  const activeSid=currentAsset?.stable_id||items[idx]?.stable_id||'';fn();
  requestAnimationFrame(()=>{const s=document.querySelector('#results');if(!s)return;s.scrollLeft=left;if(activeSid){const cards=[...s.querySelectorAll('.card')],pos=items.findIndex(x=>x.stable_id===activeSid);if(pos>=0&&cards[pos])cards[pos].classList.add('active');}});
}

async function loadMore(reason='stream'){
  if(loadingMore||!hasMore)return false;
  loadingMore=true;const gen=generation,start=loadedOffset;
  try{
    const d=await fetchPage(start,gen);if(!d)return false;
    if(queryToken&&d.queryToken&&queryToken!==d.queryToken)return false;
    const existing=new Set(items.map(x=>x.stable_id));let added=0;
    for(const x of (d.items||[]))if(!existing.has(x.stable_id)){items.push(x);existing.add(x.stable_id);added++;}
    loadedOffset=Number(d.offset??start)+Number(d._rawCount||0);
    sourceTotalMatches=Number(d.total??sourceTotalMatches);totalMatches=sourceTotalMatches;
    hasMore=!!d.hasMore&&loadedOffset<sourceTotalMatches;
    if(added){preserveStripPosition(()=>renderList());}showCount();
    console.debug('V35_RESULT_STREAM',reason,'visibleLoaded',items.length,'scanned',loadedOffset,'sourceTotal',sourceTotalMatches,'hasMore',hasMore);
    return added>0;
  }finally{loadingMore=false;}
}

function maybePrefetchFromSelection(){if(hasMore&&items.length-Math.max(0,idx)-1<=NAV_PREFETCH_REMAINING)loadMore('navigation-prefetch');}
function maybePrefetchFromScroll(){const strip=document.querySelector('#results');if(!strip||!hasMore||loadingMore)return;const remaining=strip.scrollWidth-strip.scrollLeft-strip.clientWidth;if(remaining<=strip.clientWidth*SCROLL_PREFETCH_VIEWPORTS)loadMore('horizontal-scroll');}
function installContinuousStrip(){
  const strip=document.querySelector('#results');if(!strip||strip.dataset.v33Continuous==='1')return;strip.dataset.v33Continuous='1';
  strip.addEventListener('scroll',()=>{clearTimeout(scrollTimer);scrollTimer=setTimeout(maybePrefetchFromScroll,70);},{passive:true});strip.addEventListener('pointerup',()=>setTimeout(maybePrefetchFromScroll,80),{passive:true});
}

function runtimeFailureOnStage(){const stage=document.querySelector('#stage');if(!stage)return null;const box=stage.querySelector('.errorbox');if(!box)return null;return {title:box.querySelector('h3')?.textContent?.trim()||'Rendu indisponible',details:box.querySelector('#errorDetails')?.textContent?.trim()||''};}
function rejectRuntimeId(sid){sid=String(sid||'');if(!sid)return false;if(!skippedRuntime.has(sid)){skippedRuntime.add(sid);skippedRuntimeCount++;}return true;}
function isRuntimeRejected(sid){return skippedRuntime.has(String(sid||''));}
function nextCandidateIndex(from){for(let i=Math.max(0,from);i<items.length;i++){const sid=items[i]?.stable_id;if(sid&&!isRuntimeRejected(sid))return i;}return -1;}
async function autoSkipRuntimeFailure(failedIndex,failedSid,gen){
  if(!AUTO_SKIP_RUNTIME_FAILURES||autoSkipBusy||gen!==generation)return false;
  const failure=runtimeFailureOnStage();if(!failure)return false;
  rejectRuntimeId(failedSid);recordPreview(items[failedIndex],'unavailable','',failure.details||failure.title);
  console.warn('V33_RUNTIME_SKIPPED',failedSid,failure.title,failure.details);
  const stage=document.querySelector('#stage');if(stage)stage.innerHTML='<div class="empty">Recherche du prochain rendu disponible…</div>';
  autoSkipBusy=true;
  try{
    let wanted=nextCandidateIndex(failedIndex+1);
    while(wanted<0&&hasMore&&gen===generation){await loadMore('runtime-failure-skip');wanted=nextCandidateIndex(failedIndex+1);if(!hasMore&&wanted<0)break;}
    if(gen!==generation)return true;
    if(wanted>=0){setTimeout(()=>select(wanted),0);return true;}
    for(let i=Math.min(failedIndex-1,items.length-1);i>=0;i--){const sid=items[i]?.stable_id;if(sid&&!isRuntimeRejected(sid)){setTimeout(()=>select(i),0);return true;}}
    if(stage)stage.innerHTML='<div class="empty">Aucun autre rendu décodable dans cette sélection.</div>';return true;
  }finally{autoSkipBusy=false;}
}

runSearch=async function(){
  installPreviewFilterUI();updateFilterSummary();await ensureHeroAliases();
  const rawQuery=document.querySelector('#q')?.value?.trim()||'',hero=resolveHeroQuery(rawQuery);
  activeHeroQueryId=hero?String(hero.hero_id):'';activeHeroQueryLabel=hero?String(hero.western_name||rawQuery):'';
  if(hero)console.info('V34_HERO_QUERY_STRICT',rawQuery,'=>',activeHeroQueryLabel,'#'+activeHeroQueryId);
  const gen=++generation;idx=-1;currentAsset=null;currentModel?.destroy?.();currentModel=null;
  if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
  items=[];loadedOffset=0;totalMatches=0;sourceTotalMatches=0;hasMore=false;queryToken='';skippedRuntime=new Set();skippedRuntimeCount=0;autoSkipBusy=false;
  document.querySelector('#stage').innerHTML='<div class="empty">Recherche…</div>';
  try{
    const d=await fetchPage(0,gen);if(!d)return;
    items=d.items||[];loadedOffset=Number(d.offset||0)+Number(d._rawCount||0);sourceTotalMatches=Number(d.total??0);totalMatches=sourceTotalMatches;hasMore=!!d.hasMore&&loadedOffset<sourceTotalMatches;queryToken=d.queryToken||'';
    while(!items.length&&hasMore&&gen===generation){await loadMore('preview-filter-initial-scan');}
    renderList();showCount();installContinuousStrip();
    if(items.length){select(0);maybePrefetchFromSelection();}else document.querySelector('#stage').innerHTML='<div class="empty">Aucun résultat pour ces filtres d’aperçu.</div>';
  }catch(e){if(e?.name==='AbortError')return;document.querySelector('#results').innerHTML='<div class="empty error">Échec recherche : '+esc(e.message)+'</div>';}
};

bindNav=function(){
  const p=document.querySelector('#prev'),n=document.querySelector('#next');
  if(p)p.onclick=()=>{let wanted=idx-1;while(wanted>=0&&isRuntimeRejected(items[wanted]?.stable_id))wanted--;if(wanted>=0)select(wanted);};
  if(n)n.onclick=async()=>{
    let wanted=idx+1;while(wanted<items.length&&isRuntimeRejected(items[wanted]?.stable_id))wanted++;
    if(wanted<items.length){select(wanted);maybePrefetchFromSelection();return;}
    while(hasMore&&wanted>=items.length){await loadMore('next-edge');wanted=idx+1;while(wanted<items.length&&isRuntimeRejected(items[wanted]?.stable_id))wanted++;if(wanted<items.length)break;}
    if(wanted<items.length){select(wanted);maybePrefetchFromSelection();}
  };
};

const baseSelect=select;
select=async function(i){
  if(i<0||i>=items.length)return;
  const gen=generation,sid=items[i]?.stable_id;
  if(isRuntimeRejected(sid)){const wanted=nextCandidateIndex(i+1);if(wanted>=0){setTimeout(()=>select(wanted),0);return;}}
  await baseSelect(i);
  if(gen!==generation){const current=idx;if(current>=0&&current<items.length)setTimeout(()=>select(current),0);return;}
  if(currentAsset?.stable_id!==sid){const current=idx;if(current>=0&&current<items.length)setTimeout(()=>select(current),0);return;}
  if(await autoSkipRuntimeFailure(i,sid,gen))return;
  try{window.WFGGResultStripSync?.('smooth')}catch{}
  maybePrefetchFromSelection();
};

function installStageLearning(){
  const stage=document.querySelector('#stage');if(!stage||stage.dataset.v35Learning==='1')return;stage.dataset.v35Learning='1';
  const inspect=()=>{
    const a=currentAsset;if(!a)return;
    if(stage.querySelector('.v33modelcanvas,canvas')){recordPreview(a,'visible','3d','canvas-mounted');return;}
    if(stage.querySelector('#assetImg')){recordPreview(a,'visible','2d','raster-decoded');return;}
    const text=String(stage.textContent||'');
    if(/Animation 3D non autonome|Composant 3D sans Mesh autonome|Effet 3D non autonome|Composant 3D non autonome/.test(text)){
      recordPreview(a,'nonautonomous','',text.slice(0,160));rejectRuntimeId(a.stable_id);
      if(currentPreviewFilter()==='previewable'){
        const at=idx;setTimeout(()=>{if(currentAsset?.stable_id!==a.stable_id)return;let wanted=nextCandidateIndex(at+1);if(wanted>=0)select(wanted);},40);
      }
      return;
    }
    const final=stage.querySelector('.errorbox[data-v34-final]');
    if(final){recordPreview(a,'unavailable','',final.textContent?.slice(0,180)||'final-preview-failure');rejectRuntimeId(a.stable_id);}
  };
  new MutationObserver(inspect).observe(stage,{childList:true,subtree:true});
}

const searchBtn=document.querySelector('#search');if(searchBtn)searchBtn.onclick=()=>runSearch();
const q=document.querySelector('#q');if(q)q.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();e.stopImmediatePropagation();runSearch();}},{capture:true});
const clear=document.querySelector('#clear');if(clear)clear.onclick=()=>{activeHeroQueryId='';activeHeroQueryLabel='';resetFilters(true);};

ensureHeroAliases();installContinuousStrip();installStageLearning();updateFilterSummary();
window.WFGGSearchCorrelation={
  state:()=>({generation,loaded:items.length,sourceTotal:sourceTotalMatches,scanned:loadedOffset,hasMore,queryToken,pageSize:PAGE_SIZE,mode:'continuous-lazy-stream-v35',autoSkipRuntimeFailures:AUTO_SKIP_RUNTIME_FAILURES,skippedRuntime:skippedRuntimeCount,heroQueryId:activeHeroQueryId,heroQueryLabel:activeHeroQueryLabel,heroAliasKeys:heroAliasMap.size,previewFilter:currentPreviewFilter(),previewRegistry:Object.keys(previewRegistry).length}),
  loadMore,maybePrefetchFromScroll,resolveHeroQuery,rejectRuntimeId,isRuntimeRejected,nextCandidateIndex,previewInfo,previewMatches,recordPreview,currentPreviewFilter
};
console.info('V35_PREVIEW_FILTER installed default=previewable learned='+Object.keys(previewRegistry).length);
})();
