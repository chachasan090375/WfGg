(()=>{
'use strict';
/* WfGg V40.3.1 — exact stable-ID intent wins over the client preview filter.
   The V39 server already returns the exact catalogue row even when ordinary SQL filters are active.
   This patch makes the V35 client-side preview filter obey the same rule without changing asset metadata. */
const EXACT=/^LWGA-[A-Z0-9]+$/i;
let autoSid='';
function sid(){return String(document.querySelector('#q')?.value||'').trim().toUpperCase()}
function apply(){
  const s=sid();
  if(!EXACT.test(s)){autoSid='';return false}
  const p=document.querySelector('#preview_status');
  if(p&&p.value!=='all')p.value='all';
  return true;
}
function autoRun(){
  const s=sid();
  if(!EXACT.test(s)||s===autoSid)return;
  if(!apply())return;
  autoSid=s;
  const b=document.querySelector('#search');
  if(b)setTimeout(()=>b.click(),0);
}
// Capture phase: change preview mode before the existing search handler reads it.
document.addEventListener('click',e=>{if(e.target?.closest?.('#search'))apply()},true);
document.addEventListener('keydown',e=>{if(e.target?.id==='q'&&e.key==='Enter')apply()},true);
document.querySelector('#q')?.addEventListener('input',()=>{const s=sid();if(!EXACT.test(s))autoSid='';});
// Handles restored/query-filled pages where an exact ID is already present before this patch loads.
setTimeout(autoRun,120);
setTimeout(autoRun,700);
window.WFGGExactIdBypassV4031={version:'40.3.1',apply,autoRun};
console.info('V40_3_1_EXACT_ID client-preview-bypass=ON exact-intent-wins=ON');
})();
