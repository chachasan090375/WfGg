(()=>{
'use strict';
const MAX_TRIANGLES=60000;

function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

function parseOBJ(text,label){
  const verts=[];const tris=[];let material='';
  const lines=text.split(/\r?\n/);
  for(const raw of lines){
    const line=raw.trim();if(!line||line[0]==='#')continue;
    if(line.startsWith('v ')){
      const p=line.slice(2).trim().split(/\s+/).map(Number);if(p.length>=3&&p.every(Number.isFinite))verts.push([p[0],p[1],p[2]]);
    }else if(line.startsWith('usemtl ')){material=line.slice(7).trim();
    }else if(line.startsWith('f ')){
      const ids=line.slice(2).trim().split(/\s+/).map(tok=>{let n=parseInt(tok.split('/')[0],10);if(!Number.isFinite(n))return null;if(n<0)n=verts.length+n+1;return n-1;}).filter(n=>n!==null&&n>=0&&n<verts.length);
      for(let i=1;i+1<ids.length;i++)tris.push({a:ids[0],b:ids[i],c:ids[i+1],material,label});
    }
  }
  return {verts,tris,label};
}

function rot(v,yaw,pitch){
  const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
  const x1=v[0]*cy+v[2]*sy,z1=-v[0]*sy+v[2]*cy;
  return [x1,v[1]*cp-z1*sp,v[1]*sp+z1*cp];
}

function normal(a,b,c){
  const ux=b[0]-a[0],uy=b[1]-a[1],uz=b[2]-a[2],vx=c[0]-a[0],vy=c[1]-a[1],vz=c[2]-a[2];
  const nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx,l=Math.hypot(nx,ny,nz)||1;return [nx/l,ny/l,nz/l];
}

function hashHue(s){let h=0;for(const c of String(s||''))h=(h*33+c.charCodeAt(0))>>>0;return h%360;}

async function mount(host,manifest){
  host.innerHTML='<div class="v33modelwrap"><canvas class="v33modelcanvas"></canvas><div class="v33modelhud">Chargement de la géométrie 3D réelle…</div></div>';
  const wrap=host.querySelector('.v33modelwrap'),canvas=host.querySelector('canvas'),hud=host.querySelector('.v33modelhud');
  const ctx=canvas.getContext('2d',{alpha:false});
  const models=[];const failures=[];
  for(const obj of (manifest.objects||[])){
    try{const r=await fetch(obj.url);if(!r.ok)throw new Error('HTTP '+r.status);models.push(parseOBJ(await r.text(),obj.path));}
    catch(e){failures.push(obj.path+': '+e.message);}
  }
  if(!models.length){hud.textContent='Aucune géométrie OBJ lisible.';throw new Error('Aucune géométrie OBJ lisible');}

  let all=[];let min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity],totalRaw=0;
  for(const m of models){
    const base=all.length;for(const v of m.verts){all.push(v);for(let k=0;k<3;k++){if(v[k]<min[k])min[k]=v[k];if(v[k]>max[k])max[k]=v[k];}}
    m.base=base;totalRaw+=m.tris.length;
  }
  const center=min.map((v,i)=>(v+max[i])/2),span=Math.max(...max.map((v,i)=>v-min[i]))||1;
  all=all.map(v=>[(v[0]-center[0])/span*2,(v[1]-center[1])/span*2,(v[2]-center[2])/span*2]);

  let tris=[];
  for(const m of models)for(const t of m.tris)tris.push({a:t.a+m.base,b:t.b+m.base,c:t.c+m.base,material:t.material,label:t.label});
  let sampled=false;
  if(tris.length>MAX_TRIANGLES){
    sampled=true;const step=tris.length/MAX_TRIANGLES;const keep=[];for(let i=0;i<MAX_TRIANGLES;i++)keep.push(tris[Math.floor(i*step)]);tris=keep;
  }

  let yaw=.72,pitch=-.34,zoom=1,drag=false,lastX=0,lastY=0,raf=0;
  function resize(){const dpr=Math.min(devicePixelRatio||1,2),r=wrap.getBoundingClientRect(),w=Math.max(320,r.width),h=Math.max(320,r.height);canvas.width=Math.floor(w*dpr);canvas.height=Math.floor(h*dpr);canvas.style.width=w+'px';canvas.style.height=h+'px';ctx.setTransform(dpr,0,0,dpr,0,0);draw();}
  function schedule(){if(!raf)raf=requestAnimationFrame(()=>{raf=0;draw();});}
  function draw(){
    const w=canvas.clientWidth,h=canvas.clientHeight;ctx.fillStyle='#050608';ctx.fillRect(0,0,w,h);
    const rv=all.map(v=>rot(v,yaw,pitch));const f=Math.min(w,h)*.56*zoom,cam=4.2;
    const proj=rv.map(v=>{const d=Math.max(.35,cam-v[2]);return [w/2+v[0]*f/d,h/2-v[1]*f/d,v[2]];});
    const list=[];
    for(const t of tris){const a=rv[t.a],b=rv[t.b],c=rv[t.c],pa=proj[t.a],pb=proj[t.b],pc=proj[t.c];if(!a||!b||!c)continue;const n=normal(a,b,c);if(n[2]<-0.15)continue;list.push({z:(a[2]+b[2]+c[2])/3,pa,pb,pc,n,material:t.material,label:t.label});}
    list.sort((x,y)=>x.z-y.z);
    for(const t of list){const light=Math.max(.12,Math.min(1,.28+.72*Math.abs(t.n[2]*.85+t.n[1]*.15))),hue=hashHue(t.material||t.label);ctx.beginPath();ctx.moveTo(t.pa[0],t.pa[1]);ctx.lineTo(t.pb[0],t.pb[1]);ctx.lineTo(t.pc[0],t.pc[1]);ctx.closePath();ctx.fillStyle=`hsl(${hue} 18% ${Math.round(20+light*48)}%)`;ctx.fill();}
    ctx.fillStyle='#d7deec';ctx.font='12px system-ui';ctx.fillText(`${models.length} objet(s) OBJ · ${totalRaw.toLocaleString('fr-FR')} triangles${sampled?' · aperçu mobile décimé':''}`,12,h-14);
  }
  canvas.addEventListener('pointerdown',e=>{drag=true;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture?.(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(!drag)return;yaw+=(e.clientX-lastX)*.012;pitch=Math.max(-1.45,Math.min(1.45,pitch+(e.clientY-lastY)*.012));lastX=e.clientX;lastY=e.clientY;schedule();});
  canvas.addEventListener('pointerup',()=>drag=false);canvas.addEventListener('pointercancel',()=>drag=false);
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.35,Math.min(3.5,zoom*Math.exp(-e.deltaY*.001)));schedule();},{passive:false});
  let pinch=null;
  canvas.addEventListener('touchstart',e=>{if(e.touches.length===2)pinch=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);},{passive:true});
  canvas.addEventListener('touchmove',e=>{if(e.touches.length===2&&pinch){const d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);zoom=Math.max(.35,Math.min(3.5,zoom*d/pinch));pinch=d;schedule();}},{passive:true});

  hud.innerHTML=`<b>MODÈLE 3D RÉEL</b> · glisser pour tourner · molette/pincement pour zoomer<br><span>${manifest.assemblyAssetCount||0} assets du sous-dossier · ${(manifest.bundleIds||[]).length} bundle(s) assemblé(s) · ${(manifest.files||[]).filter(x=>x.kind==='png').length} texture(s) extraite(s)</span>`;
  const tex=(manifest.files||[]).filter(x=>['png','jpg','jpeg','webp'].includes(x.kind)).slice(0,24);
  if(tex.length){const tray=document.createElement('div');tray.className='v33texturetray';tray.innerHTML='<span class="v33texturetitle">Textures / composants disponibles dans l’assemblage</span>'+tex.map(x=>`<img loading="lazy" src="${esc(x.url)}" title="${esc(x.path)}">`).join('');host.appendChild(tray);}
  const ro=new ResizeObserver(resize);ro.observe(wrap);resize();
  return {canvas,manifest,destroy(){ro.disconnect();},failures};
}

