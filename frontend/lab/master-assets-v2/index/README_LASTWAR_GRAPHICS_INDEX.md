# WfGg — Last War Graphics Master Index

Cet index est le point d’entrée canonique pour les futurs travaux graphiques Last War.

- Assets catalogués : **107247**
- Bundles : **36048**
- Fragments physiques : **1**
- Rapports JSON liés : **51**

## Fichiers

- `lastwar-graphics-master-index-v1.json` : index complet machine-readable.
- `lastwar-graphics-asset-path-index-v1.tsv` : lookup rapide/grep par chemin.

## Chemin de reconstruction

`assetPath → bundleId → logical/alias → fragment/groupe/offset/span → dépendances → UnityPy → hiérarchie/meshes/matériaux/textures`

Pour chaque futur audit, conserver le JSON source dans `master-assets-v2/meta/` puis relancer `scripts/lastwar-graphics-master-index-refresh.sh`.

## Règle de projet

Ne pas recommencer un scan global avant d’avoir interrogé cet index et les `evidenceFiles` du bundle concerné.
