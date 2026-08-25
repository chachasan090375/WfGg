# Train native v15 — source de référence

Ce dossier prépare la consolidation du frontend Train dans le dépôt WfGg.

`app.v14.live.js` est une capture du `app.js` réellement servi en production via
`https://wfgg.pages.dev/train/` avec le bridge v14 actif.

À ce stade :
- aucun routage de production n'est modifié ;
- `_worker.js` continue de servir le bridge v14 existant ;
- ce fichier sert uniquement de référence canonique pour supprimer progressivement
  les réécritures runtime.

Contrôles de capture : syntaxe JS + présence des marqueurs fonctionnels v14.
