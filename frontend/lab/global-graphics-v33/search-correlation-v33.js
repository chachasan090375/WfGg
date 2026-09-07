(()=>{
'use strict';

/* Search/result correlation layer for V33 mobile LAB.
   Hero free-text search is intentionally STRICT:
   Murphy / Audie / 50006 are the same hero key, but normal hero search returns only assets with
   direct evidence for that hero (western name, internal alias or numeric hero ID). Folder/bundle
   propagation remains available to explicit advanced hero filters, never to the default name search.
*/

const PAGE_SIZE=120;
const NAV_PREFETCH_REMAINING=18;
const SCROLL_PREFETCH_VIEWPORTS=2.0;
const AUTO_SKIP_RUNTIME_FAILURES=true;
let generation=0;
let activeController=null;
let loadedOffset=0;
let totalMatches=0;
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
    let links=(a.hero_links||[]);
    if(activeHeroQueryId){
      links=links.filter(h=>String(h.hero_id)===String(activeHeroQueryId)&&h.relation==='direct');
    }else{
      // Never present broad folder/bundle propagation as a definitive "Héros:" label.
      links=links.filter(h=>h.relation==='direct');
    }
    if(!links.length)return;
    const seen=new Set(),labels=[];
    for(const h of links){
      const key=String(h.hero_id||'');if(seen.has(key))continue;seen.add(key);
      labels.push(`${h.western_name||'Héros'} · #${h.hero_id}`);if(labels.length>=2)break;
    }
    if(labels.length){const s=document.createElement('span');s.className='hero-link-label';s.textContent='Héros : '+labels.join(' · ');card.appendChild(s);}
  });
};

function currentParams(offset=0){
  const p=params();
  if(activeHeroQueryId){
    p.delete('q');
    p.set('hero_id',String(activeHeroQueryId));
    // Critical: do not allow same-folder/same-bundle propagation to contaminate an exact hero query.
    p.set('hero_relation','direct');
  }
  p.set('limit',String(PAGE_SIZE));
  p.set('offset',String(offset));
  return p;
}

function showCount(){
  const el=document.querySelector('#resultCount');if(!el)return;
  el.textContent=totalMatches>items.length?`${items.length}/${totalMatches}`:String(totalMatches||items.length||0);
  el.title=hasMore?`${items.length} résultats chargés sur ${totalMatches}. Le reste se charge automatiquement.`:`${totalMatches||items.length||0} résultats dans la sélection.`;
  if(activeHeroQueryId)el.title+=` Recherche héros stricte: ${activeHeroQueryLabel} (#${activeHeroQueryId}).`;
}

async function fetchPage(offset,gen){
  const controller=new AbortController();
  if(offset===0){try{activeController?.abort();}catch{}activeController=controller;}
  const r=await fetch(API+'/search?'+currentParams(offset),{signal:controller.signal,cache:'no-store'});
  const d=await r.json();
  if(gen!==generation)return null;
  if(!r.ok)throw new Error(d.message||d.error||'recherche impossible');
  return d;
}

function preserveStripPosition(fn){
  const strip=document.querySelector('#results'),left=strip?.scrollLeft||0;
  const activeSid=currentAsset?.stable_id||items[idx]?.stable_id||'';
  fn();
  requestAnimationFrame(()=>{
    const s=document.querySelector('#results');if(!s)return;s.scrollLeft=left;
    if(activeSid){const cards=[...s.querySelectorAll('.card')],pos=items.findIndex(x=>x.stable_id===activeSid);if(pos>=0&&cards[pos])cards[pos].classList.add('active');}
  });
}

async function loadMore(reason='stream'){
  if(loadingMore||!hasMore)return false;
  loadingMore=true;const gen=generation,start=loadedOffset;
  try{
    const d=await fetchPage(start,gen);if(!d)return false;
    if(queryToken&&d.queryToken&&queryToken!==d.queryToken)return false;
    const existing=new Set(items.map(x=>x.stable_id));let added=0;
    for(const x of (d.items||[]))if(!existing.has(x.stable_id)){items.push(x);existing.add(x.stable_id);added++;}
    loadedOffset=Number(d.offset??start)+(d.items||[]).length;
    totalMatches=Number(d.total??totalMatches);hasMore=!!d.hasMore&&loadedOffset<totalMatches;
    if(added){preserveStripPosition(()=>renderList());showCount();}
    console.debug('V33_RESULT_STREAM',reason,'loaded',items.length,'total',totalMatches,'hasMore',hasMore);
    return added>0;
  }finally{loadingMore=false;}
}

function maybePrefetchFromSelection(){if(hasMore&&items.length-Math.max(0,idx)-1<=NAV_PREFETCH_REMAINING)loadMore('navigation-prefetch');}
function maybePrefetchFromScroll(){
  const strip=document.querySelector('#results');if(!strip||!hasMore||loadingMore)return;
  const remaining=strip.scrollWidth-strip.scrollLeft-strip.clientWidth;
  if(remaining<=strip.clientWidth*SCROLL_PREFETCH_VIEWPORTS)loadMore('horizontal-scroll');
}
function installContinuousStrip(){
  const strip=document.querySelector('#results');if(!strip||strip.dataset.v33Continuous==='1')return;
  strip.dataset.v33Continuous='1';
  strip.addEventListener('scroll',()=>{clearTimeout(scrollTimer);scrollTimer=setTimeout(maybePrefetchFromScroll,70);},{passive:true});
  strip.addEventListener('pointerup',()=>setTimeout(maybePrefetchFromScroll,80),{passive:true});
}

