(()=>{
'use strict';

/* Search/result correlation layer for V33 mobile LAB.
   The result strip is an UNBOUNDED LAZY STREAM over the current search, not a fixed 60/100-card sample.
   Pages are transport chunks only: they are appended automatically while the user scrolls or navigates.
   Old searches/renders are invalidated so only the current query can drive the visible selection. */

const PAGE_SIZE=120;                  // server maximum; transport size, NOT a result cap
const NAV_PREFETCH_REMAINING=18;      // prefetch before Previous/Next reaches the loaded edge
const SCROLL_PREFETCH_VIEWPORTS=2.0;  // append when less than 2 strip widths remain
let generation=0;
let activeController=null;
let loadedOffset=0;
let totalMatches=0;
let hasMore=false;
let loadingMore=false;
let queryToken='';
let scrollTimer=0;

function currentParams(offset=0){
  const p=params();
  p.set('limit',String(PAGE_SIZE));
  p.set('offset',String(offset));
  return p;
}

function showCount(){
  const el=document.querySelector('#resultCount');
  if(!el)return;
  if(totalMatches>items.length)el.textContent=`${items.length}/${totalMatches}`;
  else el.textContent=String(totalMatches||items.length||0);
  el.title=hasMore
    ?`${items.length} résultats chargés sur ${totalMatches}. Le reste se charge automatiquement.`
    :`${totalMatches||items.length||0} résultats dans la sélection.`;
}

async function fetchPage(offset,gen){
  const controller=new AbortController();
  if(offset===0){
    try{activeController?.abort();}catch{}
    activeController=controller;
  }
  const r=await fetch(API+'/search?'+currentParams(offset),{signal:controller.signal,cache:'no-store'});
  const d=await r.json();
  if(gen!==generation)return null;
  if(!r.ok)throw new Error(d.message||d.error||'recherche impossible');
  return d;
}

function preserveStripPosition(fn){
  const strip=document.querySelector('#results');
  const left=strip?.scrollLeft||0;
  const activeSid=currentAsset?.stable_id||items[idx]?.stable_id||'';
  fn();
  requestAnimationFrame(()=>{
    const s=document.querySelector('#results');
    if(!s)return;
    // Appending pages must never jump back to the active card. Selection itself handles centering.
    s.scrollLeft=left;
    if(activeSid){
      const cards=[...s.querySelectorAll('.card')];
      const pos=items.findIndex(x=>x.stable_id===activeSid);
      if(pos>=0&&cards[pos])cards[pos].classList.add('active');
    }
  });
}

async function loadMore(reason='stream'){
  if(loadingMore||!hasMore)return false;
  loadingMore=true;const gen=generation;const start=loadedOffset;
  try{
    const d=await fetchPage(start,gen);if(!d)return false;
    if(queryToken&&d.queryToken&&queryToken!==d.queryToken)return false;
    const existing=new Set(items.map(x=>x.stable_id));
    let added=0;
    for(const x of (d.items||[])){
      if(!existing.has(x.stable_id)){items.push(x);existing.add(x.stable_id);added++;}
    }
    loadedOffset=Number(d.offset??start)+(d.items||[]).length;
    totalMatches=Number(d.total??totalMatches);
    hasMore=!!d.hasMore && loadedOffset<totalMatches;
    if(added){preserveStripPosition(()=>renderList());showCount();}
    console.debug('V33_RESULT_STREAM',reason,'loaded',items.length,'total',totalMatches,'hasMore',hasMore);
    return added>0;
  }finally{loadingMore=false;}
}

function maybePrefetchFromSelection(){
  if(hasMore && items.length-Math.max(0,idx)-1<=NAV_PREFETCH_REMAINING)loadMore('navigation-prefetch');
}

function maybePrefetchFromScroll(){
  const strip=document.querySelector('#results');
  if(!strip||!hasMore||loadingMore)return;
  const remaining=strip.scrollWidth-strip.scrollLeft-strip.clientWidth;
  if(remaining<=strip.clientWidth*SCROLL_PREFETCH_VIEWPORTS)loadMore('horizontal-scroll');
}

function installContinuousStrip(){
  const strip=document.querySelector('#results');if(!strip||strip.dataset.v33Continuous==='1')return;
  strip.dataset.v33Continuous='1';
  strip.addEventListener('scroll',()=>{
    clearTimeout(scrollTimer);
    scrollTimer=setTimeout(maybePrefetchFromScroll,70);
  },{passive:true});
  // Wheel/trackpad and touch momentum can stop between scroll events; recheck after pointer release.
  strip.addEventListener('pointerup',()=>setTimeout(maybePrefetchFromScroll,80),{passive:true});
}

runSearch=async function(){
  updateFilterSummary();
  const gen=++generation;
  idx=-1;currentAsset=null;currentModel?.destroy?.();currentModel=null;
  if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
  items=[];loadedOffset=0;totalMatches=0;hasMore=false;queryToken='';
  document.querySelector('#stage').innerHTML='<div class="empty">Recherche…</div>';
  try{
    const d=await fetchPage(0,gen);if(!d)return;
    items=d.items||[];
    loadedOffset=Number(d.offset||0)+items.length;
    totalMatches=Number(d.total??items.length);
    hasMore=!!d.hasMore && loadedOffset<totalMatches;
    queryToken=d.queryToken||'';
    renderList();showCount();installContinuousStrip();
    if(items.length){select(0);maybePrefetchFromSelection();}
    else document.querySelector('#stage').innerHTML='<div class="empty">Aucun résultat pour ces filtres.</div>';
  }catch(e){
    if(e?.name==='AbortError')return;
    document.querySelector('#results').innerHTML='<div class="empty error">Échec recherche : '+esc(e.message)+'</div>';
  }
};

bindNav=function(){
  const p=document.querySelector('#prev'),n=document.querySelector('#next');
  if(p)p.onclick=()=>{if(idx>0)select(idx-1);};
  if(n)n.onclick=async()=>{
    const wanted=idx+1;
    if(wanted<items.length){select(wanted);maybePrefetchFromSelection();return;}
    if(hasMore&&await loadMore('next-edge')&&wanted<items.length){select(wanted);maybePrefetchFromSelection();}
  };
};

// Prevent an old asynchronous render/model response from becoming visible after a new search.
const baseSelect=select;
select=async function(i){
  if(i<0||i>=items.length)return;
  const gen=generation;const sid=items[i]?.stable_id;
  await baseSelect(i);
  if(gen!==generation){
    const current=idx;if(current>=0&&current<items.length)setTimeout(()=>select(current),0);return;
  }
  if(currentAsset?.stable_id!==sid){
    const current=idx;if(current>=0&&current<items.length)setTimeout(()=>select(current),0);return;
  }
  try{window.WFGGResultStripSync?.('smooth')}catch{}
  maybePrefetchFromSelection();
};

const searchBtn=document.querySelector('#search');if(searchBtn)searchBtn.onclick=()=>runSearch();
const q=document.querySelector('#q');if(q){
  q.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();e.stopImmediatePropagation();runSearch();}},{capture:true});
}
const clear=document.querySelector('#clear');if(clear)clear.onclick=()=>resetFilters(true);

installContinuousStrip();
window.WFGGSearchCorrelation={
  state:()=>({generation,loaded:items.length,total:totalMatches,hasMore,queryToken,pageSize:PAGE_SIZE,mode:'continuous-lazy-stream'}),
  loadMore,
  maybePrefetchFromScroll
};
})();
