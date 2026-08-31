const root=document.getElementById('bundleViewer');
const $=(id)=>document.getElementById(id);
const bundleId=(new URLSearchParams(location.search).get('bundle')||'14169').replace(/[^0-9-]/g,'');
let manifest=null;
let THREE=null,OrbitControls=null,OBJLoader=null;

function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function summaryCard(label,value){return `<div class="stat"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;}
function typeSummary(types){return Object.entries(types||{}).sort((a,b)=>b[1]-a[1]).slice(0,8).map(([k,v])=>`${k}:${v}`).join(' · ');}

function bindTabs(){
  root.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{
    root.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));
    root.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.dataset.view===b.dataset.tab));
  }));
}

function openTexture(t){
  $('dialogTitle').textContent=`${t.name||'Texture'} — ${t.width||'?'}×${t.height||'?'} — b${t.bundleId} p${t.pathID}`;
  $('dialogImage').src=t.src;$('textureDialog').showModal();
}

function renderSummary(){
  const c=manifest.counts||{},b=manifest.bundle||{};
  $('bundleSubtitle').textContent=`Bundle ${b.bundleId} · ${b.assetBundleName||'sans nom'} · ${c.objects||0} objets sérialisés`;
  $('summary').innerHTML=[
    summaryCard('Bundle',b.bundleId),summaryCard('Objets',c.objects||0),summaryCard('Matériaux',c.materials||0),summaryCard('Textures PNG',c.texturesExported||0),summaryCard('Meshes OBJ',c.meshesExported||0),summaryCard('Renderers',c.renderers||0),summaryCard('Reconstructibles',c.reconstructableRenderers||0),summaryCard('Types',Object.keys(c.types||{}).length)
  ].join('');
  const d=manifest.diagnostics||{};
  const notes=[];
  if((c.reconstructableRenderers||0)===0)notes.push('Ce bundle ne contient aucun Renderer+Mesh reconstructible avec les liens actuellement résolus. La vue Matériaux/Textures reste complète pour les assets exportés.');
  if((d.textureFailures||[]).length)notes.push(`${d.textureFailures.length} texture(s) n'ont pas pu être décodées.`);
  if((d.meshFailures||[]).length)notes.push(`${d.meshFailures.length} mesh(es) n'ont pas pu être exportés.`);
  if(notes.length)$('notice').textContent=`${$('notice').textContent} ${notes.join(' ')}`;
}

function renderMaterials(filter=''){
  const q=filter.trim().toLowerCase();
  const list=(manifest.materials||[]).filter(m=>!q||`${m.name} ${m.pathID} ${(m.shader||{}).name||''}`.toLowerCase().includes(q));
  const frag=document.createDocumentFragment();
  for(const m of list){
    const card=document.createElement('article');card.className=`material-card ${m.selectedHuman?'selected':''}`;
    const head=document.createElement('div');head.className='material-head';head.innerHTML=`<strong>${esc(m.name||'(sans nom)')}</strong><div class="meta">b${esc(m.bundleId)} · p${esc(m.pathID)}${m.shader?.name?` · shader ${esc(m.shader.name)}`:''}</div>${m.selectedHuman?'<span class="tag">Sélection humaine</span>':''}`;card.append(head);
    const slots=document.createElement('div');slots.className='slots';
    for(const s of (m.textureSlots||[])){
      const row=document.createElement('div');row.className='slot';const r=s.resolved;
      const label=document.createElement('div');label.className='slot-name';label.textContent=`${s.slot} → ${r?.name||`fileID ${s.fileID} / p${s.pathID}`}`;row.append(label);
      if(s.src){const img=document.createElement('img');img.src=s.src;img.loading='lazy';img.alt=r?.name||s.slot;img.addEventListener('click',()=>{const t=(manifest.textures||[]).find(x=>x.src===s.src);if(t)openTexture(t);});row.append(img);}else{const miss=document.createElement('div');miss.className='slot-missing';miss.textContent=r?'Texture résolue mais non exportée':'Référence non résolue';row.append(miss);}
      slots.append(row);
    }
    if(!(m.textureSlots||[]).length){const none=document.createElement('div');none.className='slot-missing';none.style.margin='0 10px 10px';none.textContent='Aucune Texture2D sérialisée dans m_TexEnvs';slots.append(none);}
    card.append(slots);frag.append(card);
  }
  $('materialsGrid').replaceChildren(frag);
}

function renderTextures(filter=''){
  const q=filter.trim().toLowerCase();
  const list=(manifest.textures||[]).filter(t=>!q||`${t.name} ${t.pathID} ${t.bundleId} ${t.format}`.toLowerCase().includes(q));
  const frag=document.createDocumentFragment();
  for(const t of list){
    const card=document.createElement('article');card.className='texture-card';const btn=document.createElement('button');btn.type='button';
    btn.innerHTML=`<img loading="lazy" src="${esc(t.src)}" alt="${esc(t.name||'Texture')}"><div class="texture-info"><strong>${esc(t.name||'(sans nom)')}</strong><span>${esc(t.width)}×${esc(t.height)} · ${esc(t.format)} · b${esc(t.bundleId)}</span><span>p${esc(t.pathID)} · ${esc(t.reason||'')}</span></div>`;
    btn.addEventListener('click',()=>openTexture(t));card.append(btn);frag.append(card);
  }
  $('texturesGrid').replaceChildren(frag);
}

