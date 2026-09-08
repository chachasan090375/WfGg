(()=>{
'use strict';
/* V39.14 — real badge row, not an overlay.
   The native render badge and linked-animation badge are reparented into one flex row.
   The 2D artwork is positioned below that row, so badges cannot cover or crop the image.
*/
const VERSION='39.14';
const STAGE_ID='stage';
const LINK_ID='wfggV39Badge';
const ROW_ID='wfggV3914BadgeRow';
const TOP=9, EDGE=9, GAP=7, ART_TOP=54;

function stage(){return document.getElementById(STAGE_ID);}
function linked(){return document.getElementById(LINK_ID);}
function imp(el,k,v){try{el.style.setProperty(k,String(v),'important');}catch{}}

function nativeBadge(st,row){
  if(row){const x=row.querySelector('.badge');if(x)return x;}
  if(!st)return null;
  for(const el of Array.from(st.children||[])){
    if(el?.id===LINK_ID||el?.id===ROW_ID)continue;
    if(el?.classList?.contains('badge'))return el;
  }
  return st.querySelector(':scope > .badge');
}

function ensureRow(st){
  let row=document.getElementById(ROW_ID);
  if(row&&row.parentElement!==st){try{row.remove();}catch{}row=null;}
  if(!row){
    row=document.createElement('div');row.id=ROW_ID;
    st.insertBefore(row,st.firstChild||null);
  }
  return row;
}

function restoreArtwork(st){
  const img=st?.querySelector('#assetImg');
  if(img){
    for(const k of ['position','top','left','right','bottom','width','height','max-width','max-height','object-fit','object-position']){
      try{img.style.removeProperty(k);}catch{}
    }
  }
  st?.classList.remove('wfgg-v3914-real-badge-row');
}

function apply(){
  const st=stage();if(!st)return false;
  const box=linked();
  const img=st.querySelector('#assetImg');
  if(!box||!box.querySelector('button')||!img){
    document.getElementById(ROW_ID)?.remove();
    restoreArtwork(st);
    return false;
  }

  const row=ensureRow(st);
  const rb=nativeBadge(st,row);
  if(!rb)return false;
  const btn=box.querySelector('button');

  /* Physically put both badges in the same DOM row. */
  if(rb.parentElement!==row)row.appendChild(rb);
  if(box.parentElement!==row)row.appendChild(box);
  st.classList.add('wfgg-v3914-real-badge-row');

  /* Row itself. */
  imp(row,'position','absolute');imp(row,'top',TOP+'px');imp(row,'left',EDGE+'px');imp(row,'right',EDGE+'px');
  imp(row,'height','34px');imp(row,'display','flex');imp(row,'align-items','center');imp(row,'gap',GAP+'px');
  imp(row,'z-index','70');imp(row,'overflow','hidden');imp(row,'pointer-events','none');

  /* Native RENDU badge becomes the fixed left chip. */
  imp(rb,'position','static');imp(rb,'inset','auto');imp(rb,'top','auto');imp(rb,'left','auto');imp(rb,'right','auto');imp(rb,'bottom','auto');
  imp(rb,'display','block');imp(rb,'flex','0 0 auto');imp(rb,'width','auto');imp(rb,'max-width','52%');
  imp(rb,'margin','0');imp(rb,'padding','5px 8px');imp(rb,'white-space','nowrap');imp(rb,'overflow','hidden');imp(rb,'text-overflow','ellipsis');
  imp(rb,'pointer-events','none');

  /* Animation chip consumes only the remaining space. Old V39.11 top/left !important rules are neutralised here. */
  imp(box,'position','static');imp(box,'inset','auto');imp(box,'top','auto');imp(box,'left','auto');imp(box,'right','auto');imp(box,'bottom','auto');
  imp(box,'display','block');imp(box,'flex','1 1 0');imp(box,'min-width','0');imp(box,'width','auto');imp(box,'max-width','none');
  imp(box,'height','auto');imp(box,'margin','0');imp(box,'padding','0');imp(box,'transform','none');imp(box,'overflow','hidden');imp(box,'pointer-events','auto');

  imp(btn,'display','block');imp(btn,'box-sizing','border-box');imp(btn,'width','100%');imp(btn,'min-width','0');imp(btn,'max-width','100%');
  imp(btn,'height','auto');imp(btn,'min-height','0');imp(btn,'margin','0');imp(btn,'padding','5px 8px');imp(btn,'border-radius','8px');
  imp(btn,'font','700 11px/1.2 system-ui,sans-serif');imp(btn,'white-space','nowrap');imp(btn,'overflow','hidden');imp(btn,'text-overflow','ellipsis');
  btn.title=(btn.textContent||'').trim()+' — toucher pour ouvrir le diagnostic';

  /* The artwork now has its own area BELOW the badge row. */
  imp(img,'position','absolute');imp(img,'top',ART_TOP+'px');imp(img,'left','0');imp(img,'right','0');imp(img,'bottom','0');
  imp(img,'width','100%');imp(img,'height','calc(100% - '+ART_TOP+'px)');imp(img,'max-width','100%');imp(img,'max-height','calc(100% - '+ART_TOP+'px)');
  imp(img,'object-fit','contain');imp(img,'object-position','center center');

  row.dataset.wfggLayout='real-flex-row';
  box.dataset.wfggLayout='real-flex-row';
  return true;
}

function installStyle(){
  if(document.getElementById('wfgg-v3914-style'))return;
  const s=document.createElement('style');s.id='wfgg-v3914-style';s.textContent=`
#stage.wfgg-v3914-real-badge-row{position:relative!important;overflow:hidden!important;}
#wfggV3914BadgeRow>#wfggV39Badge button{background:rgba(17,22,34,.96)!important;color:#edf1f8!important;border:1px solid #46546d!important;box-shadow:none!important;backdrop-filter:none!important;}
#wfggV3914BadgeRow>#wfggV39Badge button[data-state="animated-script"]{border-color:#8f79c9!important;color:#f1eaff!important;}
#wfggV3914BadgeRow>#wfggV39Badge button[data-state="animated-clip"],#wfggV3914BadgeRow>#wfggV39Badge button[data-state="animated-transform"]{border-color:#6689b8!important;color:#e7f2ff!important;}
`;
  document.head.appendChild(s);
}

function boot(){
  installStyle();apply();
  window.addEventListener('resize',()=>requestAnimationFrame(apply),{passive:true});
  new MutationObserver(()=>requestAnimationFrame(apply)).observe(document.body,{childList:true,subtree:true});
  setInterval(apply,250);
  window.WFGGAnimationBadgeLayoutV3913={version:VERSION,apply};
  console.info('V39_14_BADGE_LAYOUT installed real-flex-row=ON artwork-top=54 overlap=IMPOSSIBLE');
}
boot();
})();
