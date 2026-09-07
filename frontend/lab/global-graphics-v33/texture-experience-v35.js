(()=>{
'use strict';

/* V35 texture UX layer.
   1) Removes model/PBR texture sheets from ordinary browsing by default without deleting them
      from the catalogue. They remain available through one explicit advanced filter.
   2) Leaves texture sheets available to WFGGModelViewer internally so 3D models can discover and
      apply them through their UV coordinates.
*/

const STORE_KEY='wfgg-hide-model-texture-sheets-v35';
const FILTER_ID='texture_sheet_visibility';
let hideTextureSheets=true;
let filteredLastRender=0;

function loadSetting(){
  try{
    const v=localStorage.getItem(STORE_KEY);
    if(v!==null)hideTextureSheets=v!=='show';
  }catch{}
}
function saveSetting(){try{localStorage.setItem(STORE_KEY,hideTextureSheets?'hide':'show');}catch{}}
loadSetting();

function normPath(a){return String(a?.asset_path||a?.logical_name||a?.alias_name||'').replace(/\\/g,'/').toLowerCase();}
function tailOf(a){return normPath(a).rsplit?normPath(a).rsplit('/',1)[1]:normPath(a).split('/').pop();}
function isTextureSheet(a){
  const p=normPath(a),tail=p.split('/').pop()||'';
  const role=String(a?.model_role||'').toLowerCase(),tech=String(a?.tech_kind||'').toLowerCase();
  const dim=String(a?.dimension_class||'').toLowerCase();
  const inModelTree=/\/models?\//.test(p)||/\/cars?\//.test(p)||/\/characters?\//.test(p)||/\/weapons?\//.test(p);
  const inTextureTree=/\/(texture|textures|pbr|materials?)\//.test(p);
  const textureType=role==='texture'||/texture2d|texture|tga|dds|ktx|astc/.test(tech)||dim==='2d';
  const textureFile=/\.(tga|dds|png|jpg|jpeg|webp|ktx|ktx2|astc)$/i.test(tail);
  const mapSuffix=/(?:^|[_-])(albedo|basecolor|diffuse|color|normal|nrm|spec|specular|smooth|rough|metal|metallic|mask|ao|occlusion|emission|emissive|[sdnmao])(?:[_-]|\.)/i.test(tail);
  // We deliberately require a model + texture/PBR context. UI sprites and normal 2D art are kept.
  return !!(inModelTree&&inTextureTree&&(textureType||textureFile||mapSuffix));
}

function installFilterUI(){
  const body=document.querySelector('#advancedDialog .modal-body');if(!body)return;
  let sel=document.querySelector('#'+FILTER_ID);
  if(sel){sel.value=hideTextureSheets?'hide':'show';return;}
  const label=document.createElement('label');
  label.innerHTML='Planches de texture<select id="'+FILTER_ID+'"><option value="hide">Masquer les planches PBR / UV</option><option value="show">Afficher aussi les planches de texture</option></select>';
  const note=body.querySelector('.modal-note');body.insertBefore(label,note||body.lastChild);
  sel=label.querySelector('select');sel.value=hideTextureSheets?'hide':'show';
  sel.addEventListener('change',()=>{hideTextureSheets=sel.value!=='show';saveSetting();updateFilterSummary?.();});
}

function purgeTextureSheets(){
  if(!hideTextureSheets||typeof items==='undefined'||!Array.isArray(items)){filteredLastRender=0;return 0;}
  const before=items.length;
  if(!before){filteredLastRender=0;return 0;}
  items=items.filter(a=>!isTextureSheet(a));
  filteredLastRender=before-items.length;
  if(typeof idx==='number'&&idx>=items.length)idx=items.length-1;
  return filteredLastRender;
}

installFilterUI();

if(typeof renderList==='function'){
  const baseRenderListTexture=renderList;
  renderList=function(){installFilterUI();purgeTextureSheets();return baseRenderListTexture();};
}

if(typeof activeFilters==='function'){
  const baseActiveFiltersTexture=activeFilters;
  activeFilters=function(){
    const out=baseActiveFiltersTexture();
    if(!hideTextureSheets)out.unshift({id:FILTER_ID,label:'Planches de texture affichées'});
    return out;
  };
}

if(typeof updateFilterSummary==='function'){
  const baseUpdateFilterSummaryTexture=updateFilterSummary;
  updateFilterSummary=function(){
    baseUpdateFilterSummaryTexture();
    const h=document.querySelector('#filterSummary');if(!h)return;
    if(hideTextureSheets&&!h.querySelector('[data-texture-filter-chip]')){
      const chip=document.createElement('span');chip.className='filterchip';chip.dataset.textureFilterChip='1';chip.textContent='Planches PBR / UV masquées';h.appendChild(chip);
    }
  };
}

if(typeof resetFilters==='function'){
  const baseResetTexture=resetFilters;
  resetFilters=function(run=true){
    baseResetTexture(false);hideTextureSheets=true;saveSetting();installFilterUI();
    const sel=document.querySelector('#'+FILTER_ID);if(sel)sel.value='hide';
    updateFilterSummary?.();if(run)runSearch();
  };
}

// If the module loads after the first list has already been rendered, apply the default immediately.
try{
  if(typeof items!=='undefined'&&Array.isArray(items)&&items.length){purgeTextureSheets();renderList();}
  updateFilterSummary?.();
}catch(e){console.debug('V35_TEXTURE_FILTER_INITIAL_APPLY_FAIL',e);}

window.WFGGTextureExperienceV35={
  version:'35.2',
  isTextureSheet,
  state:()=>({hideTextureSheets,filteredLastRender}),
  setVisible:(visible)=>{hideTextureSheets=!visible;saveSetting();installFilterUI();const s=document.querySelector('#'+FILTER_ID);if(s)s.value=visible?'show':'hide';runSearch?.();}
};
console.info('V35_TEXTURE_EXPERIENCE installed texture-sheet-filter=ON default=HIDE model-textures-remain-internal=ON');
})();
