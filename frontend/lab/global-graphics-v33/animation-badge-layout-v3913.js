(()=>{
'use strict';
/* V39.13 — definitive mobile badge row.
   The render badge and linked-animation badge share a reserved top gutter in #stage.
   The artwork is laid out below that gutter, so neither badge can cover/crop the image.
*/
const VERSION='39.13';
const STAGE_ID='stage';
const LINK_ID='wfggV39Badge';
const EDGE=9,GAP=7,GUTTER=54;

function stage(){return document.getElementById(STAGE_ID);}
function linked(){return document.getElementById(LINK_ID);}
function nativeBadge(st){
  if(!st)return null;
  for(const el of Array.from(st.children||[])){
    if(el?.id===LINK_ID)continue;
    if(el?.classList?.contains('badge'))return el;
  }
  return st.querySelector(':scope > .badge');
}
function imp(el,k,v){try{el.style.setProperty(k,String(v),'important');}catch{}}
function clearLayout(st){
  if(!st)return;
  st.classList.remove('wfgg-v3913-badge-row');
  try{st.style.removeProperty('padding-top');}catch{}
}
function apply(){
  const st=stage();if(!st)return false;
  const box=linked();
  if(!box){clearLayout(st);return false;}
  const btn=box.querySelector('button');
  if(!btn){clearLayout(st);return false;}

  st.classList.add('wfgg-v3913-badge-row');
  /* Reserve physical room for both badges: image content begins below this row. */
  imp(st,'padding-top',GUTTER+'px');

  const rb=nativeBadge(st);
  let left=EDGE,top=EDGE;
  if(rb){
    left=Math.max(EDGE,Math.round((Number(rb.offsetLeft)||EDGE)+(Number(rb.offsetWidth)||0)+GAP));
    top=Math.max(EDGE,Math.round(Number(rb.offsetTop)||EDGE));
  }
  let avail=Math.floor(st.clientWidth-left-EDGE);
  avail=Math.max(64,avail);

  imp(box,'position','absolute');imp(box,'left',left+'px');imp(box,'top',top+'px');
  imp(box,'right','auto');imp(box,'bottom','auto');imp(box,'width',avail+'px');
  imp(box,'max-width',avail+'px');imp(box,'height','auto');imp(box,'margin','0');
  imp(box,'padding','0');imp(box,'transform','none');imp(box,'z-index','60');imp(box,'overflow','hidden');

  imp(btn,'display','block');imp(btn,'box-sizing','border-box');imp(btn,'width','100%');
  imp(btn,'min-width','0');imp(btn,'max-width','100%');imp(btn,'min-height','0');
  imp(btn,'padding','5px 8px');imp(btn,'margin','0');imp(btn,'border-radius','8px');
  imp(btn,'font','700 11px/1.2 system-ui,sans-serif');imp(btn,'white-space','nowrap');
  imp(btn,'overflow','hidden');imp(btn,'text-overflow','ellipsis');
  btn.title=(btn.textContent||'').trim()+' — toucher pour ouvrir le diagnostic';

  /* Keep the actual preview inside the content box below the reserved gutter. */
  const img=st.querySelector(':scope > img');
  if(img){imp(img,'width','100%');imp(img,'height','100%');imp(img,'object-fit','contain');imp(img,'object-position','center center');}
  box.dataset.wfggLayout='reserved-top-row';
  return true;
}

function installStyle(){
  if(document.getElementById('wfgg-v3913-style'))return;
  const s=document.createElement('style');s.id='wfgg-v3913-style';
  s.textContent=`
#stage.wfgg-v3913-badge-row{box-sizing:border-box!important;}
#stage.wfgg-v3913-badge-row>#wfggV39Badge{pointer-events:auto!important;}
#stage.wfgg-v3913-badge-row>#wfggV39Badge button{background:rgba(17,22,34,.96)!important;color:#edf1f8!important;border:1px solid #46546d!important;box-shadow:none!important;}
#stage.wfgg-v3913-badge-row>#wfggV39Badge button[data-state="animated-script"]{border-color:#8f79c9!important;color:#f1eaff!important;}
#stage.wfgg-v3913-badge-row>#wfggV39Badge button[data-state="animated-clip"],#stage.wfgg-v3913-badge-row>#wfggV39Badge button[data-state="animated-transform"]{border-color:#6689b8!important;color:#e7f2ff!important;}
`;
  document.head.appendChild(s);
}
function boot(){
  installStyle();apply();
  window.addEventListener('resize',()=>requestAnimationFrame(apply),{passive:true});
  new MutationObserver(()=>requestAnimationFrame(apply)).observe(document.body,{childList:true,subtree:true});
  setInterval(apply,250);
  window.WFGGAnimationBadgeLayoutV3913={version:VERSION,apply};
  console.info('V39_13_BADGE_LAYOUT installed same-row=ON reserved-gutter=54 artwork-overlap=OFF');
}
boot();
})();