window.WFGGModelViewer={mount};
})();

/* Mobile result-strip synchronisation: keep the selected bundle/asset centered
   whenever select(), Previous or Next rebuilds the result cards. */
(()=>{
'use strict';
function syncActiveCard(behavior='smooth'){
  const strip=document.getElementById('results');
  if(!strip)return;
  const desktop=window.matchMedia('(min-width:980px)').matches;
  if(desktop){
    strip.style.paddingLeft='7px';strip.style.paddingRight='7px';
    const active=strip.querySelector('.card.active');
    active?.scrollIntoView?.({block:'nearest',inline:'nearest',behavior:behavior==='smooth'?'smooth':'auto'});
    return;
  }
  const cards=[...strip.querySelectorAll('.card')];
  cards.forEach(card=>{card.style.scrollSnapAlign='center';card.style.scrollSnapStop='always';});
  const active=strip.querySelector('.card.active');
  if(!active)return;
  active.style.borderWidth='2px';
  active.style.boxShadow='0 0 0 1px #a78bfa inset,0 0 18px #a78bfa33';
  const side=Math.max(7,Math.round((strip.clientWidth-active.getBoundingClientRect().width)/2));
  strip.style.paddingLeft=side+'px';strip.style.paddingRight=side+'px';
  strip.style.scrollSnapType='x mandatory';
  requestAnimationFrame(()=>{
    const target=active.offsetLeft-(strip.clientWidth-active.offsetWidth)/2;
    strip.scrollTo({left:Math.max(0,target),behavior});
  });
}
function installStripSync(){
  const strip=document.getElementById('results');if(!strip)return;
  let queued=false;
  const schedule=(behavior='smooth')=>{
    if(queued)return;queued=true;
    requestAnimationFrame(()=>{queued=false;syncActiveCard(behavior);});
  };
  const observer=new MutationObserver(()=>schedule('smooth'));
  observer.observe(strip,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
  strip.addEventListener('click',e=>{if(e.target.closest('.card'))setTimeout(()=>syncActiveCard('smooth'),0)});
  window.addEventListener('resize',()=>syncActiveCard('auto'),{passive:true});
  schedule('auto');
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',installStripSync,{once:true});
else installStripSync();
})();
