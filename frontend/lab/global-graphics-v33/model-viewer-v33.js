(()=>{
'use strict';

/* V35.2 UV/material-aware model viewer.
   - keeps the exact V34 OBJ/PPtr pipeline;
   - parses OBJ UV coordinates and material slots;
   - uses WebGL for fast mobile texture mapping when available;
   - automatically applies exact Material -> Texture2D bindings emitted by the V35 server wrapper;
   - discovers same-model-folder texture sheets as optional alternatives;
   - exposes compact texture thumbnails inside the 3D stage (AUTO / OFF / alternatives).
*/

const MOBILE=matchMedia('(max-width:979px)').matches;
const MAX_TRIANGLES=MOBILE?50000:90000;
const MAX_OBJECTS=MOBILE?16:32;
const FETCH_BATCH=MOBILE?10:8;
const OBJECT_CACHE=new Map();
const IMAGE_CACHE=new Map();
const OBJECT_CACHE_LIMIT=MOBILE?36:84;
const IMAGE_CACHE_LIMIT=MOBILE?30:72;
const MAX_TEXTURE_CHOICES=MOBILE?14:28;

function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function clamp(v,a,b){return Math.max(a,Math.min(b,v));}
function safeIndex(raw,len){
  let n=parseInt(raw,10);if(!Number.isFinite(n)||!n)return -1;
  if(n<0)n=len+n+1;return n-1;
}
function parseOBJ(text,label){
  const verts=[],uvs=[],tris=[];let material='';const materialSlots=new Map();
  const lines=text.split(/\r?\n/);
  for(const raw of lines){
    const line=raw.trim();if(!line||line[0]==='#')continue;
    if(line.startsWith('v ')){
      const p=line.slice(2).trim().split(/\s+/).map(Number);if(p.length>=3&&p.slice(0,3).every(Number.isFinite))verts.push([p[0],p[1],p[2]]);
    }else if(line.startsWith('vt ')){
      const p=line.slice(3).trim().split(/\s+/).map(Number);if(p.length>=2&&p.slice(0,2).every(Number.isFinite))uvs.push([p[0],p[1]]);
    }else if(line.startsWith('usemtl ')){
      material=line.slice(7).trim();if(!materialSlots.has(material))materialSlots.set(material,materialSlots.size);
    }else if(line.startsWith('f ')){
      const refs=line.slice(2).trim().split(/\s+/).map(tok=>{
        const p=tok.split('/');const vi=safeIndex(p[0],verts.length),ti=p.length>1&&p[1]!==''?safeIndex(p[1],uvs.length):-1;
        return {vi,ti};
      }).filter(x=>x.vi>=0&&x.vi<verts.length);
      const slot=materialSlots.has(material)?materialSlots.get(material):0;
      for(let i=1;i+1<refs.length;i++){
        const a=refs[0],b=refs[i],c=refs[i+1];
        tris.push({
          a:a.vi,b:b.vi,c:c.vi,
          ua:a.ti>=0&&a.ti<uvs.length?uvs[a.ti]:null,
          ub:b.ti>=0&&b.ti<uvs.length?uvs[b.ti]:null,
          uc:c.ti>=0&&c.ti<uvs.length?uvs[c.ti]:null,
          material,materialSlot:slot,label
        });
      }
    }
  }
  return {verts,uvs,tris,label,materialCount:Math.max(1,materialSlots.size)};
}

function touchCache(map,key,value,limit){
  if(map.has(key))map.delete(key);map.set(key,value);
  while(map.size>limit){const oldest=map.keys().next().value;map.delete(oldest);}
}
async function fetchModelObject(obj){
  const key=String(obj.url||obj.path||'');
  if(OBJECT_CACHE.has(key)){const cached=OBJECT_CACHE.get(key);touchCache(OBJECT_CACHE,key,cached,OBJECT_CACHE_LIMIT);return cached;}
  const promise=(async()=>{const r=await fetch(obj.url,{cache:'force-cache'});if(!r.ok)throw new Error('HTTP '+r.status);return parseOBJ(await r.text(),obj.path);})();
  touchCache(OBJECT_CACHE,key,promise,OBJECT_CACHE_LIMIT);
  try{const model=await promise;touchCache(OBJECT_CACHE,key,Promise.resolve(model),OBJECT_CACHE_LIMIT);return model;}
  catch(e){if(OBJECT_CACHE.get(key)===promise)OBJECT_CACHE.delete(key);throw e;}
}
async function prefetch(manifest){
  const all=(manifest?.objects||[]).slice(0,MAX_OBJECTS);if(!all.length)return {requested:0,ready:0,failed:0};
  const results=await Promise.allSettled(all.map(fetchModelObject));
  return {requested:all.length,ready:results.filter(x=>x.status==='fulfilled').length,failed:results.filter(x=>x.status==='rejected').length};
}

function normal(a,b,c){
  const ux=b[0]-a[0],uy=b[1]-a[1],uz=b[2]-a[2],vx=c[0]-a[0],vy=c[1]-a[1],vz=c[2]-a[2];
  const nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx,l=Math.hypot(nx,ny,nz)||1;return [nx/l,ny/l,nz/l];
}
function hashHue(s){let h=0;for(const c of String(s||''))h=(h*33+c.charCodeAt(0))>>>0;return h%360;}
function hslToRgb(h,s=.22,l=.56){
  h=((h%360)+360)%360/360;const hue2rgb=(p,q,t)=>{if(t<0)t+=1;if(t>1)t-=1;if(t<1/6)return p+(q-p)*6*t;if(t<1/2)return q;if(t<2/3)return p+(q-p)*(2/3-t)*6;return p;};
  if(!s)return [l,l,l];const q=l<.5?l*(1+s):l+s-l*s,p=2*l-q;return [hue2rgb(p,q,h+1/3),hue2rgb(p,q,h),hue2rgb(p,q,h-1/3)];
}
function normPath(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||a?.path||'').replace(/\\/g,'/').toLowerCase();}
function semanticFromName(a){
  const p=normPath(a),tail=p.split('/').pop()||'';
  if(/(?:^|[_-])(normal|nrm|n)(?:[_-]|\.)/.test(tail)||/normal|bump/.test(p))return 'normal';
  if(/emiss|glow/.test(p))return 'emission';
  if(/(?:^|[_-])(spec|specular|smooth|rough|metal|metallic|mask|ao|occlusion|s|m)(?:[_-]|\.)/.test(tail))return 'material';
  if(/(?:^|[_-])(albedo|basecolor|diffuse|color|base|d|c)(?:[_-]|\.)/.test(tail)||/albedo|diffuse|basecolor|maintex/.test(p))return 'color';
  return String(a?.semantic||'unknown');
}
function looksTextureAsset(a){
  const p=normPath(a),role=String(a?.model_role||'').toLowerCase(),tech=String(a?.tech_kind||'').toLowerCase(),dim=String(a?.dimension_class||'');
  return /\/(texture|textures|pbr|materials?)\//.test(p)&&(role==='texture'||/texture2d|texture|tga|dds|ktx|astc/.test(tech)||dim==='2D'||/\.(tga|dds|png|jpg|jpeg|webp|ktx|ktx2|astc)$/i.test(p));
}
function modelStem(manifest){
  const folder=String(manifest?.assetFolder||'').replace(/\\/g,'/').replace(/\/$/,'');return (folder.split('/').pop()||String(manifest?.rootGameObject||'')).toLowerCase();
}
function textureScore(a,manifest){
  const p=normPath(a),stem=modelStem(manifest),sem=semanticFromName(a);let score=0;
  if(/\/pbr\//.test(p))score+=5;if(/\/texture/.test(p))score+=4;if(stem&&p.includes(stem))score+=6;
  if(sem==='color')score+=8;else if(sem==='unknown')score+=3;else if(sem==='normal')score-=1;
  if(String(a?.render_availability||'').startsWith('local-'))score+=2;
  return score;
}
async function discoverTextureCandidates(manifest){
  const folder=String(manifest?.assetFolder||'').replace(/\\/g,'/').replace(/\/$/,'');if(!folder)return [];
  const out=[],seen=new Set();
  async function query(path){
    try{
      const p=new URLSearchParams({path_prefix:path,render_availability:'local-renderable',limit:'120',offset:'0'});
      const r=await fetch('/api/v33/search?'+p,{cache:'no-store'}),d=await r.json();if(!r.ok)return;
      for(const a of (d.items||[]))if(looksTextureAsset(a)&&!seen.has(a.stable_id)){seen.add(a.stable_id);out.push({...a,semantic:semanticFromName(a),candidate:true,url:'/api/v33/render?id='+encodeURIComponent(a.stable_id)});}
    }catch{}
  }
  await query(folder);
  if(out.length<4){const parent=folder.split('/').slice(0,-1).join('/');if(parent&&parent!==folder)await query(parent);}
  out.sort((a,b)=>textureScore(b,manifest)-textureScore(a,manifest));return out.slice(0,MAX_TEXTURE_CHOICES);
}
function normalizeExactBindings(manifest){
  const out=[];const map=manifest?.objectTextures||{};
  for(const [objectPath,bindings] of Object.entries(map))for(const b of (bindings||[])){
    if(!b?.url)continue;out.push({...b,objectPath,semantic:String(b.semantic||semanticFromName(b)),exact:true});
  }
  return out;
}
function candidateKey(x){return String(x.url||x.stable_id||x.path||x.texturePathId||Math.random());}
async function loadImage(url){
  const key=String(url||'');if(!key)throw new Error('texture-url-empty');
  if(IMAGE_CACHE.has(key)){const cached=IMAGE_CACHE.get(key);touchCache(IMAGE_CACHE,key,cached,IMAGE_CACHE_LIMIT);return cached;}
  const promise=new Promise((resolve,reject)=>{const img=new Image();img.decoding='async';img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('texture-image-load-failed'));img.src=key;});
  touchCache(IMAGE_CACHE,key,promise,IMAGE_CACHE_LIMIT);
  try{const img=await promise;touchCache(IMAGE_CACHE,key,Promise.resolve(img),IMAGE_CACHE_LIMIT);return img;}
  catch(e){if(IMAGE_CACHE.get(key)===promise)IMAGE_CACHE.delete(key);throw e;}
}

function ensureTextureStyles(){
  if(document.getElementById('wfgg-v35-texture-style'))return;
  const s=document.createElement('style');s.id='wfgg-v35-texture-style';s.textContent=`
  .v35texpicker{position:absolute;left:8px;right:8px;bottom:58px;z-index:5;display:flex;align-items:center;gap:5px;overflow-x:auto;overflow-y:hidden;padding:5px;background:#080b10e8;border:1px solid #30394b;border-radius:10px;scrollbar-width:thin;backdrop-filter:blur(4px)}
  .v35texlead{flex:0 0 auto;font-size:9px;color:#aeb7c6;padding:0 4px;white-space:nowrap}.v35texlead b{display:block;color:#f5f7fb;font-size:10px}
  .v35texbtn{position:relative!important;flex:0 0 52px!important;width:52px!important;height:52px!important;min-width:52px!important;padding:2px!important;border-radius:7px!important;overflow:hidden!important;background:#0b0e14!important}
  .v35texbtn.active{border-color:#a78bfa!important;box-shadow:0 0 0 1px #a78bfa inset}.v35texbtn img{display:block!important;width:46px!important;height:46px!important;max-width:46px!important;object-fit:cover!important;border-radius:5px!important}
  .v35texflag{position:absolute;left:2px;right:2px;bottom:2px;padding:1px 2px;background:#080b10dd;color:#f5f7fb;font-size:7px;line-height:1.2;text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border-radius:0 0 4px 4px}
  .v35texmode{flex:0 0 auto!important;min-width:46px!important;width:auto!important;height:52px!important;padding:4px 6px!important;font-size:9px!important;line-height:1.15!important}
  @media(max-width:420px){.v35texpicker{bottom:54px}.v35texbtn{flex-basis:46px!important;width:46px!important;height:46px!important;min-width:46px!important}.v35texbtn img{width:40px!important;height:40px!important;max-width:40px!important}.v35texmode{height:46px!important}}
  `;document.head.appendChild(s);
}

function buildGeometry(models,allObjects){
  let all=[],min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity],totalRaw=0;
  for(const m of models){
    const base=all.length;for(const v of m.verts){all.push(v);for(let k=0;k<3;k++){if(v[k]<min[k])min[k]=v[k];if(v[k]>max[k])max[k]=v[k];}}
    m.base=base;totalRaw+=m.tris.length;
  }
  const center=min.map((v,i)=>(v+max[i])/2),span=Math.max(...max.map((v,i)=>v-min[i]))||1;
  all=all.map(v=>[(v[0]-center[0])/span*2,(v[1]-center[1])/span*2,(v[2]-center[2])/span*2]);
  let tris=[];
  for(const m of models)for(const t of m.tris)tris.push({...t,a:t.a+m.base,b:t.b+m.base,c:t.c+m.base});
  let sampled=false;
  if(tris.length>MAX_TRIANGLES){sampled=true;const step=tris.length/MAX_TRIANGLES,keep=[];for(let i=0;i<MAX_TRIANGLES;i++)keep.push(tris[Math.floor(i*step)]);tris=keep;}
  const uvTriangles=tris.reduce((n,t)=>n+(t.ua&&t.ub&&t.uc?1:0),0);
  return {all,tris,totalRaw,sampled,uvTriangles,objectCount:models.length,allObjectCount:allObjects.length};
}

