# Train native v15 — source de référence

Ce dossier prépare la consolidation du frontend Train dans le dépôt WfGg.

`app.v14.live.js` est une capture du `app.js` réellement servi en production via
`https://wfgg.pages.dev/train/` avec le bridge v14 actif.

État actuel :
- `app.v15.js` reste la référence canonique du frontend Train consolidé ;
- la production `/train/app.js` est encore obtenue depuis l'upstream historique puis
  corrigée par `_worker.js` ;
- le bridge runtime `WFGG_TRAIN_ROSTER_INTEGRATION_UI_RUNTIME_V1` aligne maintenant
  la production sur les cycles fixes et les quotas d'intégration de cette référence ;
- la recette de production vérifie explicitement ce marqueur dans le JS réellement servi.

Contrôles de capture : syntaxe JS + présence des marqueurs fonctionnels v14.
