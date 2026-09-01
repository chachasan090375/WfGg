(()=>{
'use strict';

/* Search/result correlation layer for V33 mobile LAB.
   - each new search invalidates older async work;
   - only the current result set drives the carousel;
   - Previous/Next can transparently fetch the next page instead of stopping at 100 rows;
   - result count shows loaded/total so the user knows what is actually being browsed. */

const PAGE_SIZE=60;
let generation=0;
let activeController=null;
let loadedOffset=0;
let totalMatches=0;
let hasMore=false;
let loadingMore=false;
let queryToken='';

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

runSearch=async function(){
  updateFilterSummary();
  const gen=++generation;
  idx=-1;currentAsset=null;currentModel?.destroy?.();currentModel=null;
  if(currentUrl){try{URL.revokeObjectURL(currentUrl)}catch{}currentUrl=null;}
  items=[];loadedOffset=0;totalMatches=0;hasMore=false;queryToken='';
  document.querySelector('#stage').innerHTML='<div class="empty">Recherche…</div>';
  try{
    const d=await fetchPage(0,gen);if(!d)return;
    items=d.items||[];loadedOffset=items.length;totalMatches=Number(d.total??items.length);hasMore=!!d.hasMore;queryToken=d.queryToken||'';
    renderList();showCount();
    if(items.length)select(0);else document.querySelector('#stage').innerHTML='<div class="empty">Aucun résultat pour ces filtres.</div>';
  }catch(e){
    if(e?.name==='AbortError')return;
    document.querySelector('#results').innerHTML='<div class="empty error">Échec recherche : '+esc(e.message)+'</div>';
  }
};

async function loadMore(){
  if(loadingMore||!hasMore)return false;
  loadingMore=true;const gen=generation;
  try{
    const d=await fetchPage(loadedOffset,gen);if(!d)return false;
    if(queryToken&&d.queryToken&&queryToken!==d.queryToken)return false;
    const existing=new Set(items.map(x=>x.stable_id));
    for(const x of (d.items||[]))if(!existing.has(x.stable_id)){items.push(x);existing.add(x.stable_id);}
    loadedOffset=Number(d.offset||loadedOffset)+(d.items||[]).length;
    totalMatches=Number(d.total??totalMatches);hasMore=!!d.hasMore;
    renderList();showCount();return true;
  }finally{loadingMore=false;}
}

bindNav=function(){
  const p=document.querySelector('#prev'),n=document.querySelector('#next');
  if(p)p.onclick=()=>idx>0&&select(idx-1);
  if(n)n.onclick=async()=>{
    const wanted=idx+1;
    if(wanted<items.length){select(wanted);return;}
    if(hasMore&&await loadMore()&&wanted<items.length)select(wanted);
  };
};

// Prevent an old asynchronous render/model response from replacing the stage after a new
// search has already selected a different item. We keep the existing rendering function but
// discard its late UI result by restoring the current asset if necessary.
const baseSelect=select;
select=async function(i){
  if(i<0||i>=items.length)return;
  const gen=generation;const sid=items[i]?.stable_id;
  await baseSelect(i);
  if(gen!==generation)return;
  if(currentAsset?.stable_id!==sid)return;
  try{window.WFGGResultStripSync?.('smooth')}catch{}
};

const searchBtn=document.querySelector('#search');if(searchBtn)searchBtn.onclick=()=>runSearch();
const q=document.querySelector('#q');if(q){
  q.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();e.stopImmediatePropagation();runSearch();}},{capture:true});
}
const clear=document.querySelector('#clear');if(clear)clear.onclick=()=>resetFilters(true);

window.WFGGSearchCorrelation={
  state:()=>({generation,loaded:items.length,total:totalMatches,hasMore,queryToken}),
  loadMore
};
})();