function createFlatRenderer(canvas,wrap,geom){
  const ctx=canvas.getContext('2d',{alpha:false});let yaw=.72,pitch=-.34,zoom=1,raf=0,textureResolver=()=>null;
  function rot(v){const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),x1=v[0]*cy+v[2]*sy,z1=-v[0]*sy+v[2]*cy;return [x1,v[1]*cp-z1*sp,v[1]*sp+z1*cp];}
  function draw(){
    const w=canvas.clientWidth,h=canvas.clientHeight;ctx.fillStyle='#050608';ctx.fillRect(0,0,w,h);const rv=geom.all.map(rot),f=Math.min(w,h)*.56*zoom,cam=4.2;
    const proj=rv.map(v=>{const d=Math.max(.35,cam-v[2]);return [w/2+v[0]*f/d,h/2-v[1]*f/d,v[2]];});const list=[];
    for(const t of geom.tris){const a=rv[t.a],b=rv[t.b],c=rv[t.c],pa=proj[t.a],pb=proj[t.b],pc=proj[t.c];if(!a||!b||!c)continue;const n=normal(a,b,c);if(n[2]<-.15)continue;list.push({z:(a[2]+b[2]+c[2])/3,pa,pb,pc,n,t});}
    list.sort((x,y)=>x.z-y.z);for(const x of list){const light=clamp(.28+.72*Math.abs(x.n[2]*.85+x.n[1]*.15),.12,1),hue=hashHue(x.t.material||x.t.label);ctx.beginPath();ctx.moveTo(x.pa[0],x.pa[1]);ctx.lineTo(x.pb[0],x.pb[1]);ctx.lineTo(x.pc[0],x.pc[1]);ctx.closePath();ctx.fillStyle=`hsl(${hue} 18% ${Math.round(20+light*48)}%)`;ctx.fill();}
    ctx.fillStyle='#d7deec';ctx.font='11px system-ui';ctx.fillText(`${geom.objectCount} OBJ · ${geom.totalRaw.toLocaleString('fr-FR')} triangles · WebGL indisponible`,10,h-12);
  }
  function resize(){const dpr=Math.min(devicePixelRatio||1,MOBILE?1.5:2),r=wrap.getBoundingClientRect(),w=Math.max(280,r.width),h=Math.max(300,r.height);canvas.width=Math.floor(w*dpr);canvas.height=Math.floor(h*dpr);canvas.style.width=w+'px';canvas.style.height=h+'px';ctx.setTransform(dpr,0,0,dpr,0,0);draw();}
  function schedule(){if(!raf)raf=requestAnimationFrame(()=>{raf=0;draw();});}
  return {mode:'canvas2d',resize,draw,schedule,setTextureResolver(fn){textureResolver=fn||(()=>null);},destroy(){if(raf)cancelAnimationFrame(raf);},setView(v){yaw=v.yaw;pitch=v.pitch;zoom=v.zoom;schedule();},getView:()=>({yaw,pitch,zoom}),textureResolver};
}

