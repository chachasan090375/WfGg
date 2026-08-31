(() => {
  const $ = (id) => document.getElementById(id);
  const loadingPanel=$('loadingPanel'), emptyPanel=$('emptyPanel'), gridPanel=$('gridPanel'), viewerPanel=$('viewerPanel'), resultsPanel=$('resultsPanel');
  const mainImage=$('mainImage'), stage=$('stage'), imageViewport=$('imageViewport');
  const counter=$('counter'), voteCounter=$('voteCounter'), fileName=$('fileName'), dimensions=$('dimensions'), identity=$('identity'), scopeMeta=$('scopeMeta'), format=$('format'), analyticMeta=$('analyticMeta');
  const thumbStrip=$('thumbStrip'), yesButton=$('yesButton'), noButton=$('noButton'), unsureButton=$('unsureButton');
  const reviewGrid=$('reviewGrid'), gridFilter=$('gridFilter'), gridPageInfo=$('gridPageInfo');
  const yesGrid=$('yesGrid'), unsureGrid=$('unsureGrid'), resultsSummary=$('resultsSummary'), unsureSummary=$('unsureSummary');
  const blurControl=$('blurControl'), blurRange=$('blurRange'), blurValue=$('blurValue');
  const STORAGE_KEY='wfgg-lastwar-formation-visual-human-search-v2';
  let manifest=null,items=[],index=0,gridPage=0,gridPageSize=12,viewMode='fit',touchStartX=null,touchStartY=null;

  const key=(item)=>`${item.id || `${item.bundleId}:${item.pathID}`}:${item.sha256 || item.src}`;
  function loadVotes(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}')||{}}catch{return {}}}
  function saveVotes(){const out={};for(const x of items)if(['yes','no','unsure'].includes(x.vote))out[key(x)]=x.vote;localStorage.setItem(STORAGE_KEY,JSON.stringify(out));}
  function reviewedCount(){return items.filter(x=>x.vote).length;}
  function firstUnvoted(){return items.findIndex(x=>!x.vote);}

  async function loadManifest(){
    try{
      const response=await fetch(`/lab/formation-texture-review-v2/manifest.json?t=${Date.now()}`,{cache:'no-store'});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      manifest=await response.json();const list=Array.isArray(manifest.items)?manifest.items:[];if(!list.length)throw new Error('manifest empty');
      gridPageSize=Number(manifest.review?.gridPageSize)||12;const votes=loadVotes();
      items=list.map(x=>({...x,vote:votes[key(x)]||null,thumb:null}));
      loadingPanel.classList.add('hidden');gridPanel.classList.remove('hidden');
      const c=manifest.counts||{};$('scopeSummary').textContent=`${items.length} images · ${c.closureShown||0} fermeture Formation · ${c.externalShown||0} hors fermeture via index courant`;
      buildThumbs();renderGrid();
      if(items.every(x=>x.vote))showResults();
    }catch(e){$('loadingText').textContent=`Lot V2 indisponible : ${e.message}`;loadingPanel.classList.add('hidden');emptyPanel.classList.remove('hidden');}
  }

  function filteredIndexes(){const f=gridFilter.value;return items.map((x,i)=>({x,i})).filter(({x})=>f==='all'||(f==='unreviewed'?!x.vote:x.vote===f)).map(v=>v.i);}
  function voteGlyph(v){return v==='yes'?'✓ Oui':v==='no'?'✕ Non':v==='unsure'?'? Incertain':'À examiner';}
  function renderGrid(){
    const ids=filteredIndexes(),pages=Math.max(1,Math.ceil(ids.length/gridPageSize));gridPage=Math.max(0,Math.min(gridPage,pages-1));
    const slice=ids.slice(gridPage*gridPageSize,(gridPage+1)*gridPageSize);gridPageInfo.textContent=`Page ${gridPage+1}/${pages} · ${ids.length} image${ids.length>1?'s':''}`;
    $('gridPrev').disabled=gridPage<=0;$('gridNext').disabled=gridPage>=pages-1;
    const frag=document.createDocumentFragment();
    for(const i of slice){const x=items[i],card=document.createElement('article');card.className=`review-tile ${x.vote?`vote-${x.vote}`:''}`;
      const open=document.createElement('button');open.className='tile-image';open.type='button';open.title='Ouvrir en détail';const img=document.createElement('img');img.src=x.src;img.alt=x.name||`Texture ${i+1}`;img.loading='lazy';open.append(img);open.addEventListener('click',()=>openDetail(i));
      const meta=document.createElement('div');meta.className='tile-meta';const strong=document.createElement('strong');strong.textContent=x.name||x.file||'Sans nom';const small=document.createElement('span');small.textContent=`${x.width}×${x.height} · ${x.scope==='formation-closure'?'fermeture':'hors fermeture'} · sprites ${x.spriteRefs||0}`;meta.append(strong,small);
      const votes=document.createElement('div');votes.className='tile-votes';for(const [v,label] of [['no','✕'],['unsure','?'],['yes','✓']]){const b=document.createElement('button');b.type='button';b.className=`tile-vote ${v} ${x.vote===v?'active':''}`;b.textContent=label;b.title=voteGlyph(v);b.addEventListener('click',()=>{setVote(i,v,false);});votes.append(b);}card.append(open,meta,votes);frag.append(card);
    }reviewGrid.replaceChildren(frag);updateProgress();
  }

  function buildThumbs(){const frag=document.createDocumentFragment();items.forEach((x,i)=>{const b=document.createElement('button');b.className='thumb';b.type='button';b.title=x.name||x.file||`Texture ${i+1}`;const img=document.createElement('img');img.src=x.src;img.alt='';img.loading='lazy';b.append(img);b.addEventListener('click',()=>openDetail(i));x.thumb=b;frag.append(b);});thumbStrip.replaceChildren(frag);}

  function openDetail(i){index=((i%items.length)+items.length)%items.length;gridPanel.classList.add('hidden');resultsPanel.classList.add('hidden');viewerPanel.classList.remove('hidden');renderDetail();}
  function renderDetail(){
    const x=items[index];mainImage.src=x.src;mainImage.alt=x.name||`Texture ${index+1}`;counter.textContent=`${index+1} / ${items.length}`;fileName.textContent=x.name||x.file||'Sans nom';dimensions.textContent=`${x.width} × ${x.height} px`;identity.textContent=`bundle ${x.bundleId} · pathID ${x.pathID}`;scopeMeta.textContent=x.scope==='formation-closure'?`Fermeture Formation · Sprite refs ${x.spriteRefs||0} · Atlas refs ${x.spriteAtlasRefs||0}`:`Hors fermeture · index graphique courant · Sprite refs ${x.spriteRefs||0}`;format.textContent=x.textureFormat||'—';analyticMeta.textContent=`Ordre ${x.orderScore??'—'} · similarité réf. ${x.referenceSimilarity??'—'} (tri seulement)`;
    yesButton.classList.toggle('active',x.vote==='yes');noButton.classList.toggle('active',x.vote==='no');unsureButton.classList.toggle('active',x.vote==='unsure');
    items.forEach((e,i)=>{if(!e.thumb)return;e.thumb.classList.toggle('active',i===index);e.thumb.classList.toggle('vote-yes',e.vote==='yes');e.thumb.classList.toggle('vote-no',e.vote==='no');e.thumb.classList.toggle('vote-unsure',e.vote==='unsure');});if(x.thumb)x.thumb.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'});imageViewport.scrollTo({left:0,top:0});updateProgress();applyMode();
  }
  function updateProgress(){const r=reviewedCount();voteCounter.textContent=`${r} examinée${r>1?'s':''} / ${items.length}`;}
  function nextUnvoted(after){for(let s=1;s<=items.length;s++){const i=(after+s)%items.length;if(!items[i].vote)return i;}return -1;}
  function setVote(i,value,advance){items[i].vote=value;saveVotes();updateProgress();renderGrid();if(i===index&&!viewerPanel.classList.contains('hidden')){if(advance){const n=nextUnvoted(i);if(n<0)showResults();else openDetail(n);}else renderDetail();}}

  function applyMode(){stage.className=`stage mode-${viewMode}`;document.querySelectorAll('.mode-button').forEach(b=>b.classList.toggle('active',b.dataset.mode===viewMode));blurControl.classList.toggle('hidden',viewMode!=='blur');mainImage.style.filter=viewMode==='blur'?`blur(${Number(blurRange.value)||0}px)`:'none';blurValue.textContent=`${blurRange.value} px`;imageViewport.scrollTo({left:0,top:0});}
  function setMode(mode){viewMode=mode;applyMode();}

  function cardFor(x){const card=document.createElement('article');card.className='yes-card';const img=document.createElement('img');img.src=x.src;img.alt=x.name||'Texture';const d=document.createElement('div');const st=document.createElement('strong');st.textContent=x.name||x.file||'Sans nom';const sp=document.createElement('span');sp.textContent=`${x.width}×${x.height} · b${x.bundleId} · p${x.pathID} · ${x.scope==='formation-closure'?'fermeture':'hors fermeture'}`;d.append(st,sp);card.append(img,d);return card;}
  function selectionLine(x){return `${x.name||x.file} — ${x.width}x${x.height} — scope=${x.scope} bundle=${x.bundleId} pathID=${x.pathID} format=${x.textureFormat||'-'} decision=${x.vote}`;}
  async function copySelection(list,buttonId,label){
    if(!list.length)return;
    const text=list.map(selectionLine).join('\n');
    const b=$(buttonId),old=b.textContent;
    try{await navigator.clipboard.writeText(text);b.textContent='Copié ✓';setTimeout(()=>b.textContent=old,1200);}
    catch{window.prompt(label,text);}
  }
  function showResults(){
    saveVotes();const yes=items.filter(x=>x.vote==='yes'),unsure=items.filter(x=>x.vote==='unsure');
    gridPanel.classList.add('hidden');viewerPanel.classList.add('hidden');resultsPanel.classList.remove('hidden');
    resultsSummary.textContent=`${yes.length} Oui sur ${items.length}. ${unsure.length} Incertaine${unsure.length>1?'s':''} conservée${unsure.length>1?'s':''}.`;
    const yf=document.createDocumentFragment();yes.forEach(x=>yf.append(cardFor(x)));yesGrid.replaceChildren(yf);
    const uf=document.createDocumentFragment();unsure.forEach(x=>uf.append(cardFor(x)));unsureGrid.replaceChildren(uf);
    unsureSummary.textContent=`Incertaines conservées (${unsure.length})`;
    $('copyYesButton').disabled=yes.length===0;
    $('copyUnsureButton').disabled=unsure.length===0;
    $('copyKeptButton').disabled=(yes.length+unsure.length)===0;
  }
  function resetVotes(){if(!window.confirm('Effacer tous les Oui / Non / Incertain et recommencer ?'))return;localStorage.removeItem(STORAGE_KEY);items.forEach(x=>x.vote=null);gridPage=0;resultsPanel.classList.add('hidden');viewerPanel.classList.add('hidden');gridPanel.classList.remove('hidden');renderGrid();}

  $('openDetailButton').addEventListener('click',()=>{const i=firstUnvoted();openDetail(i>=0?i:0);});$('backGridButton').addEventListener('click',()=>{viewerPanel.classList.add('hidden');gridPanel.classList.remove('hidden');renderGrid();});
  gridFilter.addEventListener('change',()=>{gridPage=0;renderGrid();});$('gridPrev').addEventListener('click',()=>{gridPage--;renderGrid();});$('gridNext').addEventListener('click',()=>{gridPage++;renderGrid();});
  $('prevButton').addEventListener('click',()=>openDetail(index-1));$('nextButton').addEventListener('click',()=>openDetail(index+1));$('prevBottom').addEventListener('click',()=>openDetail(index-1));$('nextBottom').addEventListener('click',()=>openDetail(index+1));
  yesButton.addEventListener('click',()=>setVote(index,'yes',true));noButton.addEventListener('click',()=>setVote(index,'no',true));unsureButton.addEventListener('click',()=>setVote(index,'unsure',true));
  document.querySelectorAll('.mode-button').forEach(b=>b.addEventListener('click',()=>setMode(b.dataset.mode)));blurRange.addEventListener('input',applyMode);$('resetVotesButton').addEventListener('click',resetVotes);$('resumeButton').addEventListener('click',()=>{resultsPanel.classList.add('hidden');gridPanel.classList.remove('hidden');renderGrid();});
  $('copyYesButton').addEventListener('click',()=>copySelection(items.filter(x=>x.vote==='yes'),'copyYesButton','Copie cette sélection Oui :'));
  $('copyUnsureButton').addEventListener('click',()=>copySelection(items.filter(x=>x.vote==='unsure'),'copyUnsureButton','Copie cette sélection Incertaine :'));
  $('copyKeptButton').addEventListener('click',()=>copySelection(items.filter(x=>x.vote==='yes'||x.vote==='unsure'),'copyKeptButton','Copie les images conservées :'));
  document.addEventListener('keydown',(e)=>{if(viewerPanel.classList.contains('hidden'))return;if(e.key==='ArrowLeft')openDetail(index-1);else if(e.key==='ArrowRight')openDetail(index+1);else if(['o','y'].includes(e.key.toLowerCase()))setVote(index,'yes',true);else if(e.key.toLowerCase()==='n')setVote(index,'no',true);else if(['i','?'].includes(e.key.toLowerCase()))setVote(index,'unsure',true);});
  imageViewport.addEventListener('touchstart',e=>{const t=e.changedTouches[0];touchStartX=t.clientX;touchStartY=t.clientY;},{passive:true});imageViewport.addEventListener('touchend',e=>{if(touchStartX===null)return;const t=e.changedTouches[0],dx=t.clientX-touchStartX,dy=t.clientY-touchStartY;touchStartX=touchStartY=null;if(Math.abs(dx)>=55&&Math.abs(dx)>=Math.abs(dy)*1.3)openDetail(index+(dx<0?1:-1));},{passive:true});
  loadManifest();
})();
