(() => {
'use strict';
/* WFGG_LASTWAR_ALLIANCE_NOTICE_V2
   Last War delivery model:
   - one alliance notification carries the public Portal address;
   - private player messages contain NO URL/domain fragment;
   - private messages may use emoji and remain personalized;
   - personal codes stay browser-local and are never included in the alliance notice.
*/
const PORTAL_URL='https://wfgg.pages.dev/';
const canonicalPseudo=p=>{
  const s=String(p||'').trim();
  return (s==='εlα ツ'||s==='εlo ツ')?'εlο ツ':s;
};
function stableVariant(value){
  let h=2166136261;
  for(const ch of String(value||'')){h^=ch.codePointAt(0);h=Math.imul(h,16777619)}
  return h>>>0;
}
const ALLIANCE_NOTICE=[
  '📣 Nouveau portail WfGg',
  '',
  'Le nouveau portail de l’alliance est ouvert 🚀',
  'Vous y trouverez le Train et les rotations Conducteur/VIP, la Bourse d’échanges, les Guides Saison 6 / Inter-Saison, puis progressivement de nouveaux outils.',
  '',
  `🌐 ${PORTAL_URL}`,
  '',
  '🔐 Votre code personnel vous sera envoyé séparément en message privé.',
  '',
  `💜 Un grand merci à l’ensemble du bureau R4/R5 pour son travail sur le projet et son investissement durant toute l’Inter-Saison.`
].join('\n');
const openings=[
  p=>`Salut ${p} 👋 Ton accès au nouveau portail WfGg est prêt !`,
  p=>`Hello ${p} 👋 Bonne nouvelle : ton accès perso WfGg est prêt.`,
  p=>`Salut ${p} 🚀 Le nouveau portail WfGg t’attend !`,
  p=>`Hello ${p} ! On a survécu au code et aux tableaux 😄 Ton accès est prêt.`,
  p=>`Salut ${p} 👋 La nouvelle boîte à outils WfGg est ouverte pour toi.`,
  p=>`Hello ${p} 🚂 Ton accès WfGg vient de sortir de l’atelier.`,
  p=>`Salut ${p} ! Petite nouveauté WfGg : ton accès personnel est actif ✨`,
  p=>`Hello ${p} 👋 Le chantier WfGg avance, et ton accès est maintenant prêt.`
];
const summaries=[
  `Tu y retrouveras le Train, les rotations Conducteur/VIP, la Bourse d’échanges et les Guides Saison 6 / Inter-Saison.`,
  `Au menu : Train, planning Conducteur/VIP, Bourse pour les échanges et Guides WfGg.`,
  `Le portail regroupe déjà le Train, les rotations, la Bourse et les Guides au même endroit.`,
  `Tu peux déjà y suivre le Train et tes rotations, utiliser la Bourse et consulter les Guides.`,
  `On y centralise les outils utiles à l’alliance : Train, rotations, échanges et Guides.`,
  `Le premier objectif est simple : retrouver Train, rotations, Bourse et Guides sans courir partout.`
];
const future=[
  `Le simulateur d’équipes et d’autres outils arriveront ensuite.`,
  `Et ce n’est que le début : d’autres modules sont déjà prévus.`,
  `Le portail continuera d’évoluer avec le simulateur d’équipes et de nouveaux outils.`,
  `La suite est déjà en préparation, notamment le simulateur d’équipes.`
];
const notificationHints=[
  `🌐 Tu trouveras l’adresse de l’appli dans les notifications d’alliance.`,
  `🌐 Pour l’adresse de l’appli, regarde les notifications d’alliance.`,
  `🌐 L’adresse du portail est dans les notifications d’alliance : pas de lien dans ce message privé.`,
  `🌐 Direction les notifications d’alliance pour récupérer l’adresse de l’appli.`,
  `🌐 L’adresse est publiée dans les notifications d’alliance ; ici je t’envoie seulement ton accès perso.`,
  `🌐 Tu trouveras le chemin vers l’appli dans les notifications d’alliance.`
];
const thanks=[
  `💜 Un grand merci à l’ensemble du bureau R4/R5 pour son travail sur le projet et son investissement durant toute l’Inter-Saison.`,
  `💜 Merci au bureau R4/R5 pour le travail collectif, le temps consacré au projet et l’investissement de toute l’Inter-Saison.`,
  `💜 Ce lancement doit aussi beaucoup au travail du bureau R4/R5 : merci pour l’énergie consacrée au projet et à toute l’Inter-Saison.`,
  `💜 Merci à l’ensemble du bureau R4/R5 pour sa contribution au portail et son investissement pendant l’Inter-Saison.`
];
const codeLines=[
  c=>`🔐 Ton code personnel : ${c}`,
  c=>`🔐 Code personnel : ${c}`,
  c=>`🔐 Ta clé d’entrée WfGg : ${c}`,
  c=>`🔐 Pour te connecter, ton code personnel est : ${c}`
];
const closings=[
  `Bonne découverte 😎`,
  `À toi de jouer maintenant 🚀`,
  `Fais un tour et dis-nous ce qu’on peut encore améliorer 👍`,
  `Bienvenue dans la nouvelle boîte à outils WfGg 💜`,
  `Tu peux tester dès maintenant. Bonne visite !`,
  `Et voilà, mission accès accomplie 😄`
];
function adminParagraph(rank){
  if(rank==='R4')return `⚙️ Ton rang R4 donne aussi accès aux outils du bureau : alliance, Joueurs & accès, statistiques, droits, profils et réinitialisation des codes.`;
  if(rank==='R5')return `👑 Ton rang R5 donne aussi accès aux outils du bureau et aux fonctions de leadership : alliance, Joueurs & accès, statistiques, droits, profils et réinitialisation des codes.`;
  return '';
}
function buildMessage(pseudo,rank,code){
  pseudo=canonicalPseudo(pseudo);rank=String(rank||'').toUpperCase();code=String(code||'').trim();
  const h=stableVariant(pseudo);
  return [
    openings[h%openings.length](pseudo),
    summaries[(h>>>3)%summaries.length],
    future[(h>>>6)%future.length],
    notificationHints[(h>>>9)%notificationHints.length],
    thanks[(h>>>12)%thanks.length],
    adminParagraph(rank),
    codeLines[(h>>>15)%codeLines.length](code),
    closings[(h>>>18)%closings.length]
  ].filter(Boolean).join('\n\n');
}
function parseCurrent(ta){
  const card=ta.closest('.invite-workspace');
  const pseudo=canonicalPseudo(card?.querySelector('.invite-player h3')?.textContent||'');
  const rank=String(card?.querySelector('.rank-badge')?.textContent||'').trim().toUpperCase();
  const full=String(ta.value||'');
  const code=(full.match(/(?:Ton\s+)?code personnel\s*:\s*(\d{6})/i)||[])[1]||'';
  return pseudo&&/^R[1-5]$/.test(rank)&&/^\d{6}$/.test(code)?{pseudo,rank,code}:null;
}
async function copyText(text,button){
  try{
    await navigator.clipboard.writeText(text);
  }catch{
    const ta=document.createElement('textarea');
    ta.value=text;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.opacity='0';
    document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();
  }
  if(button){const old=button.textContent;button.textContent='✅ Copié';setTimeout(()=>button.textContent=old,1200);}
}
function ensureAllianceNotice(host){
  if(!host||host.querySelector('[data-alliance-notice-v2]'))return;
  const box=document.createElement('section');
  box.dataset.allianceNoticeV2='v2';
  box.className='settings-card-block';
  const title=document.createElement('h3');title.textContent='📣 Notification d’alliance';
  const help=document.createElement('p');help.className='muted';help.textContent='À publier une seule fois dans les notifications d’alliance. Elle contient l’adresse du Portail, jamais les codes personnels.';
  const ta=document.createElement('textarea');ta.id='inviteAllianceNotice';ta.readOnly=true;ta.rows=10;ta.value=ALLIANCE_NOTICE;ta.spellcheck=false;
  const button=document.createElement('button');button.id='inviteAllianceCopy';button.type='button';button.className='secondary-button';button.textContent='📋 Copier la notification d’alliance';
  button.addEventListener('click',()=>copyText(ALLIANCE_NOTICE,button));
  box.append(title,help,ta,button);
  host.prepend(box);
}
function enhance(ta){
  if(!ta||ta.dataset.lastwarAlliance==='v2')return;
  const row=parseCurrent(ta);if(!row)return;
  const text=buildMessage(row.pseudo,row.rank,row.code);
  ta.dataset.lastwarAlliance='v2';ta.spellcheck=false;ta.value=text;
  const host=ta.closest('.invite-workspace');
  ensureAllianceNotice(host);
  host?.querySelector('[data-lastwar-safe-controls]')?.remove();
  host?.querySelector('[data-lastwar-single-meta]')?.remove();
  const oldMeta=host?.querySelector('[data-lastwar-alliance-meta]');if(oldMeta)oldMeta.remove();
  const meta=document.createElement('div');
  meta.dataset.lastwarAllianceMeta='v2';meta.className='muted';
  meta.textContent=`Message privé · ${text.length} caractères · avec emoji · adresse via notifications d’alliance`;
  ta.after(meta);
  const copy=host?.querySelector('#inviteCopy');if(copy)copy.textContent='📋 Copier le message privé';
  const copySent=host?.querySelector('#inviteCopySent');if(copySent){copySent.textContent='📋 Copier + marquer envoyé';copySent.disabled=false;}
}
function scan(){document.querySelectorAll('#inviteMessage').forEach(enhance)}
new MutationObserver(()=>queueMicrotask(scan)).observe(document.documentElement,{childList:true,subtree:true});
scan();
window.WFGG_LASTWAR_CHAT_SAFE_TEST={MODE:'alliance-notice-v2',PORTAL_URL,ALLIANCE_NOTICE,buildMessage,canonicalPseudo};
})();
