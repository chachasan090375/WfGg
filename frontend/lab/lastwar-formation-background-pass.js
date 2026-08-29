(()=>{'use strict';
const params=new URLSearchParams(location.search);
if(params.get('layer')==='background')document.documentElement.classList.add('lw-background-only');

const ground=document.querySelector('.formation-ground');
const blur=document.querySelector('.world-blur');
const switcher=document.getElementById('teamSwitcher');

function applyScene(team){
  const n=Math.min(4,Math.max(1,Number(team)||1));
  const src=`master-assets-v1/ui/formation-${n}.png`;
  if(ground) ground.src=src;
  if(blur) blur.style.setProperty('background-image',`url("${src}")`,'important');
  document.documentElement.dataset.formationScene=String(n);
}

applyScene(1);

switcher?.addEventListener('click',e=>{
  const b=e.target.closest('[data-team]');
  if(b) applyScene(b.dataset.team);
});
})();
