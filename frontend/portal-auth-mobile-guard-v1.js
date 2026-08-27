(() => {
'use strict';
/* WFGG_PORTAL_AUTH_MOBILE_GUARD_V1
   Android/Chrome login resilience: avoid keeping a programmatic startup focus on
   coarse-pointer devices, then honor the user's real touch as the focus gesture.
*/
const input=document.getElementById('authCode');
if(input){
  input.dataset.mobileAuthGuard='v1';
  input.style.position='relative';
  input.style.zIndex='3';
  input.style.pointerEvents='auto';
  input.style.touchAction='manipulation';
  input.style.webkitUserSelect='text';
  input.style.userSelect='text';
  input.setAttribute('enterkeyhint','go');
  let userTouched=false;
  const focusFromGesture=()=>{
    userTouched=true;
    if(input.disabled||input.readOnly)return;
    try{input.focus({preventScroll:true})}catch{input.focus()}
  };
  input.addEventListener('pointerdown',()=>{userTouched=true},{passive:true});
  input.addEventListener('pointerup',focusFromGesture,{passive:true});
  input.addEventListener('touchend',focusFromGesture,{passive:true});
  input.addEventListener('click',focusFromGesture,{passive:true});
  const coarse=()=>window.matchMedia?.('(hover: none), (pointer: coarse)')?.matches;
  setTimeout(()=>{
    if(coarse()&&!userTouched&&document.activeElement===input)input.blur();
  },120);
  window.WFGG_AUTH_MOBILE_GUARD_TEST={version:'v1',coarse};
}

/* WFGG_AUTH_LAB_PREVIEW_V1
   Visible only because this file exists on the experimental preview branch.
   The card points to an isolated module that reuses the portal session.
*/
function injectAuthLabCard(){
  const grid=document.querySelector('.module-grid');
  if(!grid||document.getElementById('authLabModuleLink'))return;
  const link=document.createElement('a');
  link.id='authLabModuleLink';
  link.className='module-card glass-card';
  link.href='/lab/';
  link.setAttribute('aria-label','Ouvrir le module laboratoire d’authentification');
  link.innerHTML='<span class="module-icon">🧪</span><span class="module-arrow">↗</span><span class="module-copy"><strong>Lab Auth</strong><small>Test du contexte partagé</small></span>';
  const settings=grid.querySelector('.settings-card');
  if(settings)grid.insertBefore(link,settings);else grid.appendChild(link);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',injectAuthLabCard,{once:true});
else injectAuthLabCard();
})();