function shader(gl,type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s)||'shader compile failed');return s;}
function program(gl,vs,fs){const p=gl.createProgram();gl.attachShader(p,shader(gl,gl.VERTEX_SHADER,vs));gl.attachShader(p,shader(gl,gl.FRAGMENT_SHADER,fs));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p)||'program link failed');return p;}
function createWebGLRenderer(canvas,wrap,geom){
  const gl=canvas.getContext('webgl',{antialias:true,alpha:false,preserveDrawingBuffer:true})||canvas.getContext('experimental-webgl',{antialias:true,alpha:false,preserveDrawingBuffer:true});if(!gl)return null;
  const vs=`attribute vec3 aPos;attribute vec2 aUV;attribute vec3 aNormal;uniform float uYaw;uniform float uPitch;uniform float uZoom;uniform float uAspect;varying vec2 vUV;varying vec3 vNormal;void main(){float cy=cos(uYaw),sy=sin(uYaw),cp=cos(uPitch),sp=sin(uPitch);vec3 py=vec3(aPos.x*cy+aPos.z*sy,aPos.y,-aPos.x*sy+aPos.z*cy);vec3 p=vec3(py.x,py.y*cp-py.z*sp,py.y*sp+py.z*cp);vec3 ny=vec3(aNormal.x*cy+aNormal.z*sy,aNormal.y,-aNormal.x*sy+aNormal.z*cy);vec3 n=normalize(vec3(ny.x,ny.y*cp-ny.z*sp,ny.y*sp+ny.z*cp));float d=max(.35,4.2-p.z);float sc=1.12*uZoom/d;gl_Position=vec4(p.x*sc/max(.45,uAspect),p.y*sc,clamp((4.2-p.z)/8.0,0.0,1.0),1.0);vUV=aUV;vNormal=n;}`;
  const fs=`precision mediump float;varying vec2 vUV;varying vec3 vNormal;uniform sampler2D uTex;uniform float uUseTex;uniform vec3 uColor;void main(){vec4 base=uUseTex>.5?texture2D(uTex,vUV):vec4(uColor,1.0);float light=clamp(.28+.72*abs(vNormal.z*.85+vNormal.y*.15),.12,1.0);gl_FragColor=vec4(base.rgb*light,1.0);}`;
  const prog=program(gl,vs,fs);gl.useProgram(prog);
  const loc={pos:gl.getAttribLocation(prog,'aPos'),uv:gl.getAttribLocation(prog,'aUV'),normal:gl.getAttribLocation(prog,'aNormal'),yaw:gl.getUniformLocation(prog,'uYaw'),pitch:gl.getUniformLocation(prog,'uPitch'),zoom:gl.getUniformLocation(prog,'uZoom'),aspect:gl.getUniformLocation(prog,'uAspect'),tex:gl.getUniformLocation(prog,'uTex'),useTex:gl.getUniformLocation(prog,'uUseTex'),color:gl.getUniformLocation(prog,'uColor')};
  const groupsMap=new Map();
  function groupFor(t){const key=t.label+'|'+String(t.materialSlot||0);if(!groupsMap.has(key))groupsMap.set(key,{key,label:t.label,slot:t.materialSlot||0,material:t.material||'',pos:[],uv:[],normal:[],uvTriangles:0});return groupsMap.get(key);}
  for(const t of geom.tris){const g=groupFor(t),pa=geom.all[t.a],pb=geom.all[t.b],pc=geom.all[t.c],n=normal(pa,pb,pc),uvs=[t.ua,t.ub,t.uc],ps=[pa,pb,pc];if(t.ua&&t.ub&&t.uc)g.uvTriangles++;
    for(let i=0;i<3;i++){g.pos.push(...ps[i]);const uv=uvs[i]||[0,0];g.uv.push(uv[0],uv[1]);g.normal.push(...n);}}
  const groups=[];for(const g of groupsMap.values()){
    const make=(data,size,attr)=>{const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);return {buffer:b,size,attr};};
    g.posB=make(g.pos,3,loc.pos);g.uvB=make(g.uv,2,loc.uv);g.normalB=make(g.normal,3,loc.normal);g.count=g.pos.length/3;g.color=hslToRgb(hashHue(g.material||g.label));delete g.pos;delete g.uv;delete g.normal;groups.push(g);
  }
  gl.clearColor(.02,.025,.035,1);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.disable(gl.CULL_FACE);gl.activeTexture(gl.TEXTURE0);gl.uniform1i(loc.tex,0);
  let yaw=.72,pitch=-.34,zoom=1,raf=0,textureResolver=()=>null;const glTextures=new Map();
  function textureFrom(rec){
    if(!rec?.image||!rec?.url)return null;const key=String(rec.url);if(glTextures.has(key))return glTextures.get(key);
    try{const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,rec.image);glTextures.set(key,t);return t;}catch(e){console.debug('V35_GL_TEXTURE_FAIL',key,e);return null;}
  }
  function bindBuf(x){gl.bindBuffer(gl.ARRAY_BUFFER,x.buffer);gl.enableVertexAttribArray(x.attr);gl.vertexAttribPointer(x.attr,x.size,gl.FLOAT,false,0,0);}
  function draw(){
    const w=canvas.width,h=canvas.height;gl.viewport(0,0,w,h);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(prog);gl.uniform1f(loc.yaw,yaw);gl.uniform1f(loc.pitch,pitch);gl.uniform1f(loc.zoom,zoom);gl.uniform1f(loc.aspect,Math.max(.45,canvas.clientWidth/Math.max(1,canvas.clientHeight)));
    for(const g of groups){bindBuf(g.posB);bindBuf(g.uvB);bindBuf(g.normalB);const rec=textureResolver(g);const tex=(g.uvTriangles>0&&rec)?textureFrom(rec):null;if(tex){gl.bindTexture(gl.TEXTURE_2D,tex);gl.uniform1f(loc.useTex,1);}else gl.uniform1f(loc.useTex,0);gl.uniform3f(loc.color,g.color[0],g.color[1],g.color[2]);gl.drawArrays(gl.TRIANGLES,0,g.count);}
  }
  function resize(){const dpr=Math.min(devicePixelRatio||1,MOBILE?1.5:2),r=wrap.getBoundingClientRect(),w=Math.max(280,r.width),h=Math.max(300,r.height),nw=Math.floor(w*dpr),nh=Math.floor(h*dpr);if(canvas.width!==nw||canvas.height!==nh){canvas.width=nw;canvas.height=nh;}canvas.style.width=w+'px';canvas.style.height=h+'px';draw();}
  function schedule(){if(!raf)raf=requestAnimationFrame(()=>{raf=0;draw();});}
  function destroy(){if(raf)cancelAnimationFrame(raf);for(const g of groups){[g.posB,g.uvB,g.normalB].forEach(x=>x?.buffer&&gl.deleteBuffer(x.buffer));}for(const t of glTextures.values())gl.deleteTexture(t);gl.deleteProgram(prog);}
  return {mode:'webgl',resize,draw,schedule,setTextureResolver(fn){textureResolver=fn||(()=>null);schedule();},destroy,setView(v){yaw=v.yaw;pitch=v.pitch;zoom=v.zoom;schedule();},getView:()=>({yaw,pitch,zoom}),stats:()=>({groups:groups.length,textures:glTextures.size})};
}

