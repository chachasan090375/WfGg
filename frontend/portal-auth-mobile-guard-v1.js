(() => {
'use strict';
/* WFGG_PORTAL_AUTH_MOBILE_GUARD_V1
   Android/Chrome login resilience: avoid keeping a programmatic startup focus on
   coarse-pointer devices, then honor the user's real touch as the focus gesture.
*/
/* WFGG_PORTAL_MODULE_LINK_BRIDGE_V1
   Synchronise une session serveur HttpOnly avant d'ouvrir Guides/Train. Le
   contrôle final reste dans le Worker : sans session Portail valide, le module
   est refusé même si son URL exacte est connue. */
const PORTAL_TOKEN_KEY='wfgg_portal_session';
let moduleSessionReady=false;
let moduleSessionPromise=null;
async function syncPortalModuleSession(){
  const portalToken=localStorage.getItem(PORTAL_TOKEN_KEY);
  if(!portalToken){moduleSessionReady=false;return false;}
  if(moduleSessionPromise)return moduleSessionPromise;
  moduleSessionPromise=fetch('/api/module-session',{
    method:'POST',
    headers:{'Authorization':'Bearer '+portalToken},
    credentials:'same-origin',
    cache:'no-store'
  }).then(r=>{moduleSessionReady=r.ok;return r.ok;}).catch(()=>{moduleSessionReady=false;return false;}).finally(()=>{moduleSessionPromise=null;});
  return moduleSessionPromise;
}
if(localStorage.getItem(PORTAL_TOKEN_KEY))syncPortalModuleSession();
window.addEventListener('pageshow',()=>{if(localStorage.getItem(PORTAL_TOKEN_KEY))syncPortalModuleSession();});
document.addEventListener('click',event=>{
  const link=event.target.closest?.('a[data-module][href]');
  if(!link)return;
  if(moduleSessionReady)return;
  event.preventDefault();
  const target=link.href;
  syncPortalModuleSession().then(ok=>{
    if(ok){location.href=target;return;}
    const u=new URL('/',location.origin);
    try{const t=new URL(target,location.href);u.searchParams.set('returnTo',t.pathname+t.search);}catch{}
    location.href=u.toString();
  });
},true);

const input=document.getElementById('authCode');
if(!input)return;
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
})();
