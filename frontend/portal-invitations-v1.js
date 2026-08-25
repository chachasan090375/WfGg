(() => {
'use strict';
/* WFGG_PORTAL_INVITATIONS_V1
   Privacy contract: CSV contents and personal codes stay in browser memory.
   This module performs no fetch/XHR and never stores codes in localStorage.
*/

const SENT_KEY='wfgg_invites_sent_v1';
const PORTAL_URL='https://wfgg.pages.dev/';
const THANKED_OFFICERS=['Metatouk','Ogie Ogilthorpe 7','ValFada','Shockwave XY','Sab93fr','εlα ツ','cat 49','Flawene'];
const EXCLUDED_FROM_THANKS=['El Tonton','Le Ced83','SnooPsy'];
let records=[];
let activeIndex=0;
let sourceName='';
let active=false;

const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const lang=()=>['fr','it','en','es'].includes(document.documentElement.lang)?document.documentElement.lang:'fr';
const UI={
  fr:{tab:'Invitations',title:'Invitations joueurs',desc:'Importe le CSV des codes puis parcours les messages un par un. Les codes restent uniquement dans ce navigateur.',privacy:'🔒 Traitement local : le CSV et les codes personnels ne sont ni envoyés au serveur, ni enregistrés dans GitHub, ni stockés dans le navigateur.',choose:'Importer le CSV',empty:'Aucun fichier chargé.',loaded:n=>`${n} joueurs chargés`,sent:'envoyés',message:'Message',copy:'📋 Copier le message',copySent:'📋 Copier + marquer envoyé',mark:'✓ Marquer envoyé',unmark:'↩ Annuler envoyé',prev:'← Précédent',next:'Suivant →',nextPending:'Prochain non envoyé',reset:'Réinitialiser le suivi',replace:'Changer de CSV',bad:'CSV invalide. Colonnes attendues : Pseudo ; Rang ; Code personnel.',invalidRows:'Certaines lignes sont invalides ou ont un code différent de 6 chiffres.',rank:'Rang',position:(i,n)=>`${i} / ${n}`,copied:'✅ Copié',done:'✓ Envoyé'},
  it:{tab:'Inviti',title:'Inviti giocatori',desc:'Importa il CSV dei codici e scorri i messaggi uno alla volta. I codici restano solo in questo browser.',privacy:'🔒 Elaborazione locale: CSV e codici personali non vengono inviati al server, salvati su GitHub o memorizzati nel browser.',choose:'Importa CSV',empty:'Nessun file caricato.',loaded:n=>`${n} giocatori caricati`,sent:'inviati',message:'Messaggio',copy:'📋 Copia messaggio',copySent:'📋 Copia + segna inviato',mark:'✓ Segna inviato',unmark:'↩ Annulla inviato',prev:'← Precedente',next:'Successivo →',nextPending:'Prossimo non inviato',reset:'Azzera avanzamento',replace:'Cambia CSV',bad:'CSV non valido. Colonne richieste: Pseudo ; Rang ; Code personnel.',invalidRows:'Alcune righe non sono valide o il codice non contiene 6 cifre.',rank:'Grado',position:(i,n)=>`${i} / ${n}`,copied:'✅ Copiato',done:'✓ Inviato'},
  en:{tab:'Invitations',title:'Player invitations',desc:'Import the code CSV and browse the messages one by one. Codes stay only in this browser.',privacy:'🔒 Local processing: the CSV and personal codes are not sent to the server, saved to GitHub or persisted in the browser.',choose:'Import CSV',empty:'No file loaded.',loaded:n=>`${n} players loaded`,sent:'sent',message:'Message',copy:'📋 Copy message',copySent:'📋 Copy + mark sent',mark:'✓ Mark sent',unmark:'↩ Mark unsent',prev:'← Previous',next:'Next →',nextPending:'Next unsent',reset:'Reset tracking',replace:'Change CSV',bad:'Invalid CSV. Expected columns: Pseudo ; Rang ; Code personnel.',invalidRows:'Some rows are invalid or the personal code is not 6 digits.',rank:'Rank',position:(i,n)=>`${i} / ${n}`,copied:'✅ Copied',done:'✓ Sent'},
  es:{tab:'Invitaciones',title:'Invitaciones jugadores',desc:'Importa el CSV de códigos y recorre los mensajes uno a uno. Los códigos permanecen solo en este navegador.',privacy:'🔒 Procesamiento local: el CSV y los códigos personales no se envían al servidor, no se guardan en GitHub ni se almacenan en el navegador.',choose:'Importar CSV',empty:'Ningún archivo cargado.',loaded:n=>`${n} jugadores cargados`,sent:'enviados',message:'Mensaje',copy:'📋 Copiar mensaje',copySent:'📋 Copiar + marcar enviado',mark:'✓ Marcar enviado',unmark:'↩ Marcar no enviado',prev:'← Anterior',next:'Siguiente →',nextPending:'Siguiente no enviado',reset:'Reiniciar seguimiento',replace:'Cambiar CSV',bad:'CSV inválido. Columnas esperadas: Pseudo ; Rang ; Code personnel.',invalidRows:'Algunas filas no son válidas o el código personal no tiene 6 cifras.',rank:'Rango',position:(i,n)=>`${i} / ${n}`,copied:'✅ Copiado',done:'✓ Enviado'}
};
const tx=()=>UI[lang()]||UI.fr;

function stableKey(row){
  const s=`${row.pseudo}|${row.rank}`;
  let h=2166136261;
  for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}
  return `p${(h>>>0).toString(16)}`;
}
function sentSet(){
  try{const v=JSON.parse(localStorage.getItem(SENT_KEY)||'[]');return new Set(Array.isArray(v)?v:[])}catch{return new Set()}
}
function saveSent(set){localStorage.setItem(SENT_KEY,JSON.stringify([...set]));}
function isSent(row){return sentSet().has(stableKey(row));}
function setSent(row,value){const set=sentSet(),k=stableKey(row);value?set.add(k):set.delete(k);saveSent(set);}

function normalizeHeader(v){return String(v||'').replace(/^\uFEFF/,'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toLowerCase();}
function parseCsvLine(line,delimiter){
  const out=[];let cur='',quoted=false;
  for(let i=0;i<line.length;i++){
    const ch=line[i];
    if(ch==='"'){
      if(quoted&&line[i+1]==='"'){cur+='"';i++;}
      else quoted=!quoted;
    }else if(ch===delimiter&&!quoted){out.push(cur);cur='';}
    else cur+=ch;
  }
  out.push(cur);return out;
}
function parseCsv(text){
  const lines=String(text||'').replace(/\r\n?/g,'\n').split('\n').filter(x=>x.trim().length);
  if(lines.length<2)throw new Error(tx().bad);
  const delimiter=(lines[0].match(/;/g)||[]).length>=(lines[0].match(/,/g)||[]).length?';':',';
  const headers=parseCsvLine(lines[0],delimiter).map(normalizeHeader);
  const find=(...names)=>headers.findIndex(h=>names.includes(h));
  const pIdx=find('pseudo','joueur','player','player name');
  const rIdx=find('rang','rank');
  const cIdx=find('code personnel','code','personal code','code personnel wfgg');
  if(Math.min(pIdx,rIdx,cIdx)<0)throw new Error(tx().bad);
  const rows=[];
  for(let i=1;i<lines.length;i++){
    const cols=parseCsvLine(lines[i],delimiter);
    const pseudo=String(cols[pIdx]||'').trim();
    const rank=String(cols[rIdx]||'').trim().toUpperCase();
    const code=String(cols[cIdx]||'').trim();
    if(!pseudo&&!rank&&!code)continue;
    if(!pseudo||!/^R[1-5]$/.test(rank)||!/^\d{6}$/.test(code))throw new Error(`${tx().invalidRows} (ligne ${i+1})`);
    rows.push({pseudo,rank,code,variant:rows.length});
  }
  if(!rows.length)throw new Error(tx().bad);
  return rows;
}

const openings=[
  p=>`Salut ${p} 👋`,
  p=>`Hello ${p} !`,
  p=>`Salut ${p}, petite nouveauté importante côté WfGg 👋`,
  p=>`Hello ${p}, on a quelque chose de nouveau à te présenter !`,
  p=>`Salut ${p} ! Le portail WfGg est enfin prêt 🚀`,
  p=>`Hello ${p} 👋 Après plusieurs mois de travail, on peut enfin ouvrir le portail WfGg.`,
  p=>`Salut ${p}, bienvenue dans la nouvelle étape de WfGg !`,
  p=>`Hello ${p} ! Voici ton accès personnel au nouveau portail WfGg.`
];
const projectBlocks=[
  `Depuis plusieurs mois, le bureau R4/R5 travaille sur un projet commun : réunir dans un même portail les outils qui nous servent au quotidien et rendre l'organisation de l'alliance plus simple.`,
  `Le bureau R4/R5 travaille depuis des mois à la construction d'un espace unique pour centraliser nos outils, nos infos et les services utiles à l'alliance.`,
  `Ce portail est le résultat de plusieurs mois de travail collectif du bureau R4/R5, avec l'idée de simplifier l'accès à nos outils et d'éviter de disperser les informations.`,
  `On prépare ce projet depuis des mois avec l'ensemble du bureau R4/R5 : un point d'entrée unique, plus clair, pour les outils WfGg actuels et ceux qui arrivent.`,
  `Après plusieurs mois de préparation par le bureau R4/R5, WfGg dispose maintenant de son propre portail pour rassembler progressivement les outils de l'alliance.`,
  `L'ensemble du bureau R4/R5 travaille depuis plusieurs mois sur cette nouvelle plateforme afin de rendre l'organisation plus fluide et les informations plus faciles à retrouver.`,
  `Ce nouveau portail est un travail de longue haleine mené depuis plusieurs mois par le bureau R4/R5 pour donner à l'alliance un espace commun, pratique et évolutif.`,
  `Le projet a mûri pendant plusieurs mois au sein du bureau R4/R5 : l'objectif est de construire une vraie boîte à outils WfGg accessible depuis une seule adresse.`
];
const trainBlocks=[
  `Le module Train permet de consulter les rotations, les prochains passages Conducteur/VIP et la Bourse pour organiser les échanges lorsqu'un créneau pose problème.`,
  `Tu y trouveras notamment le Train : planning des rotations, passages Conducteur et VIP, ainsi que la Bourse pour proposer ou accepter un échange de créneau.`,
  `Le Train est déjà intégré : il centralise le planning, les rotations Conducteur/VIP et les échanges de créneaux via la Bourse.`,
  `Côté organisation, le module Train donne une vue claire du planning et de tes rotations, avec la possibilité d'utiliser la Bourse en cas de besoin d'échange.`,
  `Le premier gros outil est le Train, qui reprend le planning de rotation, les rôles Conducteur/VIP et le système d'échange de dates.`,
  `Dans le Train, tu peux retrouver les dates programmées, suivre les rotations et passer par la Bourse si tu dois échanger un créneau.`,
  `Le module Train sert de référence pour l'organisation des rotations et permet aussi de gérer les demandes d'échange entre joueurs.`
];
const guideBlocks=[
  `Les Guides sont également accessibles depuis le portail, avec les contenus Saison 6 et Inter-Saison regroupés au même endroit.`,
  `Le portail donne aussi accès aux Guides WfGg, notamment Saison 6 et Inter-Saison, pour retrouver rapidement les fiches et explications.`,
  `Tu peux également ouvrir directement les Guides, où nous centralisons les contenus utiles de Saison 6 et d'Inter-Saison.`,
  `Les Guides font partie du portail : ils rassemblent les fiches, conseils et contenus Saison 6 / Inter-Saison.`,
  `Un accès direct aux Guides est prévu dès l'accueil pour retrouver les fiches et contenus de Saison 6 et d'Inter-Saison.`,
  `Les contenus de guide sont eux aussi centralisés : Saison 6, Inter-Saison et les fiches utiles sont accessibles depuis le même portail.`,
  `Depuis la page d'accueil tu peux passer directement aux Guides WfGg et retrouver les contenus Saison 6 et Inter-Saison.`
];
const futureBlocks=[
  `Et ce n'est qu'un début : le simulateur d'équipes, un générateur de notifications et un générateur de messages/mails font partie des prochains modules prévus.`,
  `D'autres outils arrivent ensuite, notamment le simulateur d'équipes et des générateurs pour préparer plus rapidement notifications, messages et mails.`,
  `La suite est déjà prévue : simulateur d'équipes, création assistée de notifications et génération de messages/mails pour gagner du temps au quotidien.`,
  `Le portail va continuer d'évoluer avec, entre autres, un simulateur d'équipes et des outils de génération de notifications et de messages.`,
  `Parmi les prochains chantiers : simulateur d'équipes, générateur de notifications et outils de préparation de messages/mails.`,
  `Nous allons progressivement ajouter de nouveaux modules, dont le simulateur d'équipes et des générateurs de notifications et de communications.`
];
const thankBlocks=[
  `Un grand merci à ${THANKED_OFFICERS.join(', ')} pour leur travail et leur implication dans la mise en place du projet.`,
  `Merci tout particulièrement à ${THANKED_OFFICERS.join(', ')}, qui ont participé au travail du bureau autour de ce projet.`,
  `Ce lancement doit aussi beaucoup au travail de ${THANKED_OFFICERS.join(', ')} : merci à eux pour le temps et l'énergie consacrés au projet.`,
  `Je tiens à remercier ${THANKED_OFFICERS.join(', ')} pour leur contribution au travail mené par le bureau sur cette plateforme.`
];
const closings=[
  `Tu peux te connecter dès maintenant. Bonne découverte !`,
  `Tout est prêt : tu peux tester ton accès dès maintenant. À très vite sur le portail !`,
  `N'hésite pas à aller faire un tour et à nous signaler ce qui pourrait encore être amélioré.`,
  `Ton accès est actif dès maintenant. Bonne visite et bienvenue sur le portail WfGg !`,
  `Tu peux commencer à l'utiliser tout de suite. On continuera à l'améliorer au fil des retours.`,
  `Voilà pour l'essentiel : ton accès est prêt, il ne reste plus qu'à découvrir le portail.`
];
function adminParagraph(rank){
  if(!['R4','R5'].includes(rank))return '';
  const leader=rank==='R5'?' En tant que R5, tu disposes également de l’accès de leadership correspondant à ton rôle.':'';
  return `\n\nTon statut de ${rank} te donne aussi accès aux fonctions d'administration réservées au bureau : paramètres de l'alliance, Joueurs & accès, statistiques joueurs, réglages de l'application, Droits & accès, gestion des profils et des rangs, fonctions R4, activation/désactivation des comptes, réinitialisation des codes personnels et gestion du changement de R5.${leader}`;
}
function messageFor(row){
  const i=row.variant;
  const parts=[
    openings[i%openings.length](row.pseudo),
    '',
    projectBlocks[(i*3)%projectBlocks.length],
    '',
    trainBlocks[(i*5+1)%trainBlocks.length],
    guideBlocks[(i*4+2)%guideBlocks.length],
    futureBlocks[(i*5+3)%futureBlocks.length],
    '',
    thankBlocks[i%thankBlocks.length],
    adminParagraph(row.rank),
    '',
    `🌐 Adresse : ${PORTAL_URL}`,
    `🔐 Ton code personnel : ${row.code}`,
    '',
    closings[(i*5+2)%closings.length]
  ];
  return parts.filter((v,idx,a)=>!(v===''&&a[idx-1]==='')).join('\n').replace(/\n{3,}/g,'\n\n');
}

function moduleHtml(){
  const x=tx();
  return `<div class="settings-section invite-module"><div class="settings-card-block"><div class="section-heading"><div><h3>✉️ ${esc(x.title)}</h3><p class="muted">${esc(x.desc)}</p></div></div><div class="invite-privacy">${esc(x.privacy)}</div><div class="invite-import-row"><label class="secondary-button invite-file-button">📄 ${esc(records.length?x.replace:x.choose)}<input id="inviteCsvInput" class="hidden" type="file" accept=".csv,text/csv,text/plain"></label><span id="inviteFileMeta" class="muted invite-file-meta">${esc(records.length?`${sourceName} · ${x.loaded(records.length)}`:x.empty)}</span></div><div id="inviteError" class="form-message error hidden"></div></div><div id="inviteWorkspace"></div></div>`;
}
function renderWorkspace(){
  const host=$('inviteWorkspace');if(!host)return;
  if(!records.length){host.innerHTML='';return;}
  const x=tx(),row=records[activeIndex],sent=sentSet(),done=records.filter(r=>sent.has(stableKey(r))).length,flag=sent.has(stableKey(row));
  host.innerHTML=`<div class="settings-card-block invite-workspace"><div class="invite-progress"><strong>${esc(x.position(activeIndex+1,records.length))}</strong><span>${done} / ${records.length} ${esc(x.sent)}</span></div><div class="invite-player"><div><small>${esc(x.rank)} ${esc(row.rank)}</small><h3>${esc(row.pseudo)}</h3></div><span class="rank-badge">${esc(row.rank)}</span></div><label class="field-label" for="inviteMessage">${esc(x.message)}</label><textarea id="inviteMessage" class="invite-message" spellcheck="true"></textarea><div class="invite-primary-actions"><button id="inviteCopy" class="primary-button" type="button">${esc(x.copy)}</button><button id="inviteCopySent" class="secondary-button ${flag?'invite-sent':''}" type="button">${esc(x.copySent)}</button></div><div class="invite-secondary-actions"><button id="inviteToggleSent" class="secondary-button ${flag?'invite-sent':''}" type="button">${esc(flag?x.unmark:x.mark)}</button><button id="inviteNextPending" class="secondary-button" type="button">${esc(x.nextPending)}</button></div><div class="invite-nav"><button id="invitePrev" class="secondary-button" type="button" ${activeIndex===0?'disabled':''}>${esc(x.prev)}</button><button id="inviteNext" class="secondary-button" type="button" ${activeIndex===records.length-1?'disabled':''}>${esc(x.next)}</button></div><button id="inviteReset" class="small-btn" type="button">${esc(x.reset)}</button></div>`;
  $('inviteMessage').value=messageFor(row);
  bindWorkspace();
}
async function copyCurrent(mark=false){
  const ta=$('inviteMessage');if(!ta)return;
  const text=ta.value;
  try{await navigator.clipboard.writeText(text)}catch{ta.focus();ta.select();document.execCommand('copy');ta.setSelectionRange(0,0);}
  if(mark){setSent(records[activeIndex],true);renderWorkspace();}
  else{const b=$('inviteCopy');if(b){const old=b.textContent;b.textContent=tx().copied;setTimeout(()=>{if(document.body.contains(b))b.textContent=old},900);}}
}
function nextPending(){
  if(!records.length)return;
  const sent=sentSet();
  for(let step=1;step<=records.length;step++){
    const idx=(activeIndex+step)%records.length;
    if(!sent.has(stableKey(records[idx]))){activeIndex=idx;renderWorkspace();return;}
  }
}
function bindWorkspace(){
  $('inviteCopy')?.addEventListener('click',()=>copyCurrent(false));
  $('inviteCopySent')?.addEventListener('click',()=>copyCurrent(true));
  $('inviteToggleSent')?.addEventListener('click',()=>{const r=records[activeIndex];setSent(r,!isSent(r));renderWorkspace();});
  $('inviteNextPending')?.addEventListener('click',nextPending);
  $('invitePrev')?.addEventListener('click',()=>{if(activeIndex>0){activeIndex--;renderWorkspace();}});
  $('inviteNext')?.addEventListener('click',()=>{if(activeIndex<records.length-1){activeIndex++;renderWorkspace();}});
  $('inviteReset')?.addEventListener('click',()=>{localStorage.removeItem(SENT_KEY);renderWorkspace();});
}
function showError(msg){const e=$('inviteError');if(!e)return;e.textContent=msg;e.classList.remove('hidden');}
function bindImport(){
  $('inviteCsvInput')?.addEventListener('change',async e=>{
    const file=e.target.files?.[0];if(!file)return;
    try{
      const parsed=parseCsv(await file.text());
      records=parsed;activeIndex=0;sourceName=file.name;
      const meta=$('inviteFileMeta');if(meta)meta.textContent=`${sourceName} · ${tx().loaded(records.length)}`;
      $('inviteError')?.classList.add('hidden');
      renderWorkspace();
    }catch(err){records=[];activeIndex=0;sourceName='';renderWorkspace();showError(err?.message||tx().bad);}
    e.target.value='';
  });
}
function renderModule(){
  const content=$('settingsContent');if(!content)return;
  active=true;
  document.querySelectorAll('#settingsTabs .tab').forEach(b=>b.classList.remove('active'));
  document.querySelector('#settingsTabs [data-invitations-tab]')?.classList.add('active');
  content.innerHTML=moduleHtml();bindImport();renderWorkspace();
}
function installTab(){
  const tabs=$('settingsTabs');if(!tabs)return;
  const adminVisible=Boolean(tabs.querySelector('[data-settings-tab="members"]')&&tabs.querySelector('[data-settings-tab="statistics"]'));
  if(!adminVisible){tabs.querySelector('[data-invitations-tab]')?.remove();active=false;return;}
  if(tabs.querySelector('[data-invitations-tab]'))return;
  const b=document.createElement('button');b.type='button';b.className=`tab${active?' active':''}`;b.dataset.invitationsTab='1';b.textContent=tx().tab;
  b.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();renderModule();});
  tabs.appendChild(b);
}
const observer=new MutationObserver(()=>installTab());
const tabs=$('settingsTabs');if(tabs)observer.observe(tabs,{childList:true,subtree:true});
installTab();

document.addEventListener('click',e=>{
  if(active&&e.target.closest('#settingsTabs [data-settings-tab]'))active=false;
},true);

const auth=$('authView');
if(auth)new MutationObserver(()=>{
  if(!auth.classList.contains('hidden')){records=[];activeIndex=0;sourceName='';active=false;}
}).observe(auth,{attributes:true,attributeFilter:['class']});

window.WFGG_INVITATIONS_TEST={parseCsv,messageFor,thanked:[...THANKED_OFFICERS],excluded:[...EXCLUDED_FROM_THANKS],portalUrl:PORTAL_URL};
})();