function renderObjects(filter=''){
  const q=filter.trim().toLowerCase();
  const list=(manifest.objects||[]).filter(o=>!q||`${o.type} ${o.name} ${o.pathID} ${o.serializedFile}`.toLowerCase().includes(q));
  const frag=document.createDocumentFragment();
  for(const o of list.slice(0,2500)){
    const tr=document.createElement('tr');tr.innerHTML=`<td>${esc(o.type)}</td><td>${esc(o.name||'—')}</td><td>${esc(o.pathID)}</td><td>${esc(o.ptrCount)}</td><td>${esc(o.serializedFile)}</td>`;frag.append(tr);
  }
  $('objectsBody').replaceChildren(frag);
}

class ThreeStage{
  constructor(mount){this.mount=mount;this.renderer=null;this.scene=null;this.camera=null;this.controls=null;this.content=null;this.wire=false;this.resizeObserver=null;this.animation=0;}
  init(){
    if(!THREE){this.mount.innerHTML='<div class="empty-3d">Moteur 3D indisponible. Les onglets Matériaux, Textures et Objets restent utilisables.</div>';return false;}
    this.mount.replaceChildren();this.scene=new THREE.Scene();this.scene.background=new THREE.Color(0x07070a);
    this.camera=new THREE.PerspectiveCamera(45,1,.01,100000);this.camera.position.set(4,3,6);
    this.renderer=new THREE.WebGLRenderer({antialias:true});this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.mount.append(this.renderer.domElement);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);this.controls.enableDamping=true;
    const amb=new THREE.HemisphereLight(0xffffff,0x303040,1.6);this.scene.add(amb);const key=new THREE.DirectionalLight(0xffffff,2.2);key.position.set(4,8,5);this.scene.add(key);
    this.content=new THREE.Group();this.scene.add(this.content);
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(this.mount);this.resize();
    const loop=()=>{this.animation=requestAnimationFrame(loop);this.controls.update();this.renderer.render(this.scene,this.camera);};loop();return true;
  }
  resize(){if(!this.renderer)return;const r=this.mount.getBoundingClientRect(),w=Math.max(1,r.width),h=Math.max(1,r.height);this.renderer.setSize(w,h,false);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();}
  clear(){if(!this.content)return;while(this.content.children.length){const x=this.content.children.pop();x.traverse?.(o=>{if(o.geometry)o.geometry.dispose?.();if(o.material){const ms=Array.isArray(o.material)?o.material:[o.material];ms.forEach(m=>m.dispose?.());}});}}
  neutralize(obj){obj.traverse(o=>{if(o.isMesh){o.material=new THREE.MeshStandardMaterial({color:0xbcb8c2,roughness:.86,metalness:0,wireframe:this.wire,side:THREE.DoubleSide});}});}
  fit(target=this.content){if(!target)return;const box=new THREE.Box3().setFromObject(target);if(box.isEmpty())return;const size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3()),max=Math.max(size.x,size.y,size.z,0.001);const dist=max/(2*Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2)))*1.45;this.camera.position.set(center.x+dist*.72,center.y+dist*.55,center.z+dist);this.camera.near=Math.max(dist/10000,.001);this.camera.far=Math.max(dist*100,1000);this.camera.updateProjectionMatrix();this.controls.target.copy(center);this.controls.update();}
  setWire(){this.wire=!this.wire;this.content?.traverse(o=>{if(o.isMesh&&o.material){const ms=Array.isArray(o.material)?o.material:[o.material];ms.forEach(m=>m.wireframe=this.wire);}});return this.wire;}
  async loadObj(src,name='mesh'){if(!THREE||!OBJLoader)return null;const loader=new OBJLoader();const o=await loader.loadAsync(src);o.name=name;this.neutralize(o);return o;}
}

let sceneStage=null,meshStage=null;
async function renderScene3D(){
  sceneStage=new ThreeStage($('threeMount'));if(!sceneStage.init())return;
  const list=(manifest.scene||[]).filter(x=>x.reconstructable&&x.mesh?.src);
  if(!list.length){sceneStage.mount.innerHTML='<div class="empty-3d">Aucun Renderer + Mesh exactement reconstructible dans ce bundle. Cela signifie que ce bundle est probablement un bundle de ressources (par exemple matériaux/textures) plutôt qu’un bundle de scène.</div>';return;}
  const groups=new Map();
  for(const x of list){
    try{
      const obj=await sceneStage.loadObj(x.mesh.src,x.gameObject?.name||x.mesh.name);if(!obj)continue;const g=new THREE.Group();g.userData.record=x;g.name=x.gameObject?.name||x.mesh.name;g.add(obj);
      const tr=x.transform;if(tr){const p=tr.localPosition||[0,0,0],r=tr.localRotation||[0,0,0,1],s=tr.localScale||[1,1,1];g.position.set(+p[0]||0,+p[1]||0,+p[2]||0);g.quaternion.set(+r[0]||0,+r[1]||0,+r[2]||0,Number.isFinite(+r[3])?+r[3]:1);g.scale.set(Number.isFinite(+s[0])?+s[0]:1,Number.isFinite(+s[1])?+s[1]:1,Number.isFinite(+s[2])?+s[2]:1);}
      groups.set(String(x.gameObject?.pathID||''),g);
    }catch(e){console.warn('OBJ scene load failed',x,e);}
  }
  for(const [id,g] of groups){const rec=g.userData.record,parent=rec.parentGameObjectPathID?groups.get(String(rec.parentGameObjectPathID)):null;(parent||sceneStage.content).add(g);}
  sceneStage.fit();
  renderSceneList(groups);
}

