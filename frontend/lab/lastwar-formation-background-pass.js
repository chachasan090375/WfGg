(()=>{'use strict';
const params=new URLSearchParams(location.search);
const layer=params.get('layer');
if(layer==='background')document.documentElement.classList.add('lw-background-only');
if(layer==='world')document.documentElement.classList.add('lw-world-only');

const ground=document.querySelector('.formation-ground');
const switcher=document.getElementById('teamSwitcher');

/* Layer0 is now a single fixed baked world image and never changes per team.
   Only Layer1 (biandui_cheku_N) switches with the active formation. */
function applyPlatform(team){
  const n=Math.min(4,Math.max(1,Number(team)||1));
  if(ground)ground.src=`master-assets-v1/ui/formation-${n}.png`;
  document.documentElement.dataset.formationScene=String(n);
}

applyPlatform(1);
switcher?.addEventListener('click',e=>{
  const b=e.target.closest('[data-team]');
  if(b)applyPlatform(b.dataset.team);
});
})();