async function mount(host,manifest){
  ensureTextureStyles();
  host.innerHTML='<div class="v33modelwrap"><canvas class="v33modelcanvas"></canvas><div class="v33modelhud">Préparation de l’aperçu 3D réel…</div></div>';
  const wrap=host.querySelector('.v33modelwrap'),canvas=host.querySelector('canvas'),hud=host.querySelector('.v33modelhud');
  const allObjects=(manifest.objects||[]),objects=allObjects.slice(0,MAX_OBJECTS),models=[],failures=[];
  for(let start=0;start<objects.length;start+=FETCH_BATCH){
    const batch=objects.slice(start,start+FETCH_BATCH);hud.textContent=`Chargement 3D réel… ${Math.min(start+batch.length,objects.length)}/${objects.length}`;
    const results=await Promise.allSettled(batch.map(fetchModelObject));results.forEach((res,i)=>{if(res.status==='fulfilled')models.push(res.value);else failures.push((batch[i]?.path||'OBJ')+': '+res.reason)});await new Promise(resolve=>setTimeout(resolve,0));
  }
  if(!models.length){hud.textContent='Aucune géométrie OBJ lisible.';throw new Error('Aucune géométrie OBJ lisible');}
  const geom=buildGeometry(models,allObjects);let renderer=createWebGLRenderer(canvas,wrap,geom);if(!renderer)renderer=createFlatRenderer(canvas,wrap,geom);

  let view={yaw:.72,pitch:-.34,zoom:1},drag=false,lastX=0,lastY=0,pinch=null;
  function syncView(){renderer.setView(view);}
  canvas.addEventListener('pointerdown',e=>{drag=true;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture?.(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(!drag)return;view.yaw+=(e.clientX-lastX)*.012;view.pitch=clamp(view.pitch+(e.clientY-lastY)*.012,-1.45,1.45);lastX=e.clientX;lastY=e.clientY;syncView();});
  canvas.addEventListener('pointerup',()=>drag=false);canvas.addEventListener('pointercancel',()=>drag=false);
  canvas.addEventListener('wheel',e=>{e.preventDefault();view.zoom=clamp(view.zoom*Math.exp(-e.deltaY*.001),.35,3.5);syncView();},{passive:false});
  canvas.addEventListener('touchstart',e=>{if(e.touches.length===2)pinch=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);},{passive:true});
  canvas.addEventListener('touchmove',e=>{if(e.touches.length===2&&pinch){const d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);view.zoom=clamp(view.zoom*d/pinch,.35,3.5);pinch=d;syncView();}},{passive:true});

  const exactBindings=normalizeExactBindings(manifest),exactByObject=new Map();let textureMode='auto',overrideTexture=null,autoFallback=null,picker=null,textureChoices=[];
  function exactSlotMap(objectPath){if(!exactByObject.has(objectPath))exactByObject.set(objectPath,new Map());return exactByObject.get(objectPath);}
  function chooseAutoBinding(bindings){return bindings.find(x=>x.semantic==='color')||bindings.find(x=>x.semantic==='unknown')||null;}
  const groupedExact=new Map();for(const b of exactBindings){const key=b.objectPath+'|'+String(b.materialSlot||0);if(!groupedExact.has(key))groupedExact.set(key,[]);groupedExact.get(key).push(b);}
  renderer.setTextureResolver(group=>{
    if(textureMode==='off')return null;if(textureMode==='override'&&overrideTexture)return overrideTexture;
    const sm=exactByObject.get(group.label);return sm?.get(group.slot)||sm?.get(0)||autoFallback||null;
  });

  function refreshHud(){
    const limited=allObjects.length>objects.length?` · aperçu ${objects.length}/${allObjects.length} OBJ`:'';
    const texInfo=exactBindings.length?` · ${exactBindings.length} liaison(s) texture exactes`:'';
    hud.innerHTML=`<b>APERÇU 3D RÉEL</b> · glisser pour tourner · pincer pour zoomer<br><span>${(manifest.bundleIds||[]).length} bundle(s) · ${models.length} OBJ chargés${limited}${geom.sampled?' · triangles décimés':''} · ${geom.uvTriangles.toLocaleString('fr-FR')} triangles UV · ${renderer.mode.toUpperCase()}${texInfo}${manifest.assemblySpeed?' · '+esc(manifest.assemblySpeed):''}</span>`;
  }
  refreshHud();

  function markPickerActive(){
    if(!picker)return;picker.querySelectorAll('[data-mode],[data-tex-key]').forEach(b=>b.classList.remove('active'));
    const mode=picker.querySelector(`[data-mode="${textureMode}"]`);if(textureMode!=='override'&&mode)mode.classList.add('active');
    if(textureMode==='override'&&overrideTexture){const b=picker.querySelector(`[data-tex-key="${CSS.escape(candidateKey(overrideTexture.source||overrideTexture))}"]`);if(b)b.classList.add('active');}
  }
  async function setOverride(source){
    try{const image=await loadImage(source.url);overrideTexture={url:source.url,image,source};textureMode='override';markPickerActive();renderer.schedule();}
    catch(e){console.debug('V35_TEXTURE_OVERRIDE_FAIL',source?.url,e);}
  }
  function setAuto(){textureMode='auto';overrideTexture=null;markPickerActive();renderer.schedule();}
  function setOff(){textureMode='off';overrideTexture=null;markPickerActive();renderer.schedule();}

  function createPicker(choices){
    textureChoices=choices;picker?.remove();picker=document.createElement('div');picker.className='v35texpicker';
    const lead=document.createElement('span');lead.className='v35texlead';lead.innerHTML='<b>Textures 3D</b>UV du modèle';picker.appendChild(lead);
    const auto=document.createElement('button');auto.type='button';auto.className='v35texmode';auto.dataset.mode='auto';auto.innerHTML='AUTO<br><span style="font-size:7px;color:#aeb7c6">jeu</span>';auto.onclick=setAuto;picker.appendChild(auto);
    const off=document.createElement('button');off.type='button';off.className='v35texmode';off.dataset.mode='off';off.textContent='OFF';off.onclick=setOff;picker.appendChild(off);
    for(const source of choices){
      const b=document.createElement('button');b.type='button';b.className='v35texbtn';const key=candidateKey(source);b.dataset.texKey=key;b.title=(source.exact?'Liaison Unity exacte · ':'Texture candidate · ')+(source.textureName||source.alias_name||source.path||source.asset_path||key);
      const img=document.createElement('img');img.loading='lazy';img.src=source.url;img.alt='texture';b.appendChild(img);const flag=document.createElement('span');flag.className='v35texflag';const sem=String(source.semantic||semanticFromName(source)).toUpperCase();flag.textContent=(source.exact?'✓ ':'')+sem;b.appendChild(flag);b.onclick=()=>setOverride(source);picker.appendChild(b);
    }
    wrap.appendChild(picker);markPickerActive();
  }

  // Load exact color/unknown bindings first. Each object/material slot receives the texture tied to
  // the same renderer Material PPtr; OBJ UVs then select the correct regions of the atlas.
  const exactLoadJobs=[];
  for(const [key,bindings] of groupedExact){const chosen=chooseAutoBinding(bindings);if(!chosen)continue;const [objectPath,slotRaw]=key.split('|');const slot=Number(slotRaw)||0;exactLoadJobs.push((async()=>{try{const image=await loadImage(chosen.url);exactSlotMap(objectPath).set(slot,{url:chosen.url,image,source:chosen});}catch(e){console.debug('V35_EXACT_TEXTURE_LOAD_FAIL',chosen.url,e);}})());}
  Promise.allSettled(exactLoadJobs).then(()=>renderer.schedule());

  const embedded=(manifest.files||[]).filter(x=>['png','jpg','jpeg','webp'].includes(String(x.kind||'').toLowerCase())).map(x=>({...x,semantic:semanticFromName(x),exact:!!x.exact}));
  const exactUnique=[];const exactSeen=new Set();for(const x of [...exactBindings,...embedded]){const k=candidateKey(x);if(exactSeen.has(k))continue;exactSeen.add(k);exactUnique.push(x);}
  createPicker(exactUnique.slice(0,MAX_TEXTURE_CHOICES));
  discoverTextureCandidates(manifest).then(async candidates=>{
    const seen=new Set(exactUnique.map(candidateKey)),merged=[...exactUnique];for(const x of candidates){const k=candidateKey(x);if(!seen.has(k)){seen.add(k);merged.push(x);}}
    createPicker(merged.slice(0,MAX_TEXTURE_CHOICES));
    // When exact bindings are unavailable, use a very strong same-folder color candidate as a
    // reversible AUTO fallback. Otherwise leave neutral shading until the user taps a thumbnail.
    if(!exactBindings.length){const strong=candidates.find(x=>x.semantic==='color'&&textureScore(x,manifest)>=15);if(strong){try{const image=await loadImage(strong.url);autoFallback={url:strong.url,image,source:strong};renderer.schedule();}catch{}}}
  });

  const ro=new ResizeObserver(()=>renderer.resize());ro.observe(wrap);renderer.resize();syncView();
  return {
    canvas,manifest,failures,
    textureState:()=>({mode:textureMode,exactBindings:exactBindings.length,choices:textureChoices.length,uvTriangles:geom.uvTriangles,renderer:renderer.mode}),
    setTexture:setOverride,clearTexture:setAuto,disableTextures:setOff,
    destroy(){ro.disconnect();renderer.destroy();picker?.remove();}
  };
}

