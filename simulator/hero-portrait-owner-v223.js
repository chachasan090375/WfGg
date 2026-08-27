(()=>{
  'use strict';

  const MANIFEST='data/hero-portrait-owner-v223.json';
  const FALLBACK=id=>`assets/heroes/cutout-v21/${id}.webp`;
  const REST_MS=1300, START_MS=900, END_CAPTURE_LEAD_MS=24;
  const SYNTH=[
    'wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live','wfgg-v15-live',
    'wfgg-native-gif-active-v17b','wfgg-native-gif-active-v17c','wfgg-v22-native-active'
  ];

  let data={animated:{}}, timer=0, running=false, generation=0, active=[], queued=false;
  const assetCache=new Map();
  const stageState=new WeakMap();
  const step=()=>document.getElementById('step-heroes');
  const grid=()=>document.getElementById('gameHeroGrid');
  const visible=()=>{const s=step();return !!s&&!s.classList.contains('hidden')&&document.visibilityState==='visible'};
  const cards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')];
  const viewport=()=>cards().filter(c=>{if(c.offsetParent===null)return false;const r=c.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth});
  const shuffle=a=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
  const wait=ms=>new Promise(res=>setTimeout(res,ms));

  function neutral(c){
    SYNTH.forEach(x=>c.classList.remove(x));
    c.style.setProperty('--wfgg-v15-x','0%');
    c.style.setProperty('--wfgg-v15-y','0%');
    c.style.setProperty('--wfgg-v15-zoom','1');
    c.dataset.wfggPortraitOwner='v223';
    c.classList.add('wfgg-v223-owned');
  }

  function sourceSize(source){
    return [Number(source?.naturalWidth||source?.width||0),Number(source?.naturalHeight||source?.height||0)];
  }

  function paintContained(canvas,source){
    if(!canvas||!source)return false;
    const stage=canvas.parentElement;
    if(!stage)return false;
    const rect=stage.getBoundingClientRect();
    const cssW=Math.max(1,rect.width||stage.clientWidth||1);
    const cssH=Math.max(1,rect.height||stage.clientHeight||1);
    const dpr=Math.min(3,Math.max(1,window.devicePixelRatio||1));
    const w=Math.max(1,Math.round(cssW*dpr));
    const h=Math.max(1,Math.round(cssH*dpr));
    if(canvas.width!==w)canvas.width=w;
    if(canvas.height!==h)canvas.height=h;
    const [sw,sh]=sourceSize(source);
    if(!sw||!sh)return false;
    const scale=Math.min(w/sw,h/sh);
    const dw=sw*scale, dh=sh*scale;
    const dx=(w-dw)/2, dy=0;
    const ctx=canvas.getContext('2d',{alpha:true,desynchronized:false});
    if(!ctx)return false;
    ctx.clearRect(0,0,w,h);
    ctx.imageSmoothingEnabled=true;
    ctx.imageSmoothingQuality='high';
    ctx.drawImage(source,dx,dy,dw,dh);
    return true;
  }

  function clearRestPixels(stage){
    if(!stage)return;
    const canvas=stage.querySelector('.wfgg-v223-rest');
    if(!canvas)return;
    const ctx=canvas.getContext('2d',{alpha:true,desynchronized:false});
    if(ctx)ctx.clearRect(0,0,canvas.width,canvas.height);
  }

  function makeStage(c){
    if(!c)return null;
    neutral(c);
    const host=c.querySelector('.hero-card-portrait');
    if(!host)return null;
    let stage=host.querySelector(':scope > .wfgg-v223-stage');
    if(!stage){
      stage=document.createElement('span');
      stage.className='wfgg-v223-stage';
      stage.setAttribute('aria-hidden','true');
      const canvas=document.createElement('canvas');
      canvas.className='wfgg-v223-rest';
      stage.appendChild(canvas);
      const fallback=document.createElement('img');
      fallback.className='wfgg-v223-rest-fallback';
      fallback.alt='';
      fallback.setAttribute('aria-hidden','true');
      stage.appendChild(fallback);
      host.appendChild(stage);
      const redraw=()=>{
        const s=stageState.get(stage);
        if(s?.bitmap&&!stage.classList.contains('wfgg-v223-frame2'))paintContained(canvas,s.bitmap);
      };
      if('ResizeObserver' in window){
        const ro=new ResizeObserver(redraw); ro.observe(stage); stageState.set(stage,{ro,bitmap:null});
      }else{
        stageState.set(stage,{ro:null,bitmap:null});
      }
    }
    return stage;
  }

  async function loadAsset(id,a,token){
    if(!a?.src)return null;
    if(assetCache.has(id))return assetCache.get(id);
    const promise=(async()=>{
      try{
        const r=await fetch(a.src,{cache:'force-cache'});
        if(!r.ok)throw new Error(a.src);
        const blob=await r.blob();
        if(token!==generation)return null;
        const url=URL.createObjectURL(blob);
        let bitmap=null;
        if('createImageBitmap' in window){
          try{bitmap=await createImageBitmap(blob)}catch(_){bitmap=null}
        }
        return {blob,url,bitmap};
      }catch(_){
        return {blob:null,url:a.src,bitmap:null};
      }
    })();
    assetCache.set(id,promise);
    return promise;
  }

  async function ensureRest(c,a,token){
    if(token!==generation||!c?.isConnected)return null;
    const id=c.dataset.heroId;
    const stage=makeStage(c);
    if(!stage)return null;
    stage.classList.remove('wfgg-v223-frame2');
    const canvas=stage.querySelector('.wfgg-v223-rest');
    const fallback=stage.querySelector('.wfgg-v223-rest-fallback');
    const asset=await loadAsset(id,a,token);
    if(token!==generation||!asset||!stage.isConnected)return null;
    const s=stageState.get(stage)||{};
    s.bitmap=asset.bitmap||null;
    stageState.set(stage,s);
    if(asset.bitmap){
      fallback.removeAttribute('src');
      stage.classList.remove('wfgg-v223-rest-fallback-active');
      paintContained(canvas,asset.bitmap);
    }else{
      fallback.src=a.still||FALLBACK(id);
      stage.classList.add('wfgg-v223-rest-fallback-active');
    }
    return {stage,asset};
  }

  function clearAnim(c){
    if(!c)return;
    c.classList.remove('wfgg-v223-native-active');
    c.querySelectorAll('.wfgg-v223-stage').forEach(stage=>stage.classList.remove('wfgg-v223-frame2'));
    c.querySelectorAll('.wfgg-v223-stage .wfgg-v223-anim').forEach(n=>n.remove());
  }

  function stop(restore=true){
    generation++; running=false; clearTimeout(timer); timer=0;
    if(restore)active.forEach(clearAnim);
    active=[];
    document.documentElement.dataset.wfggV223Phase='idle';
    document.documentElement.dataset.wfggV223Active='0';
  }

  async function playCard(c,a,token){
    if(token!==generation||!c.isConnected||c.offsetParent===null)return false;
    clearAnim(c);
    const prepared=await ensureRest(c,a,token);
    if(token!==generation||!prepared||!c.isConnected)return false;
    const {stage,asset}=prepared;

    const anim=new Image();
    anim.className='wfgg-v223-anim';
    anim.alt='';
    anim.setAttribute('aria-hidden','true');
    anim.decoding='sync';
    stage.appendChild(anim);

    const loaded=new Promise(resolve=>{
      let done=false;
      const finish=ok=>{if(done)return;done=true;resolve(ok)};
      anim.addEventListener('load',()=>finish(true),{once:true});
      anim.addEventListener('error',()=>finish(false),{once:true});
      setTimeout(()=>finish(false),2500);
    });
    anim.src=asset.url||a.src;
    const ok=await loaded;
    if(token!==generation||!ok||!anim.naturalWidth||!anim.isConnected){anim.remove();return false}

    const duration=Math.max(600,Number(a.durationMs)||4000);
    const frames=Math.max(2,Number(a.frames)||48);
    const firstFrameMs=Math.max(40,Math.min(160,duration/frames));
    const startedAt=performance.now();

    stage.classList.remove('wfgg-v223-frame2');
    c.classList.add('wfgg-v223-native-active');
    active.push(c);

    /* Frame 1 is the rest image. From frame 2 onward the fixed surface is physically cleared. */
    await wait(firstFrameMs);
    if(token!==generation||!anim.isConnected){clearAnim(c);return false}
    stage.classList.add('wfgg-v223-frame2');
    clearRestPixels(stage);
    document.documentElement.dataset.wfggV223Handoff='frame2';

    const captureAt=Math.max(0,duration-END_CAPTURE_LEAD_MS);
    const elapsedToFrame2=performance.now()-startedAt;
    await wait(Math.max(0,captureAt-elapsedToFrame2));
    if(token!==generation||!anim.isConnected){clearAnim(c);return false}

    const canvas=stage.querySelector('.wfgg-v223-rest');
    stage.classList.remove('wfgg-v223-rest-fallback-active');
    paintContained(canvas,anim);

    const elapsedToCapture=performance.now()-startedAt;
    await wait(Math.max(0,duration-elapsedToCapture));
    if(token!==generation){clearAnim(c);return false}

    anim.remove();
    stage.classList.remove('wfgg-v223-frame2');
    c.classList.remove('wfgg-v223-native-active');
    active=active.filter(x=>x!==c);
    return true;
  }

  async function next(token){
    if(token!==generation||!running||!visible())return;
    const candidates=shuffle(viewport().filter(c=>data.animated?.[c.dataset.heroId]));
    if(!candidates.length){timer=setTimeout(()=>next(token),1000);return}
    const group=candidates.slice(0,Math.min(innerWidth<=600?3:4,candidates.length));

    document.documentElement.dataset.wfggV223Phase='prepare';
    document.documentElement.dataset.wfggV223Batch=group.map(c=>c.dataset.heroId).join(',');
    const jobs=group.map(c=>playCard(c,data.animated[c.dataset.heroId],token));
    document.documentElement.dataset.wfggV223Phase='active';
    document.documentElement.dataset.wfggV223Active=String(group.length);
    await Promise.all(jobs);

    if(token!==generation||!running||!visible())return;
    document.documentElement.dataset.wfggV223Phase='rest';
    document.documentElement.dataset.wfggV223Active='0';
    timer=setTimeout(()=>next(token),REST_MS);
  }

  async function prime(token){
    const list=viewport();
    await Promise.all(list.map(async c=>{
      const a=data.animated?.[c.dataset.heroId];
      if(a)await ensureRest(c,a,token);
      else neutral(c);
    }));
  }

  async function start(){
    if(running||!visible())return;
    running=true;
    const token=++generation;
    await prime(token);
    if(token!==generation||!running||!visible())return;
    timer=setTimeout(()=>next(token),START_MS);
  }

  function enforce(){
    if(!visible())return;
    cards().forEach(neutral);
    const token=generation;
    viewport().forEach(c=>{const a=data.animated?.[c.dataset.heroId];if(a)ensureRest(c,a,token)});
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
    window.WfGgHeroPortraitOwnerV223={version:'22.3.2-frame2-handoff',manifest:data};
    window.WfGgHeroPortraitV18={version:'223.2-compat',profileFor:()=>({x:'0%',y:'0%',zoom:1}),apply:schedule};
    document.documentElement.dataset.wfggPortraitOwner='v223-frame2-handoff';
    const s=step(); if(s)new MutationObserver(sync).observe(s,{attributes:true,attributeFilter:['class']});
    const g=grid(); if(g)new MutationObserver(schedule).observe(g,{childList:true,subtree:true});
    document.addEventListener('visibilitychange',sync,{passive:true});
    window.addEventListener('resize',schedule,{passive:true});
    window.addEventListener('pagehide',()=>{
      stop(false);
      for(const p of assetCache.values())Promise.resolve(p).then(a=>{if(a?.url?.startsWith('blob:'))URL.revokeObjectURL(a.url)});
    },{once:true});
    sync();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
