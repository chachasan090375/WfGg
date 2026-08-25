(() => {
'use strict';
/* WFGG_LASTWAR_CHAT_SAFE_V1
   Last War does not publish a numeric chat limit. Invitation messages are therefore
   exposed as short <=240-character blocks, without Unicode emoji, while keeping
   the original local-only privacy model. The portal domain is shown without scheme
   so a link-filter failure is isolated to the final access block.
*/
const MAX_CHARS=240;
const THANKED=['Metatouk','Ogie Ogilthorpe 7','ValFada','Shockwave XY','Sab93fr','εlο ツ','cat 49','Flawene'];
const states=new WeakMap();
const canonicalPseudo=p=>{
  const s=String(p||'').trim();
  return (s==='εlα ツ'||s==='εlo ツ')?'εlο ツ':s;
};
function stableVariant(value){
  let h=2166136261;
  for(const ch of String(value||'')){h^=ch.codePointAt(0);h=Math.imul(h,16777619)}
  return h>>>0;
}
function splitSafe(text,max=MAX_CHARS){
  const src=String(text||'').trim();
  if(!src)return [];
  if(src.length<=max)return [src];
  const words=src.split(/\s+/);const out=[];let line='';
  for(const word of words){
    if(word.length>max){
      if(line){out.push(line);line='';}
      for(let i=0;i<word.length;i+=max)out.push(word.slice(i,i+max));
      continue;
    }
    const next=line?`${line} ${word}`:word;
    if(next.length>max){out.push(line);line=word}else line=next;
  }
  if(line)out.push(line);
  return out;
}
function buildBlocks(pseudo,rank,code){
  pseudo=canonicalPseudo(pseudo);rank=String(rank||'').toUpperCase();code=String(code||'').trim();
  const variants=[
    `Salut ${pseudo}. Le nouveau portail WfGg est ouvert après plusieurs mois de travail du bureau R4/R5. Tu y trouveras le Train, les rotations Conducteur/VIP, la Bourse d'échanges et les Guides Saison 6 / Inter-Saison.`,
    `Hello ${pseudo}. Le portail WfGg est maintenant disponible après plusieurs mois de travail du bureau R4/R5. Tu y trouveras le Train, les rotations Conducteur/VIP, la Bourse d'échanges et les Guides Saison 6 / Inter-Saison.`,
    `Salut ${pseudo}. Ton accès au nouveau portail WfGg est prêt. Le bureau R4/R5 travaille dessus depuis plusieurs mois. Tu y trouveras le Train, les rotations Conducteur/VIP, la Bourse d'échanges et les Guides Saison 6 / Inter-Saison.`
  ];
  const source=[variants[stableVariant(pseudo)%variants.length],
    `Merci à ${THANKED.join(', ').replace(', Flawene',' et Flawene')} pour leur travail sur le projet et leur investissement durant toute l'Inter-Saison. Le simulateur d'équipes et d'autres outils arriveront ensuite.`
  ];
  if(rank==='R4')source.push(`Ton rang R4 donne aussi accès aux outils du bureau : paramètres alliance, Joueurs & accès, statistiques, réglages, Droits & accès, gestion des profils/rangs, activation des comptes et réinitialisation des codes.`);
  if(rank==='R5')source.push(`Ton rang R5 donne aussi accès aux outils du bureau : paramètres alliance, Joueurs & accès, statistiques, réglages, Droits & accès, gestion des profils/rangs et réinitialisation des codes. Tu conserves les fonctions de leadership R5.`);
  source.push(`Adresse du portail : wfgg.pages.dev\nCode personnel : ${code}`);
  return source.flatMap(x=>splitSafe(x));
}
function parseCurrent(ta){
  const card=ta.closest('.invite-workspace');
  const pseudo=canonicalPseudo(card?.querySelector('.invite-player h3')?.textContent||'');
  const rank=String(card?.querySelector('.rank-badge')?.textContent||'').trim().toUpperCase();
  const full=String(ta.value||'');
  const code=(full.match(/(?:Ton\s+)?code personnel\s*:\s*(\d{6})/i)||[])[1]||'';
  return pseudo&&/^R[1-5]$/.test(rank)&&/^\d{6}$/.test(code)?{pseudo,rank,code}:null;
}
function update(ta){
  const st=states.get(ta);if(!st)return;
  st.index=Math.max(0,Math.min(st.index,st.blocks.length-1));
  const text=st.blocks[st.index];ta.value=text;
  const host=ta.closest('.invite-workspace');
  const meta=host?.querySelector('[data-lastwar-safe-meta]');
  if(meta)meta.textContent=`Bloc ${st.index+1}/${st.blocks.length} · ${text.length}/${MAX_CHARS} caractères · sans emoji`;
  const prev=host?.querySelector('[data-lastwar-safe-prev]');
  const next=host?.querySelector('[data-lastwar-safe-next]');
  if(prev)prev.disabled=st.index===0;
  if(next)next.disabled=st.index===st.blocks.length-1;
  const copy=host?.querySelector('#inviteCopy');if(copy)copy.textContent='Copier ce bloc';
  const copySent=host?.querySelector('#inviteCopySent');
  if(copySent){copySent.textContent='Copier dernier + marquer envoyé';copySent.disabled=st.index!==st.blocks.length-1;}
}
function enhance(ta){
  if(!ta||ta.dataset.lastwarSafe==='v1')return;
  const row=parseCurrent(ta);if(!row)return;
  const blocks=buildBlocks(row.pseudo,row.rank,row.code);
  if(!blocks.length||blocks.some(x=>x.length>MAX_CHARS))return;
  ta.dataset.lastwarSafe='v1';ta.spellcheck=false;
  states.set(ta,{blocks,index:0,row});
  const actions=ta.closest('.invite-workspace')?.querySelector('.invite-primary-actions');
  if(actions&&!actions.parentElement.querySelector('[data-lastwar-safe-controls]')){
    const controls=document.createElement('div');
    controls.dataset.lastwarSafeControls='v1';
    controls.className='invite-secondary-actions';
    controls.innerHTML='<button type="button" class="secondary-button" data-lastwar-safe-prev>Bloc précédent</button><span class="muted" data-lastwar-safe-meta></span><button type="button" class="secondary-button" data-lastwar-safe-next>Bloc suivant</button>';
    actions.before(controls);
    controls.querySelector('[data-lastwar-safe-prev]')?.addEventListener('click',()=>{const s=states.get(ta);if(s&&s.index>0){s.index--;update(ta)}});
    controls.querySelector('[data-lastwar-safe-next]')?.addEventListener('click',()=>{const s=states.get(ta);if(s&&s.index<s.blocks.length-1){s.index++;update(ta)}});
  }
  update(ta);
}
function scan(){document.querySelectorAll('#inviteMessage').forEach(enhance)}
new MutationObserver(()=>queueMicrotask(scan)).observe(document.documentElement,{childList:true,subtree:true});
scan();
window.WFGG_LASTWAR_CHAT_SAFE_TEST={MAX_CHARS,buildBlocks,canonicalPseudo};
})();