window.WFGGModelViewer={mount,prefetch,cacheStats:()=>({objects:OBJECT_CACHE.size,images:IMAGE_CACHE.size,objectLimit:OBJECT_CACHE_LIMIT,imageLimit:IMAGE_CACHE_LIMIT,maxPreviewObjects:MAX_OBJECTS,batch:FETCH_BATCH,uvTextureViewer:'v35.2'})};
})();

/* Earliest possible legacy-error shield.
   This file is loaded before the base inline init() call, so it is the only reliable place to
   prevent the historical selector from flashing a technical error while V34 is still taking over.
   V34 final error boxes are explicitly marked data-v34-final=1 and are never suppressed. */
(()=>{
'use strict';
const INTERIM=/RUNTIME_3D_OBJECT_MISMATCH|RUNTIME_TARGET_OBJECT_NOT_FOUND/;
function shield(){
  const stage=document.getElementById('stage');if(!stage)return false;
  const box=stage.querySelector('.errorbox');if(!box||box.dataset.v34Final==='1')return false;
  const text=box.textContent||'';if(!INTERIM.test(text))return false;
  if(box.dataset.wfggShielded==='1')return true;
  const original=box.outerHTML;
  const neutral=document.createElement('div');neutral.className='empty';neutral.dataset.wfggInterim='1';
  neutral.innerHTML='<b>Finalisation de l\'aperçu…</b><br><span class="hint">Reconstruction exacte en cours. Le diagnostic intermédiaire reste disponible dans Termux.</span>';
  box.replaceWith(neutral);
  console.debug('V34_EARLY_ERROR_SHIELD',text.slice(0,180));
  setTimeout(()=>{
    if(window.WFGGPreviewAccelerator)return;
    const n=stage.querySelector('[data-wfgg-interim="1"]');if(n)n.outerHTML=original;
  },12000);
  return true;
}
function install(){
  const stage=document.getElementById('stage');if(!stage)return;
  const obs=new MutationObserver(shield);obs.observe(stage,{childList:true,subtree:true});shield();
  window.WFGGEarlyPreviewShield={version:'35.2',shield,state:()=>({active:true,accelerator:!!window.WFGGPreviewAccelerator})};
  console.info('V35_EARLY_PREVIEW_SHIELD installed before-base-init=ON');
}
if(document.readyState==='loading')install();else install();
})();

