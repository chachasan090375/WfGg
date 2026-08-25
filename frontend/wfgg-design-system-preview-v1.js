(() => {
  'use strict';
  /* WFGG_DESIGN_SYSTEM_PREVIEW_V1
     Preview-only shell. It adds common classes, preview marker, common logo treatment
     and a standard return-to-Portal control to proxied modules.
  */
  const path=location.pathname;
  const route=path.startsWith('/train')?'train':path.startsWith('/guides')?'guides':'portal';
  const root=document.documentElement;
  root.classList.add('wfgg-design-preview',`wfgg-ds-${route}`);
  root.dataset.wfggDesignSystem='preview-v1';

  const labels={
    fr:{home:'Portail WfGg',preview:'Charte preview V1'},
    it:{home:'Portale WfGg',preview:'Anteprima stile V1'},
    en:{home:'WfGg Portal',preview:'Design preview V1'},
    es:{home:'Portal WfGg',preview:'Vista previa V1'}
  };
  const lang=()=>{
    const raw=String(document.documentElement.lang||localStorage.getItem('wfgg_portal_language')||'fr').toLowerCase().split('-')[0];
    return labels[raw]?raw:'fr';
  };

  function commonHomeMarkup(){
    const t=labels[lang()];
    return `<img src="/assets/wfgg-logo-mini.svg" alt=""><span>${t.home}</span><span class="wfgg-home-arrow" aria-hidden="true">←</span>`;
  }

  function ensurePreviewBadge(){
    if(document.querySelector('[data-wfgg-preview-badge]'))return;
    const badge=document.createElement('div');
    badge.className='wfgg-preview-badge';
    badge.dataset.wfggPreviewBadge='v1';
    badge.textContent=labels[lang()].preview;
    document.body.appendChild(badge);
  }

  function normalizeGuideBrand(){
    if(route!=='guides')return;
    document.querySelectorAll('.logo-mini img').forEach(img=>{
      img.src='/assets/wfgg-logo-mini.svg';
      img.alt='WfGg';
    });
    document.querySelectorAll('.portal-back').forEach(a=>{
      a.href='/';
      a.classList.add('wfgg-home-source');
    });
  }

  function ensureModuleHome(){
    if(route==='portal')return;
    let home=document.querySelector('[data-wfgg-unified-home]');
    if(home)return;

    if(route==='train'){
      const candidate=document.getElementById('brandHome');
      if(candidate && candidate.tagName==='A')home=candidate;
    }

    if(!home){
      home=document.createElement('a');
      document.body.appendChild(home);
    }
    home.dataset.wfggUnifiedHome='v1';
    home.classList.add('wfgg-unified-home');
    home.href='/';
    home.setAttribute('aria-label',labels[lang()].home);
    home.innerHTML=commonHomeMarkup();
  }

  function markMajorSurfaces(){
    document.body.classList.add('wfgg-design-body','wfgg-design-ready');
    if(route==='portal'){
      document.querySelectorAll('.module-card').forEach((el,i)=>el.dataset.wfggSurface=`module-${i+1}`);
    }
  }

  function refreshLocalizedChrome(){
    const badge=document.querySelector('[data-wfgg-preview-badge]');
    if(badge)badge.textContent=labels[lang()].preview;
    const home=document.querySelector('[data-wfgg-unified-home]');
    if(home){
      home.setAttribute('aria-label',labels[lang()].home);
      home.innerHTML=commonHomeMarkup();
    }
  }

  function scan(){
    if(!document.body)return;
    ensurePreviewBadge();
    normalizeGuideBrand();
    ensureModuleHome();
    markMajorSurfaces();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',scan,{once:true});
  else scan();

  let queued=false;
  new MutationObserver(()=>{
    if(queued)return;
    queued=true;
    queueMicrotask(()=>{queued=false;scan();});
  }).observe(document.documentElement,{childList:true,subtree:true});

  document.addEventListener('click',event=>{
    const target=event.target.closest('[data-lang],[data-set-lang],.language-strip button,.lang a');
    if(target)setTimeout(refreshLocalizedChrome,0);
  },true);
  document.addEventListener('change',event=>{
    const el=event.target;
    if(el && /lang/i.test(`${el.id||''} ${el.name||''} ${el.className||''}`))setTimeout(refreshLocalizedChrome,0);
  },true);

  window.WFGG_DESIGN_SYSTEM_PREVIEW={version:'v1',route};
})();
