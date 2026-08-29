(()=>{'use strict';
const host=document.querySelector('.world-blur');if(!host)return;
const PACK='local_assets/lastwar-formation-layer0-renderpack-v1/';
const MANIFEST='master-assets-v2/meta/formation-layer0-renderpack-v1.json';
const PIPELINE='master-assets-v2/meta/formation-background-pipeline-v1.json';
const RUNTIME_WORLD='local_assets/lastwar-formation-runtime-world-v1/world-source.png';
const native={blurRate:.5,blurScale:89.4000015258789,radius:222,lightness:.9039999842643738,saturation:.47999998927116394};
const note=document.createElement('div');note.className='lw-world-note';
const loadJSON=async u=>{const r=await fetch(u,{cache:'no-store'});if(!r.ok)throw Error(`${r.status} ${u}`);return r.json()};
const image=src=>new Promise((ok,no)=>{const i=new Image();i.onload=()=>ok(i);i.onerror=()=>no(Error(src));i.src=src+(src.includes('?')?'&':'?')+'v=004'});
const optionalImage=async src=>{try{return await image(src)}catch{return null}};
const byName=(m,n)=>(m.textures||[]).find(t=>t.name===n);
const blurPx=Math.max(2.5,Math.min(9,(native.radius/native.blurScale)*(1+native.blurRate)));
host.style.setProperty('--lw-native-blur-px',`${blurPx.toFixed(3)}px`);
host.style.setProperty('--lw-native-saturation',String(native.saturation));
host.style.setProperty('--lw-native-lightness',String(native.lightness));
const debug=new URLSearchParams(location.search).get('debug')==='1';
function finish(source,detail=''){
 host.dataset.source=source;
 host.dataset.blurMaterial='Lapu_BlurUI002';
 host.dataset.blurRate=String(native.blurRate);host.dataset.blurScale=String(native.blurScale);host.dataset.radius=String(native.radius);
 host.appendChild(note);
 if(debug)note.textContent=`Layer0 · ${source} · BlurUI rate=${native.blurRate} scale=${native.blurScale} radius=${native.radius} light=${native.lightness} sat=${native.saturation}${detail?' · '+detail:''}`;
}
(async()=>{try{
 /* FormationBg est un RawImage alimente au runtime. Si une source Monde propre
    est fournie localement, elle est prioritaire : aucune image Formation baked. */
 const runtime=await optionalImage(RUNTIME_WORLD);
 if(runtime){
   const img=document.createElement('img');img.className='lw-world-runtime';img.src=runtime.src;img.alt='';
   host.replaceChildren(img);finish('native-runtime-world');return;
 }
 const [manifest]=await Promise.all([loadJSON(MANIFEST),loadJSON(PIPELINE).catch(()=>null)]);
 const canvas=document.createElement('canvas');canvas.className='lw-world-canvas';host.replaceChildren(canvas);
 const controlMeta=byName(manifest,'SplatControl_World')||byName(manifest,'SplatControl_City_3')||byName(manifest,'Terrain_splatmap_01');
 const macroMeta=byName(manifest,'MixWorldMap_basecolor')||byName(manifest,'MixWorldMap_basecolor_2')||byName(manifest,'GrassMap01_basecolor');
 const grassMeta=byName(manifest,'GrassMap01_basecolor')||macroMeta;
 const layerNames=['O_terrain_grass01_D','O_terrain_grass04_D','O_terrain_desert_02_D','O_terrain_DesertStorm_02_D'];
 const layers=layerNames.map(n=>byName(manifest,n)).filter(Boolean);
 if(!controlMeta||!macroMeta||layers.length<2)throw Error('pack World/Terrain incomplet');
 while(layers.length<4)layers.push(layers[layers.length-1]);
 const metas=[controlMeta,macroMeta,grassMeta,...layers.slice(0,4)];
 const ims=await Promise.all(metas.map(x=>image(PACK+x.file)));
 const [ci,mi,gi,...li]=ims;
 const gl=canvas.getContext('webgl',{alpha:false,antialias:true,premultipliedAlpha:false});if(!gl)throw Error('WebGL indisponible');
 const vs='attribute vec2 p;varying vec2 v;void main(){v=(p+1.0)*.5;gl_Position=vec4(p,0.,1.);}';
 const fs=`precision mediump float;varying vec2 v;uniform sampler2D c,m,g,t0,t1,t2,t3;
 float lum(vec3 q){return dot(q,vec3(.299,.587,.114));}
 void main(){
  vec4 w=texture2D(c,v);float z=w.r+w.g+w.b+w.a;if(z<.001)w=vec4(1.,0.,0.,0.);else w/=z;
  vec2 uv=v*6.0;vec3 a=texture2D(t0,uv).rgb;vec3 b=texture2D(t1,uv*1.09).rgb;vec3 d=texture2D(t2,uv*.91).rgb;vec3 e=texture2D(t3,uv*1.18).rgb;
  vec3 terrain=a*w.r+b*w.g+d*w.b+e*w.a;
  vec3 macro=texture2D(m,v*.92+vec2(.035,.04)).rgb;
  vec3 grass=texture2D(g,v*1.13+vec2(.08,-.03)).rgb;
  float macroL=lum(macro);float grassL=lum(grass);
  float shade=clamp(.88+macroL*.18+(grassL-.5)*.08,.82,1.08);
  vec3 col=mix(terrain,macro,.28);col=mix(col,grass,.08);col*=shade;
  gl_FragColor=vec4(col,1.0);
 }`;
 const sh=(type,src)=>{const q=gl.createShader(type);gl.shaderSource(q,src);gl.compileShader(q);if(!gl.getShaderParameter(q,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(q));return q};
 const pr=gl.createProgram();gl.attachShader(pr,sh(gl.VERTEX_SHADER,vs));gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,fs));gl.linkProgram(pr);if(!gl.getProgramParameter(pr,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(pr));gl.useProgram(pr);
 const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);const pa=gl.getAttribLocation(pr,'p');gl.enableVertexAttribArray(pa);gl.vertexAttribPointer(pa,2,gl.FLOAT,false,0,0);
 const tex=(im,unit,name,repeat=true)=>{const t=gl.createTexture();gl.activeTexture(gl.TEXTURE0+unit);gl.bindTexture(gl.TEXTURE_2D,t);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,repeat?gl.REPEAT:gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,repeat?gl.REPEAT:gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);gl.uniform1i(gl.getUniformLocation(pr,name),unit)};
 tex(ci,0,'c',false);tex(mi,1,'m',true);tex(gi,2,'g',true);li.forEach((im,i)=>tex(im,i+3,'t'+i,true));
 const draw=()=>{const d=Math.min(2,devicePixelRatio||1),w=Math.max(1,host.clientWidth),h=Math.max(1,host.clientHeight);if(canvas.width!==Math.round(w*d)||canvas.height!==Math.round(h*d)){canvas.width=Math.round(w*d);canvas.height=Math.round(h*d);gl.viewport(0,0,canvas.width,canvas.height)}gl.drawArrays(gl.TRIANGLES,0,6)};draw();addEventListener('resize',draw);
 finish('native-world-assets-fallback',[controlMeta.name,macroMeta.name,grassMeta.name].join(' / '));
 }catch(e){host.classList.add('lw-world-error');host.replaceChildren();host.appendChild(note);note.textContent='Layer0 indisponible : '+e.message;console.error(e)}})();
})();