function renderSceneList(groups=new Map()){
  const list=(manifest.scene||[]).filter(x=>x.reconstructable&&x.mesh?.src),frag=document.createDocumentFragment();
  if(!list.length){const d=document.createElement('div');d.className='status';d.textContent='Aucun objet de rendu reconstructible.';frag.append(d);}
  for(const x of list){const b=document.createElement('button');b.className='item';b.type='button';b.innerHTML=`<strong>${esc(x.gameObject?.name||x.mesh?.name||'Objet')}</strong><span>${esc(x.renderer?.type||'Renderer')} · mesh ${esc(x.mesh?.name||'—')}</span><span>GO p${esc(x.gameObject?.pathID||'—')}</span>`;b.addEventListener('click',()=>{const g=groups.get(String(x.gameObject?.pathID||''));if(g)sceneStage.fit(g);});frag.append(b);}
  $('sceneList').replaceChildren(frag);
}

async function initMeshViewer(){
  meshStage=new ThreeStage($('meshMount'));meshStage.init();renderMeshList();
}
function renderMeshList(filter=''){
  const q=filter.trim().toLowerCase(),list=(manifest.meshes||[]).filter(m=>!q||`${m.name} ${m.pathID} ${m.bundleId}`.toLowerCase().includes(q));const frag=document.createDocumentFragment();
  if(!list.length){const d=document.createElement('div');d.className='status';d.textContent='Aucun Mesh OBJ exporté pour ce bundle.';frag.append(d);}
  for(const m of list){const b=document.createElement('button');b.className='item';b.type='button';b.innerHTML=`<strong>${esc(m.name||'(sans nom)')}</strong><span>b${esc(m.bundleId)} · p${esc(m.pathID)}</span><span>${esc(m.reason||'')}</span>`;b.addEventListener('click',async()=>{if(!meshStage||!THREE)return;root.querySelectorAll('#meshList .item').forEach(x=>x.classList.remove('active'));b.classList.add('active');meshStage.clear();try{const o=await meshStage.loadObj(m.src,m.name);if(o){meshStage.content.add(o);meshStage.fit();}}catch(e){meshStage.mount.innerHTML=`<div class="empty-3d">Échec de lecture OBJ : ${esc(e.message)}</div>`;}});frag.append(b);}
  $('meshList').replaceChildren(frag);
}

async function init3D(){
  try{
    THREE=await import('three');({OrbitControls}=await import('three/addons/controls/OrbitControls.js'));({OBJLoader}=await import('three/addons/loaders/OBJLoader.js'));
  }catch(e){console.warn('Three.js unavailable',e);$('notice').textContent+=' Le moteur Three.js n’a pas pu être chargé; la consultation 2D reste disponible.';}
  await renderScene3D();await initMeshViewer();
}

async function load(){
  bindTabs();$('dialogClose').addEventListener('click',()=>$('textureDialog').close());
  $('materialSearch').addEventListener('input',e=>renderMaterials(e.target.value));$('textureSearch').addEventListener('input',e=>renderTextures(e.target.value));$('objectSearch').addEventListener('input',e=>renderObjects(e.target.value));$('meshSearch').addEventListener('input',e=>renderMeshList(e.target.value));
  try{
    const r=await fetch(`/lab/bundle-reconstruction-data/${encodeURIComponent(bundleId)}/manifest.json?t=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);manifest=await r.json();
  }catch(e){$('bundleSubtitle').textContent=`Manifeste du bundle ${bundleId} absent. Lance d'abord le script de construction.`;$('notice').textContent=`Données locales introuvables : ${e.message}. Commande attendue : bash scripts/lastwar-bundle-reconstruction-viewer-build-v1.sh ${bundleId}`;root.querySelectorAll('.tab').forEach(x=>x.disabled=true);return;}
  renderSummary();renderMaterials();renderTextures();renderObjects();
  $('resetCamera').addEventListener('click',()=>sceneStage?.fit());$('toggleWire').addEventListener('click',e=>{if(sceneStage)e.currentTarget.classList.toggle('primary',sceneStage.setWire());});$('meshResetCamera').addEventListener('click',()=>meshStage?.fit());$('meshToggleWire').addEventListener('click',e=>{if(meshStage)e.currentTarget.classList.toggle('primary',meshStage.setWire());});
  init3D();
}
load();
