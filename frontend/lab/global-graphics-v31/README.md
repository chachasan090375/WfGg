# WfGg Last War LAB — Global Graphics V31

Branche de travail : `lab-global-graphics-catalog-v31`

## Objectif

Indexer l'ensemble du corpus graphique connu sans extraire durablement toutes les images. Le catalogue sépare l'arborescence physique des facettes sémantiques afin qu'un même asset puisse être simultanément, par exemple, `vehicles > tank`, `icon`, `formation` et `event`.

## Source canonique

`frontend/lab/master-assets-v2/index/lastwar-graphics-asset-path-index-v1.tsv`

Le build CI validé le 01/09/2026 a produit :

- 107 247 assets indexés ;
- 121 761 nœuds de chemin (dossiers, sous-dossiers et feuilles) ;
- 100 % des 107 247 assets reliés à un nœud de chemin ;
- base SQLite finale ~285 MB sur le runner CI ;
- FTS5 activé.

## Facettes principales

- famille / sous-famille ;
- sujet ou entité représentée ;
- forme visuelle (`icon`, `portrait`, `background`, `texture`, etc.) ;
- contexte de jeu (`hero`, `formation`, `combat`, etc.) ;
- type technique ;
- état / variante / langue ;
- périmètre éditorial-temporel ;
- confiance et preuves de classement ;
- provenance exacte (bundle, fragment, offset, taille).

## Périmètre éditorial-temporel

Valeurs :

- `generic` — ressource explicitement générique ;
- `feature` — fonction permanente ;
- `event` — événement ;
- `recurring-event` — événement récurrent ;
- `season` — saison ;
- `interseason` — inter-saison / pré-saison ;
- `limited` — contenu limité dans le temps ;
- `collaboration` — collaboration ;
- `regional` — variante région/langue explicite ;
- `unknown` — preuve insuffisante.

**Règle absolue : l'absence de preuve d'événement n'est jamais une preuve de contenu générique.** Les assets sans preuve suffisante restent `unknown`.

`Chasseur de prime` est enregistré comme scope connu `bounty-hunter`, de type `recurring-event`, avec alias français/anglais. Sa cadence exacte reste volontairement `periodic-unspecified` tant qu'une donnée du jeu ne prouve pas une périodicité plus précise.

## Viewer

Page : `frontend/lab/lastwar-global-graphics-viewer-v31.html`

Serveur local : `scripts/lastwar-global-graphics-server-v31.py`

Le viewer reconstruit uniquement le bundle demandé à partir de la position physique de l'index (`fragment + offset + spanBytes`), puis tente un rendu réel Sprite/Texture2D via UnityPy. Le contexte Unity est détruit après le rendu. Un micro-cache limité conserve au maximum quelques bundles matérialisés et rendus PNG pour rendre Suivant/Précédent fluide.

La capture documentée génère une fiche PNG incluant le visuel réel et les informations utiles pour retrouver l'asset : ID WfGg stable, chemin, famille, contexte, scope, bundle, fragment, offset, taille et confiance.

## Lancement Termux

```bash
git fetch origin
git switch lab-global-graphics-catalog-v31
git pull --ff-only
bash scripts/lastwar-global-graphics-v31.sh
```

Le runner reconstruit le catalogue local, enrichit/corrige les scopes, construit la hiérarchie physique et démarre ensuite le viewer local.

## Limite volontaire actuelle

Le champ de périmètre décrit d'abord **l'appartenance prouvée** par les noms/chemins et règles connues. Une ressource générique utilisée par un événement ne doit pas être faussement reclassée comme appartenant à cet événement. Une future couche `used-by / related-to` pourra propager les événements via les relations de dépendance **exactes** tout en conservant l'appartenance intrinsèque séparée.

Les relations candidates ne doivent jamais être promues au même niveau que les relations exactes.
