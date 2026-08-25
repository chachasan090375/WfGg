(() => {
  'use strict';
  /* WFGG_DESIGN_SYSTEM_PREVIEW_V2
     Premium preview-only shell. It applies shared classes, SVG iconography,
     brand lockups and normalized Portal return controls without touching app logic.
  */
  const path=location.pathname;
  const route=path.startsWith('/train')?'train':path.startsWith('/guides')?'guides':'portal';
  const root=document.documentElement;
  root.classList.add('wfgg-design-preview-v2',`wfgg-ds-${route}-v2`);
  root.dataset.wfggDesignSystem='preview-v2-premium';

  const labels={
    fr:{home:'Portail',portal:'WfGg',guides:'Guides',train:'Train',preview:'Charte premium V2'},
    it:{home:'Portale',portal:'WfGg',guides:'Guide',train:'Treno',preview:'Stile premium V2'},
    en:{home:'Portal',portal:'WfGg',guides:'Guides',train:'Train',preview:'Premium design V2'},
    es:{home:'Portal',portal:'WfGg',guides:'Guías',train:'Tren',preview:'Diseño premium V2'}
  };
  const lang=()=>{
    const raw=String(document.documentElement.lang||localStorage.getItem('wfgg_portal_language')||'fr').trim().toLowerCase().replace('_','-').split('-')[0];
    return labels[raw]?raw:'fr';
  };

  const paths={
    book:'<path d="M4.5 5.5A3.5 3.5 0 0 1 8 2h10a1.5 1.5 0 0 1 1.5 1.5V19H8a3.5 3.5 0 0 0-3.5 3.5V5.5Z"/><path d="M8 2v17"/><path d="M4.5 18.5A3.5 3.5 0 0 1 8 15h11.5"/>',
    train:'<path d="M6 17h12a2 2 0 0 0 2-2V6c0-2.2-2.7-4-8-4S4 3.8 4 6v9a2 2 0 0 0 2 2Z"/><path d="M7 21l2-4m8 4-2-4M7 7h10M8 12h.01M16 12h.01"/>',
    settings:'<path d="M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06-2.83 2.83-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21h-4v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06-2.83-2.83.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3v-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06 2.83-2.83.06.06A1.65 1.65 0 0 0 8.92 4a1.65 1.65 0 0 0 1-1.51V2h4v.49a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06 2.83 2.83-.06.06A1.65 1.65 0 0 0 19.4 9c.2.61.77 1.02 1.41 1.02H21v4h-.19c-.64 0-1.21.41-1.41 1Z"/>',
    user:'<circle cx="12" cy="8" r="4"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/>',
    logout:'<path d="M10 17l5-5-5-5M15 12H3M21 19V5a2 2 0 0 0-2-2h-5"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',
    home:'<path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10M9 20v-6h6v6"/>',
    season:'<path d="M12 3c4.5 4.8 6 8.2 4.5 10.3C15 15.4 12.9 14.8 12 14c-.9.8-3 1.4-4.5-.7C6 11.2 7.5 7.8 12 3Z"/><path d="M12 14v7M8 18h8"/>',
    compass:'<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2.3 4.7-4.7 2.3 2.3-4.7 4.7-2.3Z"/>',
    calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18"/>',
    swap:'<path d="M7 7h11l-3-3M17 17H6l3 3"/>',
    bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
    chart:'<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
    help:'<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.8 2.8 0 1 1 4.3 2.35c-1.05.68-1.8 1.13-1.8 2.65M12 17h.01"/>',
    history:'<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
    rotate:'<path d="M20 7h-6V1M4 17h6v6"/><path d="M5.1 9A8 8 0 0 1 18.5 5.5L20 7M4 17l1.5 1.5A8 8 0 0 0 18.9 15"/>',
    link:'<path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.15 1.15"/><path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.15-1.15"/>',
    arrow:'<path d="M5 12h14M14 7l5 5-5 5"/>',
    back:'<path d="M19 12H5M10 17l-5-5 5-5"/>',
    close:'<path d="M6 6l12 12M18 6 6 18"/>',
    check:'<path d="m5 12 4 4L19 6"/>',
    crown:'<path d="m3 7 4 4 5-7 5 7 4-4-2 11H5L3 7Z"/>',
    mail:'<path d="M3 5h18v14H3z"/><path d="m3 7 9 6 9-6"/>'
  };

  function icon(name,size=''){
    const body=paths[name]||paths.link;
    return `<span class="wfgg-icon ${size}" aria-hidden="true"><svg viewBox="0 0 24 24">${body}</svg></span>`;
  }
  function disc(name){return `<span class="wfgg-icon-disc">${icon(name,'lg')}</span>`}

  const emojiMap=[
    ['📚','book'],['🚂','train'],['🚆','train'],['⚙️','settings'],['⚙','settings'],['👤','user'],['ℹ️','info'],['ℹ','info'],['🔎','search'],['🔍','search'],['📅','calendar'],['🗓️','calendar'],['🗓','calendar'],['🔔','bell'],['📊','chart'],['📈','chart'],['👥','users'],['🔁','rotate'],['🧾','history'],['🎓','help'],['🔗','link'],['⭐','crown'],['✉️','mail'],['✉','mail'],['🧭','compass'],['🌴','season']
  ];

  function brandMarkup(moduleLabel){
    const t=labels[lang()];
    return `<span class="wfgg-brand-seal"><img src="/assets/wfgg-logo-mini.svg" alt=""></span><span class="wfgg-brand-copy"><b>${t.portal}</b><small>${moduleLabel||t.home}</small></span>${icon('back','xs')}`;
  }

  function ensurePreviewBadge(){
    if(document.querySelector('[data-wfgg-preview-badge-v2]'))return;
    const badge=document.createElement('div');
    badge.className='wfgg-preview-badge-v2';
    badge.dataset.wfggPreviewBadgeV2='1';
    badge.textContent=labels[lang()].preview;
    document.body.appendChild(badge);
  }

  function premiumPortal(){
    if(route!=='portal')return;
    const brand=document.querySelector('.brand-mark');
    if(brand&&!brand.dataset.wfggPremiumBrand){
      brand.dataset.wfggPremiumBrand='1';
      brand.innerHTML='<img src="/assets/wfgg-logo-mini.svg" alt="WfGg">';
    }
    const mods=[
      ['.module-card[data-module="guides"] .module-icon','book'],
      ['.module-card[data-module="train"] .module-icon','train'],
      ['.module-card.settings-card .module-icon','settings']
    ];
    mods.forEach(([sel,name])=>{
      const el=document.querySelector(sel);if(!el||el.dataset.wfggIconV2)return;
      el.dataset.wfggIconV2='1';el.innerHTML=disc(name);
    });
    document.querySelectorAll('.module-arrow').forEach(el=>{if(el.dataset.wfggIconV2)return;el.dataset.wfggIconV2='1';el.innerHTML=icon('arrow','sm')});
    const profile=document.querySelector('[data-action="profile"]>span:first-child');if(profile&&!profile.dataset.wfggIconV2){profile.dataset.wfggIconV2='1';profile.innerHTML=icon('user','sm')}
    const logout=document.querySelector('[data-action="logout"]>span:first-child');if(logout&&!logout.dataset.wfggIconV2){logout.dataset.wfggIconV2='1';logout.innerHTML=icon('logout','sm')}
    const info=document.querySelector('#profileRequiredBanner>span:first-child');if(info&&!info.dataset.wfggIconV2){info.dataset.wfggIconV2='1';info.innerHTML=icon('info','sm')}
    const search=document.querySelector('.member-search>span:first-child');if(search&&!search.dataset.wfggIconV2){search.dataset.wfggIconV2='1';search.innerHTML=icon('search','sm')}
    const back=document.querySelector('.members-back');if(back&&!back.dataset.wfggIconV2){back.dataset.wfggIconV2='1';back.innerHTML=icon('back','sm')}
  }

  function normalizeGuideBrand(){
    if(route!=='guides')return;
    document.querySelectorAll('.logo-mini img').forEach(img=>{img.src='/assets/wfgg-logo-mini.svg';img.alt='WfGg'});
    document.querySelectorAll('.portal-back').forEach(a=>{a.href='/';a.classList.add('wfgg-legacy-home-hidden')});
    const cards=[...document.querySelectorAll('.grid>.card')];
    cards.forEach(card=>{
      const target=card.querySelector('.icon');if(!target||target.dataset.wfggIconV2)return;
      const href=card.getAttribute('href')||'';
      const name=/season6/i.test(href)?'season':/interseason/i.test(href)?'compass':'book';
      target.dataset.wfggIconV2='1';target.innerHTML=disc(name);
    });
    document.querySelectorAll('.topic .ico,.icon-card .big').forEach(iconifyStandalone);
  }

  function ensureGuideHome(){
    if(route!=='guides')return;
    const top=document.querySelector('.top');
    if(top){
      if(top.querySelector('[data-wfgg-inline-home-v2]'))return;
      const a=document.createElement('a');
      a.href='/';a.className='wfgg-inline-home';a.dataset.wfggInlineHomeV2='1';a.setAttribute('aria-label',labels[lang()].home);
      a.innerHTML=brandMarkup(labels[lang()].guides);
      const spacer=top.querySelector('.spacer');
      if(spacer)top.insertBefore(a,spacer);else top.appendChild(a);
      return;
    }
    if(document.querySelector('[data-wfgg-module-home-v2]'))return;
    const a=document.createElement('a');
    a.href='/';a.className='wfgg-module-home';a.dataset.wfggModuleHomeV2='1';a.setAttribute('aria-label',labels[lang()].home);
    a.innerHTML=brandMarkup(labels[lang()].guides);
    const actions=document.querySelector('.portal-actions');
    if(actions){actions.innerHTML='';actions.appendChild(a)}else{a.style.position='fixed';a.style.top='12px';a.style.left='12px';a.style.zIndex='2147482000';document.body.appendChild(a)}
  }

  function ensureTrainHome(){
    if(route!=='train')return;
    let home=document.getElementById('brandHome');
    if(home){
      if(!home.dataset.wfggModuleHomeV2){home.dataset.wfggModuleHomeV2='1';home.classList.add('wfgg-module-home');home.innerHTML=brandMarkup(labels[lang()].train);home.setAttribute('aria-label',labels[lang()].home)}
      return;
    }
    if(document.querySelector('[data-wfgg-module-home-v2]'))return;
    home=document.createElement('a');home.href='/';home.className='wfgg-module-home';home.dataset.wfggModuleHomeV2='1';home.innerHTML=brandMarkup(labels[lang()].train);
    home.style.position='fixed';home.style.top='12px';home.style.left='12px';home.style.zIndex='2147482000';document.body.appendChild(home);
  }

  function emojiName(text){
    const s=String(text||'').trim();
    for(const [emoji,name] of emojiMap)if(s.startsWith(emoji))return {emoji,name};
    return null;
  }
  function iconifyHeading(el){
    if(!el||el.dataset.wfggIconifiedV2||el.children.length>0)return;
    const hit=emojiName(el.textContent);if(!hit)return;
    const rest=el.textContent.trim().slice(hit.emoji.length).trim();if(!rest)return;
    el.dataset.wfggIconifiedV2='1';el.classList.add('wfgg-iconified-heading');el.innerHTML=icon(hit.name,'sm')+`<span>${escapeHtml(rest)}</span>`;
  }
  function iconifyStandalone(el){
    if(!el||el.dataset.wfggIconifiedV2)return;
    const hit=emojiName(el.textContent);if(!hit)return;
    const rest=el.textContent.trim().slice(hit.emoji.length).trim();
    el.dataset.wfggIconifiedV2='1';el.classList.add('wfgg-iconified-standalone');
    el.innerHTML=rest?icon(hit.name,'sm')+`<span>${escapeHtml(rest)}</span>`:icon(hit.name,'lg');
  }
  function escapeHtml(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}

  function normalizeTrainIconography(){
    if(route!=='train')return;
    document.querySelectorAll('h1,h2,h3,.section-title h2,.section-title h3').forEach(iconifyHeading);
    document.querySelectorAll('.analytics-group-icon>span,.overview-icon-card>span,.history-import-kpis>div>span,.public-help-icon').forEach(iconifyStandalone);
  }

  function markReady(){document.body.classList.add('wfgg-design-ready-v2')}

  function refreshLocalizedChrome(){
    const t=labels[lang()];
    const badge=document.querySelector('[data-wfgg-preview-badge-v2]');if(badge)badge.textContent=t.preview;
    const guide=document.querySelector('[data-wfgg-inline-home-v2],[data-wfgg-module-home-v2]');
    if(guide&&route==='guides')guide.innerHTML=brandMarkup(t.guides);
    const train=document.getElementById('brandHome')||document.querySelector('[data-wfgg-module-home-v2]');
    if(train&&route==='train')train.innerHTML=brandMarkup(t.train);
  }

  function scan(){
    if(!document.body)return;
    ensurePreviewBadge();
    premiumPortal();
    normalizeGuideBrand();
    ensureGuideHome();
    ensureTrainHome();
    normalizeTrainIconography();
    markReady();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',scan,{once:true});else scan();

  let queued=false;
  new MutationObserver(()=>{
    if(queued)return;queued=true;
    requestAnimationFrame(()=>{queued=false;scan()});
  }).observe(document.documentElement,{childList:true,subtree:true});

  document.addEventListener('click',event=>{
    const target=event.target.closest('[data-lang],[data-set-lang],.language-strip button,.lang a');
    if(target)setTimeout(refreshLocalizedChrome,0);
  },true);
  document.addEventListener('change',event=>{
    const el=event.target;
    if(el&&/lang/i.test(`${el.id||''} ${el.name||''} ${el.className||''}`))setTimeout(refreshLocalizedChrome,0);
  },true);

  window.WFGG_DESIGN_SYSTEM_PREVIEW={version:'v2-premium',route,icons:Object.keys(paths)};
})();