/* Result-strip synchronisation.
   IMPORTANT: appending another search page must not recenter the strip on the old active card.
   Centering happens only after an explicit selection/click/Previous/Next call. */
(()=>{
'use strict';
function centerActiveCard(behavior='smooth'){
  const strip=document.getElementById('results'),active=strip?.querySelector('.card.active');
  if(!strip||!active)return;
  if(matchMedia('(min-width:980px)').matches){active.scrollIntoView({block:'nearest',inline:'nearest',behavior});return;}
  strip.style.scrollSnapType='x proximity';strip.querySelectorAll('.card').forEach(c=>c.style.scrollSnapAlign='center');
  const sr=strip.getBoundingClientRect(),ar=active.getBoundingClientRect(),delta=(ar.left+ar.width/2)-(sr.left+sr.width/2);
  strip.scrollTo({left:Math.max(0,strip.scrollLeft+delta),behavior});
}
window.WFGGResultStripSync=centerActiveCard;
function install(){
  const strip=document.getElementById('results');if(!strip)return;
  strip.addEventListener('click',e=>{if(e.target.closest('.card'))requestAnimationFrame(()=>centerActiveCard('smooth'));});
  window.addEventListener('resize',()=>requestAnimationFrame(()=>centerActiveCard('auto')),{passive:true});requestAnimationFrame(()=>centerActiveCard('auto'));
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
