(() => {
'use strict';
/* WFGG_LASTWAR_SINGLE_V1
   Single-message Last War experiment.
   The portal address is deliberately broken into spaced fragments so the game chat
   is less likely to classify it as a clickable link. Messages stay browser-local,
   contain no Unicode emoji, and vary deterministically from one player to another.
*/
const BROKEN_ADDRESS='wfgg . pages . dev';
const THANKED=['Metatouk','Ogie Ogilthorpe 7','ValFada','Shockwave XY','Sab93fr','εlο ツ','cat 49','Flawene'];
const canonicalPseudo=p=>{
  const s=String(p||'').trim();
  return (s==='εlα ツ'||s==='εlo ツ')?'εlο ツ':s;
};
function stableVariant(value){
  let h=2166136261;
  for(const ch of String(value||'')){h^=ch.codePointAt(0);h=Math.imul(h,16777619)}
  return h>>>0;
}
const openings=[
  p=>`Salut ${p}. Petite nouveauté WfGg : ton accès au nouveau portail est prêt.`,
  p=>`Hello ${p}. Après quelques mois de bricolage sérieux côté WfGg, ton accès au portail est prêt.`,
  p=>`Salut ${p}. Le bureau a enfin sorti le nouveau portail WfGg de l'atelier, et ton accès est prêt.`,
  p=>`Hello ${p}. Bonne nouvelle : le nouveau portail WfGg est ouvert et ton accès personnel t'attend.`,
  p=>`Salut ${p}. On a survécu aux tableaux, aux rotations et au code : le portail WfGg est prêt pour toi.`,
  p=>`Hello ${p}. La nouvelle boîte à outils WfGg est ouverte, et tu fais partie des premiers à recevoir ton accès.`,
  p=>`Salut ${p}. Le portail WfGg est maintenant en ligne : voici ton accès personnel.`,
  p=>`Hello ${p}. Le chantier WfGg avance : le portail est prêt et ton accès vient d'être préparé.`
];
const project=[
  `Le bureau R4/R5 travaille dessus depuis plusieurs mois pour réunir au même endroit les outils utiles à l'alliance.`,
  `L'idée est simple : arrêter de courir après les infos et regrouper nos outils WfGg dans un seul espace.`,
  `Ce portail est le résultat de plusieurs mois de travail du bureau pour centraliser l'organisation de l'alliance.`,
  `On voulait un point d'entrée unique, plus clair et plus pratique pour les outils WfGg : c'est maintenant chose faite.`,
  `Le projet a mûri pendant plusieurs mois avec un objectif très simple : rendre l'organisation WfGg plus fluide.`,
  `Le bureau a construit ce portail pour rassembler progressivement les outils de l'alliance au même endroit.`,
  `Après plusieurs mois de préparation, on dispose enfin d'un espace commun pour les outils et infos WfGg.`,
  `Le portail doit devenir notre boîte à outils commune, avec les fonctions actuelles et celles qui arrivent ensuite.`
];
const tools=[
  `Tu y trouveras déjà le Train, les rotations Conducteur/VIP, la Bourse d'échanges et les Guides Saison 6 / Inter-Saison.`,
  `Au programme : Train, planning Conducteur/VIP, Bourse pour les échanges et Guides Saison 6 / Inter-Saison.`,
  `Le Train et ses rotations sont déjà intégrés, avec la Bourse d'échanges et les Guides Saison 6 / Inter-Saison.`,
  `Tu peux déjà consulter le Train, suivre les rotations, utiliser la Bourse et retrouver les Guides au même endroit.`,
  `Les premiers outils disponibles sont le Train, les rotations Conducteur/VIP, la Bourse et les Guides WfGg.`,
  `Le portail centralise déjà le Train, les passages Conducteur/VIP, les échanges de dates et les Guides.`,
  `Tu retrouveras les rotations du Train, la Bourse d'échanges et les contenus Saison 6 / Inter-Saison sans changer d'espace.`
];
const futures=[
  `Le simulateur d'équipes et d'autres générateurs arriveront ensuite.`,
  `Et ce n'est que le début : le simulateur d'équipes et d'autres outils sont déjà prévus.`,
  `La suite comprendra notamment le simulateur d'équipes et de nouveaux outils de communication.`,
  `D'autres modules suivront, dont le simulateur d'équipes et des générateurs pour nous faire gagner du temps.`,
  `Le portail continuera d'évoluer avec le simulateur d'équipes et d'autres fonctions en préparation.`,
  `Prochaine étape : enrichir progressivement le portail avec le simulateur d'équipes et de nouveaux outils.`
];
const thanks=[
  `Un grand merci à ${THANKED.join(', ')} pour leur travail sur le projet et leur investissement durant toute l'Inter-Saison.`,
  `Merci à ${THANKED.join(', ')} pour le temps consacré au projet et pour leur investissement pendant toute l'Inter-Saison.`,
  `Ce lancement doit aussi beaucoup à ${THANKED.join(', ')} : merci pour leur implication sur le projet et durant toute l'Inter-Saison.`,
  `Merci tout particulièrement à ${THANKED.join(', ')} pour leur contribution au portail et leur investissement durant toute l'Inter-Saison.`
];
const linkJokes=[
  `(Oui, l'adresse est découpée exprès : le chat Last War joue parfois au videur et refuse les liens.)`,
  `(Adresse en kit volontaire : Last War aime tellement filtrer les liens qu'on lui donne les points séparément.)`,
  `(Les espaces sont volontaires : petit camouflage maison pour éviter que le chat Last War fasse son difficile.)`,
  `(Ne recolle pas les morceaux avant de la saisir dans ton navigateur : c'est notre petite ruse anti-filtre Last War.)`,
  `(C'est bien l'adresse, simplement déguisée avec des espaces pour essayer de passer sous le radar du filtre Last War.)`,
  `(Oui, on écrit l'adresse façon puzzle : c'est juste pour éviter que le filtre du chat ne décide de faire du zèle.)`
];
const closings=[
  `Tu peux tester ton accès dès maintenant. Bonne découverte.`,
  `Ton accès est prêt. Fais un tour et dis-nous ce qui peut encore être amélioré.`,
  `Tu peux l'utiliser dès maintenant ; les prochains modules arriveront progressivement.`,
  `Voilà, tu as tout ce qu'il faut pour commencer. Bonne visite sur le portail WfGg.`,
  `À toi de jouer maintenant : ton accès est actif et le portail continuera d'évoluer avec vos retours.`,
  `Tu peux commencer tout de suite. Bienvenue dans la nouvelle boîte à outils WfGg.`
];
function adminParagraph(rank){
  if(rank==='R4')return `Ton rang R4 donne aussi accès aux outils du bureau : paramètres alliance, Joueurs & accès, statistiques, droits, gestion des profils et réinitialisation des codes.`;
  if(rank==='R5')return `Ton rang R5 donne aussi accès aux outils du bureau : paramètres alliance, Joueurs & accès, statistiques, droits, gestion des profils et réinitialisation des codes, avec les fonctions de leadership R5.`;
  return '';
}
function buildMessage(pseudo,rank,code){
  pseudo=canonicalPseudo(pseudo);rank=String(rank||'').toUpperCase();code=String(code||'').trim();
  const h=stableVariant(pseudo);
  const parts=[
    openings[h%openings.length](pseudo),
    project[(h>>>3)%project.length],
    tools[(h>>>6)%tools.length],
    futures[(h>>>9)%futures.length],
    thanks[(h>>>12)%thanks.length],
    adminParagraph(rank),
    `Adresse : ${BROKEN_ADDRESS}`,
    linkJokes[(h>>>15)%linkJokes.length],
    `Code personnel : ${code}.`,
    closings[(h>>>18)%closings.length]
  ].filter(Boolean);
  return parts.join('\n\n');
}
function parseCurrent(ta){
  const card=ta.closest('.invite-workspace');
  const pseudo=canonicalPseudo(card?.querySelector('.invite-player h3')?.textContent||'');
  const rank=String(card?.querySelector('.rank-badge')?.textContent||'').trim().toUpperCase();
  const full=String(ta.value||'');
  const code=(full.match(/(?:Ton\s+)?code personnel\s*:\s*(\d{6})/i)||[])[1]||'';
  return pseudo&&/^R[1-5]$/.test(rank)&&/^\d{6}$/.test(code)?{pseudo,rank,code}:null;
}
function enhance(ta){
  if(!ta||ta.dataset.lastwarSingle==='v1')return;
  const row=parseCurrent(ta);if(!row)return;
  const text=buildMessage(row.pseudo,row.rank,row.code);
  ta.dataset.lastwarSingle='v1';ta.spellcheck=false;ta.value=text;
  const host=ta.closest('.invite-workspace');
  host?.querySelector('[data-lastwar-safe-controls]')?.remove();
  const oldMeta=host?.querySelector('[data-lastwar-single-meta]');
  if(oldMeta)oldMeta.remove();
  const meta=document.createElement('div');
  meta.dataset.lastwarSingleMeta='v1';meta.className='muted';
  meta.textContent=`Message unique · ${text.length} caractères · adresse découpée · sans emoji`;
  ta.after(meta);
  const copy=host?.querySelector('#inviteCopy');if(copy)copy.textContent='Copier le message';
  const copySent=host?.querySelector('#inviteCopySent');if(copySent){copySent.textContent='Copier + marquer envoyé';copySent.disabled=false;}
}
function scan(){document.querySelectorAll('#inviteMessage').forEach(enhance)}
new MutationObserver(()=>queueMicrotask(scan)).observe(document.documentElement,{childList:true,subtree:true});
scan();
window.WFGG_LASTWAR_CHAT_SAFE_TEST={MODE:'single-v1',BROKEN_ADDRESS,buildMessage,canonicalPseudo};
})();
