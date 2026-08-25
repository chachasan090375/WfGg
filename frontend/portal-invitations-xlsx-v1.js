(() => {
'use strict';
/* WFGG_PORTAL_INVITATIONS_XLSX_V1
   Local-only XLSX adapter for the Invitations module.
   It reads the workbook in browser memory, converts the first worksheet to
   CSV text, then hands that local text to the existing CSV parser.
   No workbook content or personal code is sent over the network.
*/

const convertedFiles=new WeakSet();
const decoder=new TextDecoder('utf-8');

function u16(view,offset){return view.getUint16(offset,true);}
function u32(view,offset){return view.getUint32(offset,true);}
function findEocd(view){
  const min=Math.max(0,view.byteLength-0xFFFF-22);
  for(let i=view.byteLength-22;i>=min;i--){
    if(u32(view,i)===0x06054b50)return i;
  }
  throw new Error('Classeur Excel illisible (archive ZIP invalide).');
}
async function inflateRaw(bytes){
  if(typeof DecompressionStream!=='function')throw new Error('Ce navigateur ne peut pas lire les fichiers Excel localement.');
  const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
async function zipEntries(file){
  const buffer=await file.arrayBuffer();
  const view=new DataView(buffer);
  const bytes=new Uint8Array(buffer);
  const eocd=findEocd(view);
  const total=u16(view,eocd+10);
  let pos=u32(view,eocd+16);
  const entries=new Map();
  for(let i=0;i<total;i++){
    if(u32(view,pos)!==0x02014b50)throw new Error('Classeur Excel illisible (répertoire ZIP invalide).');
    const method=u16(view,pos+10);
    const compSize=u32(view,pos+20);
    const nameLen=u16(view,pos+28);
    const extraLen=u16(view,pos+30);
    const commentLen=u16(view,pos+32);
    const localOffset=u32(view,pos+42);
    const name=decoder.decode(bytes.slice(pos+46,pos+46+nameLen));
    entries.set(name,{method,compSize,localOffset});
    pos+=46+nameLen+extraLen+commentLen;
  }
  async function read(name){
    const entry=entries.get(name);
    if(!entry)return null;
    const o=entry.localOffset;
    if(u32(view,o)!==0x04034b50)throw new Error('Classeur Excel illisible (entrée ZIP invalide).');
    const nameLen=u16(view,o+26),extraLen=u16(view,o+28);
    const start=o+30+nameLen+extraLen;
    const packed=bytes.slice(start,start+entry.compSize);
    if(entry.method===0)return packed;
    if(entry.method===8)return inflateRaw(packed);
    throw new Error(`Compression Excel non prise en charge (${entry.method}).`);
  }
  return {entries,read};
}
function parseXml(bytes,label){
  if(!bytes)throw new Error(`${label} introuvable dans le classeur Excel.`);
  const doc=new DOMParser().parseFromString(decoder.decode(bytes),'application/xml');
  if(doc.getElementsByTagName('parsererror').length)throw new Error(`${label} XML invalide.`);
  return doc;
}
function normalizeSheetTarget(target){
  let t=String(target||'').replace(/^\//,'');
  if(t.startsWith('xl/'))return t;
  while(t.startsWith('../'))t=t.slice(3);
  return `xl/${t}`;
}
async function firstSheetPath(zip){
  try{
    const workbook=parseXml(await zip.read('xl/workbook.xml'),'workbook.xml');
    const sheet=workbook.getElementsByTagName('sheet')[0];
    const relId=sheet?.getAttribute('r:id')||sheet?.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships','id');
    if(relId){
      const rels=parseXml(await zip.read('xl/_rels/workbook.xml.rels'),'workbook.xml.rels');
      const rel=[...rels.getElementsByTagName('Relationship')].find(x=>x.getAttribute('Id')===relId);
      if(rel?.getAttribute('Target'))return normalizeSheetTarget(rel.getAttribute('Target'));
    }
  }catch{}
  return [...zip.entries.keys()].find(n=>/^xl\/worksheets\/sheet\d+\.xml$/i.test(n))||'xl/worksheets/sheet1.xml';
}
function sharedStrings(doc){
  if(!doc)return [];
  return [...doc.getElementsByTagName('si')].map(si=>[...si.getElementsByTagName('t')].map(t=>t.textContent||'').join(''));
}
function colIndex(ref){
  const m=String(ref||'').match(/^([A-Z]+)/i);if(!m)return 0;
  let n=0;for(const ch of m[1].toUpperCase())n=n*26+(ch.charCodeAt(0)-64);
  return n-1;
}
function cellValue(cell,shared){
  const type=cell.getAttribute('t')||'';
  if(type==='inlineStr')return [...cell.getElementsByTagName('t')].map(t=>t.textContent||'').join('');
  const v=cell.getElementsByTagName('v')[0]?.textContent||'';
  if(type==='s')return shared[Number(v)]??'';
  if(type==='b')return v==='1'?'TRUE':'FALSE';
  return v;
}
function quoteCsv(value){
  const s=String(value??'');
  return /[;"\r\n]/.test(s)?`"${s.replace(/"/g,'""')}"`:s;
}
async function xlsxToCsv(file){
  const zip=await zipEntries(file);
  const sharedBytes=await zip.read('xl/sharedStrings.xml');
  const shared=sharedStrings(sharedBytes?parseXml(sharedBytes,'sharedStrings.xml'):null);
  const sheetPath=await firstSheetPath(zip);
  const sheet=parseXml(await zip.read(sheetPath),'première feuille Excel');
  const rows=[];
  for(const row of [...sheet.getElementsByTagName('row')]){
    const values=[];
    for(const cell of [...row.getElementsByTagName('c')])values[colIndex(cell.getAttribute('r'))]=cellValue(cell,shared);
    rows.push(values.slice(0,3).map(v=>v??''));
  }
  if(!rows.length)throw new Error('Le classeur Excel ne contient aucune donnée.');
  return rows.map(r=>[0,1,2].map(i=>quoteCsv(r[i]??'')).join(';')).join('\n');
}
function isXlsx(file){
  return /\.xlsx$/i.test(file?.name||'')||file?.type==='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
}
function showError(message){
  const box=document.getElementById('inviteError');
  if(box){box.textContent=message;box.classList.remove('hidden');}
}
function updateLabels(){
  const input=document.getElementById('inviteCsvInput');
  if(!input)return;
  input.dataset.xlsxSupport='v1';
  const label=input.closest('.invite-file-button');
  if(label&&label.firstChild?.nodeType===Node.TEXT_NODE){
    const l=(document.documentElement.lang||'fr').toLowerCase();
    const text=l==='it'?'📄 Importa CSV / Excel':l==='en'?'📄 Import CSV / Excel':l==='es'?'📄 Importar CSV / Excel':'📄 Importer CSV / Excel';
    label.firstChild.textContent=text;
  }
}

new MutationObserver(updateLabels).observe(document.documentElement,{childList:true,subtree:true});
updateLabels();

document.addEventListener('change',async event=>{
  const input=event.target;
  if(!(input instanceof HTMLInputElement)||input.id!=='inviteCsvInput')return;
  const file=input.files?.[0];
  if(!file||convertedFiles.has(file)||!isXlsx(file))return;
  event.stopImmediatePropagation();
  try{
    const csv=await xlsxToCsv(file);
    const converted=new File([csv],file.name,{type:'text/csv',lastModified:file.lastModified});
    convertedFiles.add(converted);
    const dt=new DataTransfer();dt.items.add(converted);input.files=dt.files;
    input.dispatchEvent(new Event('change',{bubbles:true}));
  }catch(err){
    try{input.value='';}catch{}
    showError(err?.message||'Classeur Excel invalide.');
  }
},true);

window.WFGG_INVITATIONS_XLSX_TEST={xlsxToCsv};
})();