function runtimeFailureOnStage(){
  const stage=document.querySelector('#stage');if(!stage)return null;
  const box=stage.querySelector('.errorbox');if(!box)return null;
  return {title:box.querySelector('h3')?.textContent?.trim()||'Rendu indisponible',details:box.querySelector('#errorDetails')?.textContent?.trim()||''};
}
function rejectRuntimeId(sid){
  sid=String(sid||'');if(!sid)return false;
  if(!skippedRuntime.has(sid)){skippedRuntime.add(sid);skippedRuntimeCount++;}
  return true;
}
function isRuntimeRejected(sid){return skippedRuntime.has(String(sid||''));}
function nextCandidateIndex(from){
  for(let i=Math.max(0,from);i<items.length;i++){const sid=items[i]?.stable_id;if(sid&&!isRuntimeRejected(sid))return i;}
  return -1;
}
async function autoSkipRuntimeFailure(failedIndex,failedSid,gen){
  if(!AUTO_SKIP_RUNTIME_FAILURES||autoSkipBusy||gen!==generation)return false;
  const failure=runtimeFailureOnStage();if(!failure)return false;
  rejectRuntimeId(failedSid);
  console.warn('V33_RUNTIME_SKIPPED',failedSid,failure.title,failure.details);
  const stage=document.querySelector('#stage');if(stage)stage.innerHTML='<div class="empty">Recherche du prochain rendu disponible…</div>';
  autoSkipBusy=true;
  try{
    let wanted=nextCandidateIndex(failedIndex+1);
    while(wanted<0&&hasMore&&gen===generation){const added=await loadMore('runtime-failure-skip');if(!added)break;wanted=nextCandidateIndex(failedIndex+1);}
    if(gen!==generation)return true;
    if(wanted>=0){setTimeout(()=>select(wanted),0);return true;}
    for(let i=Math.min(failedIndex-1,items.length-1);i>=0;i--){const sid=items[i]?.stable_id;if(sid&&!isRuntimeRejected(sid)){setTimeout(()=>select(i),0);return true;}}
    if(stage)stage.innerHTML='<div class="empty">Aucun autre rendu décodable dans cette sélection.</div>';
    return true;
  }finally{autoSkipBusy=false;}
}

runSearch=async function(){
  updateFilterSummary();await ensureHeroAliases();
  const rawQuery=document.querySelector('#q')?.value?.trim()||'',hero=resolveHeroQuery(rawQuery);
  activeHeroQueryId=hero?String(hero.hero_id):'';activeHeroQueryLabel=hero?String(hero.western_name||rawQuery):'';
  if(hero)console.info('V34_HERO_QUERY_STRICT',rawQuery,'=>',activeHeroQueryLabel,'#'+activeHeroQueryId);
  const gen=++generation;
  idx=-1;currentAsset=null;currentModel?.destroy?.();currentModel=null;
  if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
  items=[];loadedOffset=0;totalMatches=0;hasMore=false;queryToken='';skippedRuntime=new Set();skippedRuntimeCount=0;autoSkipBusy=false;
  document.querySelector('#stage').innerHTML='<div class="empty">Recherche…</div>';
  try{
    const d=await fetchPage(0,gen);if(!d)return;
    items=d.items||[];loadedOffset=Number(d.offset||0)+items.length;totalMatches=Number(d.total??items.length);hasMore=!!d.hasMore&&loadedOffset<totalMatches;queryToken=d.queryToken||'';
    renderList();showCount();installContinuousStrip();
    if(items.length){select(0);maybePrefetchFromSelection();}else document.querySelector('#stage').innerHTML='<div class="empty">Aucun résultat pour ces filtres.</div>';
  }catch(e){if(e?.name==='AbortError')return;document.querySelector('#results').innerHTML='<div class="empty error">Échec recherche : '+esc(e.message)+'</div>';}
};

bindNav=function(){
  const p=document.querySelector('#prev'),n=document.querySelector('#next');
  if(p)p.onclick=()=>{let wanted=idx-1;while(wanted>=0&&isRuntimeRejected(items[wanted]?.stable_id))wanted--;if(wanted>=0)select(wanted);};
  if(n)n.onclick=async()=>{
    let wanted=idx+1;while(wanted<items.length&&isRuntimeRejected(items[wanted]?.stable_id))wanted++;
    if(wanted<items.length){select(wanted);maybePrefetchFromSelection();return;}
    if(hasMore&&await loadMore('next-edge')){wanted=idx+1;while(wanted<items.length&&isRuntimeRejected(items[wanted]?.stable_id))wanted++;if(wanted<items.length){select(wanted);maybePrefetchFromSelection();}}
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

const searchBtn=document.querySelector('#search');if(searchBtn)searchBtn.onclick=()=>runSearch();
const q=document.querySelector('#q');if(q)q.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();e.stopImmediatePropagation();runSearch();}},{capture:true});
const clear=document.querySelector('#clear');if(clear)clear.onclick=()=>{activeHeroQueryId='';activeHeroQueryLabel='';resetFilters(true);};

ensureHeroAliases();installContinuousStrip();
window.WFGGSearchCorrelation={
  state:()=>({generation,loaded:items.length,total:totalMatches,hasMore,queryToken,pageSize:PAGE_SIZE,mode:'continuous-lazy-stream',autoSkipRuntimeFailures:AUTO_SKIP_RUNTIME_FAILURES,skippedRuntime:skippedRuntimeCount,heroQueryId:activeHeroQueryId,heroQueryLabel:activeHeroQueryLabel,heroAliasKeys:heroAliasMap.size}),
  loadMore,maybePrefetchFromScroll,resolveHeroQuery,rejectRuntimeId,isRuntimeRejected,nextCandidateIndex
};
})();
