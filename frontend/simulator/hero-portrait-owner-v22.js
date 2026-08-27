(()=>{
  'use strict';
  const MANIFEST='data/hero-portrait-owner-v22.json';
  const STILL=id=>`assets/heroes/cutout-v21/${id}.webp`;
  const FB1=id=>`assets/heroes/master-v20/${id}.webp`;
  const FB2=id=>`assets/heroes/${id}.webp`;
  const ACTIVE_MS=3500,REST_MS=1400,START_MS=1000;
  const SYNTH=['wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live','wfgg-v15-live','wfgg-native-gif-active-v17b','wfgg-native-gif-active-v17c'];
  let data={animated:{}},timer=0,running=false,generation=0,active=[],queued=false;
  const step=()=>document.getElementById('step-heroes');
  const grid=()=>document.getElementById('gameHeroGrid');
  const visible=()=>{const s=step();return !!s&&!s.classList.contains('hidden')&&document.visibilityState==='visible'};
  const cards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const viewport=()=>cards().filter(c=>{if(c.offsetParent===null)return false;const r=c.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth});
  const imgFor=c=>c.querySelector('.wfgg-v15-motion-layer>img')||c.querySelector('.hero-card-portrait img');
  const shuffle=a=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
  function neutral(c){SYNTH.forEach(x=>c.classList.remove(x));c.style.setProperty('--wfgg-v15-x','0%');c.style.setProperty('--wfgg-v15-y','0%');c.style.setProperty('--wfgg-v15-zoom','1');c.dataset.wfggPortraitOwner='v22'}
  function setSource(c,url,kind){const img=imgFor(c);if(!img)return;neutral(c);if(img.getAttribute('src')!==url)img.src=url;c.dataset.wfggPortraitKind=kind;c.classList.toggle('wfgg-v22-native-active',kind==='animated')}
  function still(c){if(c?.dataset?.heroId)setSource(c,STILL(c.dataset.heroId),'still')}
  function stop(restore=true){generation++;running=false;clearTimeout(timer);timer=0;if(restore)active.forEach(still);active=[];document.documentElement.dataset.wfggV22Phase='idle';document.documentElement.dataset.wfggV22Active='0'}
  function preload(url,token){return new Promise(res=>{if(!url||token!==generation){res(false);return}const i=new Image();let done=false;const fin=v=>{if(done)return;done=true;res(v)};i.onload=()=>fin(true);i.onerror=()=>fin(false);i.src=url;if(i.complete)fin(true);setTimeout(()=>fin(false),2500)})}
  async function next(token){
    if(token!==generation||!running||!visible())return;
    const candidates=shuffle(viewport().filter(c=>data.animated?.[c.dataset.heroId]));
    if(!candidates.length){timer=setTimeout(()=>next(token),1000);return}
    const group=candidates.slice(0,Math.min(innerWidth<=600?3:4,candidates.length));
    const ready=[];document.documentElement.dataset.wfggV22Phase='preload';
    for(const c of group){const a=data.animated[c.dataset.heroId];if(await preload(a?.src,token))ready.push(c);if(token!==generation||!running||!visible())return}
    active=ready.filter(c=>c.isConnected&&c.offsetParent!==null);
    active.forEach(c=>setSource(c,data.animated[c.dataset.heroId].src,'animated'));
    document.documentElement.dataset.wfggV22Phase='active';document.documentElement.dataset.wfggV22Active=String(active.length);document.documentElement.dataset.wfggV22Batch=active.map(c=>c.dataset.heroId).join(',');
    timer=setTimeout(()=>{if(token!==generation||!running)return;active.forEach(still);active=[];document.documentElement.dataset.wfggV22Phase='rest';document.documentElement.dataset.wfggV22Active='0';timer=setTimeout(()=>next(token),REST_MS)},ACTIVE_MS)
  }
  function start(){if(running||!visible())return;running=true;const token=++generation;cards().forEach(still);timer=setTimeout(()=>next(token),START_MS)}
  function enforce(){if(!visible())return;for(const c of cards()){if(!c.classList.contains('wfgg-v22-native-active'))still(c)}if(!running)start()}
  function schedule(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;enforce()})}
  function sync(){if(visible())schedule();else stop(true)}
  function onError(e){const img=e.target;if(!(img instanceof HTMLImageElement))return;const c=img.closest('.game-hero-card[data-hero-id]');if(!c)return;const id=c.dataset.heroId;if(c.classList.contains('wfgg-v22-native-active')){still(c);return}const s=img.getAttribute('src')||'';if(s.includes('/cutout-v21/'))img.src=FB1(id);else if(s.includes('/master-v20/'))img.src=FB2(id)}
  async function init(){
    try{const r=await fetch(MANIFEST,{cache:'no-cache'});if(r.ok)data=await r.json()}catch(_){data={animated:{}}}
    window.WfGgHeroMotionOwner='portrait-owner-v22';window.WfGgHeroPortraitOwnerV22={version:'22.2.0',manifest:data};window.WfGgHeroPortraitV18={version:'22-compat',profileFor:()=>({x:'0%',y:'0%',zoom:1}),apply:schedule};
    document.documentElement.dataset.wfggPortraitOwner='v22-single';
    const s=step();if(s)new MutationObserver(sync).observe(s,{attributes:true,attributeFilter:['class']});
    const g=grid();if(g){g.addEventListener('error',onError,true);new MutationObserver(schedule).observe(g,{childList:true,subtree:true,attributes:true,attributeFilter:['src']})}
    document.addEventListener('visibilitychange',sync,{passive:true});window.addEventListener('pagehide',()=>stop(false),{once:true});sync();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
