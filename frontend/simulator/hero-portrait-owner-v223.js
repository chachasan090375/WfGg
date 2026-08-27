(()=>{
  'use strict';
  const MANIFEST='data/hero-portrait-owner-v223.json';
  const STILL=id=>`assets/heroes/cutout-v21/${id}.webp`;
  const FB1=id=>`assets/heroes/master-v20/${id}.webp`;
  const FB2=id=>`assets/heroes/${id}.webp`;
  const REST_MS=1300,START_MS=900;
  const SYNTH=['wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live','wfgg-v15-live','wfgg-native-gif-active-v17b','wfgg-native-gif-active-v17c','wfgg-v22-native-active'];
  let data={animated:{}},timer=0,running=false,generation=0,active=[],queued=false;
  const step=()=>document.getElementById('step-heroes');
  const grid=()=>document.getElementById('gameHeroGrid');
  const visible=()=>{const s=step();return !!s&&!s.classList.contains('hidden')&&document.visibilityState==='visible'};
  const cards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const viewport=()=>cards().filter(c=>{if(c.offsetParent===null)return false;const r=c.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth});
  const baseFor=c=>c.querySelector('.wfgg-v15-motion-layer>img:not(.wfgg-v223-anim)')||c.querySelector('.hero-card-portrait img:not(.wfgg-v223-anim)');
  const shuffle=a=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};

  function neutral(c){
    SYNTH.forEach(x=>c.classList.remove(x));
    c.style.setProperty('--wfgg-v15-x','0%');
    c.style.setProperty('--wfgg-v15-y','0%');
    c.style.setProperty('--wfgg-v15-zoom','1');
    c.dataset.wfggPortraitOwner='v223';
  }

  function bindBase(c){
    const id=c?.dataset?.heroId, img=baseFor(c);
    if(!id||!img)return;
    neutral(c);
    img.classList.add('wfgg-v223-base');
    img.removeAttribute('srcset');
    const desired=STILL(id);
    if(!img.dataset.wfggBaseBound){
      img.dataset.wfggBaseBound='1';
      img.addEventListener('error',()=>{
        const src=img.getAttribute('src')||'';
        if(src.includes('/cutout-v21/'))img.src=FB1(id);
        else if(src.includes('/master-v20/'))img.src=FB2(id);
      });
    }
    const src=img.getAttribute('src')||'';
    if(!src.includes('/cutout-v21/')&&!src.includes('/master-v20/')&&!src.includes('/assets/heroes/'))img.src=desired;
    else if(!src)img.src=desired;
  }

  function clearAnim(c){
    if(!c)return;
    c.classList.remove('wfgg-v223-native-active');
    c.querySelectorAll('.wfgg-v223-anim').forEach(n=>n.remove());
  }

  function stop(restore=true){
    generation++; running=false; clearTimeout(timer); timer=0;
    if(restore)active.forEach(clearAnim);
    active=[];
    document.documentElement.dataset.wfggV223Phase='idle';
    document.documentElement.dataset.wfggV223Active='0';
  }

  function preload(url,token){
    return new Promise(res=>{
      if(!url||token!==generation){res(false);return}
      const i=new Image(); let done=false;
      const fin=v=>{if(done)return;done=true;res(v)};
      i.onload=()=>fin(true); i.onerror=()=>fin(false); i.src=url;
      if(i.complete)fin(true); setTimeout(()=>fin(false),3500);
    });
  }

  async function activate(c,a,token){
    if(token!==generation||!c.isConnected||c.offsetParent===null)return false;
    bindBase(c); clearAnim(c);
    const host=c.querySelector('.wfgg-v15-motion-layer')||c.querySelector('.hero-card-portrait');
    if(!host)return false;
    const anim=new Image();
    anim.className='wfgg-v223-anim';
    anim.alt=''; anim.setAttribute('aria-hidden','true');
    anim.src=a.src;
    host.appendChild(anim);
    await new Promise(resolve=>{
      if(anim.complete){resolve();return}
      anim.addEventListener('load',resolve,{once:true});
      anim.addEventListener('error',resolve,{once:true});
      setTimeout(resolve,1200);
    });
    if(token!==generation||!anim.isConnected||!anim.naturalWidth){anim.remove();return false}
    c.classList.add('wfgg-v223-native-active');
    return true;
  }

  async function next(token){
    if(token!==generation||!running||!visible())return;
    const candidates=shuffle(viewport().filter(c=>data.animated?.[c.dataset.heroId]));
    if(!candidates.length){timer=setTimeout(()=>next(token),1000);return}
    const group=candidates.slice(0,Math.min(innerWidth<=600?3:4,candidates.length));
    const ready=[];
    document.documentElement.dataset.wfggV223Phase='preload';
    for(const c of group){
      const a=data.animated[c.dataset.heroId];
      if(await preload(a?.src,token))ready.push(c);
      if(token!==generation||!running||!visible())return;
    }
    active=[];
    for(const c of ready){
      const a=data.animated[c.dataset.heroId];
      if(await activate(c,a,token))active.push(c);
    }
    if(token!==generation||!running)return;
    document.documentElement.dataset.wfggV223Phase='active';
    document.documentElement.dataset.wfggV223Active=String(active.length);
    document.documentElement.dataset.wfggV223Batch=active.map(c=>c.dataset.heroId).join(',');
    const activeMs=Math.max(3000,...active.map(c=>Number(data.animated[c.dataset.heroId]?.durationMs)||4000));
    timer=setTimeout(()=>{
      if(token!==generation||!running)return;
      active.forEach(clearAnim); active=[];
      document.documentElement.dataset.wfggV223Phase='rest';
      document.documentElement.dataset.wfggV223Active='0';
      timer=setTimeout(()=>next(token),REST_MS);
    },activeMs);
  }

  function start(){
    if(running||!visible())return;
    running=true; const token=++generation;
    cards().forEach(bindBase);
    timer=setTimeout(()=>next(token),START_MS);
  }

  function enforce(){
    if(!visible())return;
    cards().forEach(bindBase);
    if(!running)start();
  }
  function schedule(){
    if(queued)return; queued=true;
    requestAnimationFrame(()=>{queued=false;enforce()});
  }
  function sync(){if(visible())schedule();else stop(true)}

  async function init(){
    try{const r=await fetch(MANIFEST,{cache:'no-cache'});if(r.ok)data=await r.json()}catch(_){data={animated:{}}}
    window.WfGgHeroMotionOwner='portrait-owner-v223';
    window.WfGgHeroPortraitOwnerV223={version:'22.3.0',manifest:data};
    window.WfGgHeroPortraitV18={version:'223-compat',profileFor:()=>({x:'0%',y:'0%',zoom:1}),apply:schedule};
    document.documentElement.dataset.wfggPortraitOwner='v223-single';
    const s=step(); if(s)new MutationObserver(sync).observe(s,{attributes:true,attributeFilter:['class']});
    const g=grid(); if(g)new MutationObserver(schedule).observe(g,{childList:true,subtree:true});
    document.addEventListener('visibilitychange',sync,{passive:true});
    window.addEventListener('pagehide',()=>stop(false),{once:true});
    sync();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
