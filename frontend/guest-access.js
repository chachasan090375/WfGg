/* WFGG_GUEST_GUIDES_ONLY_V1 */
(()=>{
  'use strict';
  const GUEST_CODE='000000';
  const GUEST_KEY='wfgg_portal_guest_v1';
  const TOKEN_KEY='wfgg_portal_session';
  const LANG_KEY='wfgg_portal_language';
  const isGuest=()=>localStorage.getItem(GUEST_KEY)==='1';
  const lang=()=>['fr','it','en','es'].includes((localStorage.getItem(LANG_KEY)||'').slice(0,2))?(localStorage.getItem(LANG_KEY)||'fr').slice(0,2):'fr';
  const words={
    fr:{name:'Invité',welcome:'Accès invité · Guides en lecture seule',logout:'Déconnexion'},
    it:{name:'Ospite',welcome:'Accesso ospite · Guide in sola lettura',logout:'Disconnetti'},
    en:{name:'Guest',welcome:'Guest access · Guides are read-only',logout:'Sign out'},
    es:{name:'Invitado',welcome:'Acceso invitado · Guías en solo lectura',logout:'Cerrar sesión'}
  };
  const setText=(el,value)=>{if(el&&el.textContent!==value)el.textContent=value;};
  function setGuest(on){
    if(on){localStorage.setItem(GUEST_KEY,'1');localStorage.removeItem(TOKEN_KEY);document.cookie='wfgg_guest=1; Path=/; SameSite=Lax; Secure';}
    else{localStorage.removeItem(GUEST_KEY);document.cookie='wfgg_guest=; Path=/; Max-Age=0; SameSite=Lax; Secure';}
  }
  function policy(){
    if(!isGuest())return;
    const w=words[lang()]||words.fr;
    document.getElementById('bootView')?.classList.add('hidden');
    document.getElementById('authView')?.classList.add('hidden');
    document.getElementById('portalView')?.classList.remove('hidden');
    setText(document.getElementById('heroName'),w.name);
    setText(document.getElementById('homeWelcome'),w.welcome);
    document.getElementById('profileRequiredBanner')?.classList.add('hidden');
    document.getElementById('profileChip')?.classList.add('hidden');
    document.getElementById('profileMenu')?.classList.add('hidden');
    document.querySelectorAll('[data-module]').forEach(el=>el.classList.toggle('hidden',el.dataset.module!=='guides'));
    document.querySelectorAll('.settings-card,[data-action="settings"],[data-action="profile"]').forEach(el=>el.classList.add('hidden'));
    const guides=document.getElementById('guidesModuleLink'); if(guides)guides.href='/guides/?lang='+lang();
    let out=document.getElementById('wfggGuestLogout');
    if(!out){
      out=document.createElement('button');out.id='wfggGuestLogout';out.type='button';out.className='secondary-button';out.dataset.guestLogout='1';
      const anchor=document.querySelector('.home-profile-anchor')||document.querySelector('.home-welcome-row');
      anchor?.appendChild(out);
    }
    setText(out,w.logout);
  }
  document.getElementById('authForm')?.addEventListener('submit',e=>{
    const input=document.getElementById('authCode');
    if((input?.value||'').trim()!==GUEST_CODE)return;
    e.preventDefault();e.stopImmediatePropagation();
    setGuest(true);if(input)input.value='';policy();window.scrollTo({top:0,left:0,behavior:'auto'});
  },true);
  document.addEventListener('click',e=>{
    if(!isGuest())return;
    const logout=e.target.closest('[data-guest-logout]');
    if(logout){e.preventDefault();e.stopImmediatePropagation();setGuest(false);location.replace('/');return;}
    const mod=e.target.closest('[data-module]');
    if(mod&&mod.dataset.module!=='guides'){e.preventDefault();e.stopImmediatePropagation();policy();return;}
    const act=e.target.closest('[data-action]');
    if(act&&['settings','profile','add-member','edit-member','toggle-member','save-member','reset-member-code','transfer-r5','confirm-transfer','revoke-others'].includes(act.dataset.action)){
      e.preventDefault();e.stopImmediatePropagation();policy();
    }
  },true);
  document.getElementById('languageStrip')?.addEventListener('click',()=>setTimeout(policy,0));
  window.addEventListener('pageshow',policy);
  new MutationObserver(()=>{if(isGuest())policy()}).observe(document.documentElement,{subtree:true,childList:true});
  if(isGuest()){setTimeout(policy,0);setTimeout(policy,80);setTimeout(policy,350);}
})();
