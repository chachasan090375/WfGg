# WfGg — Last War Graphics History Index

Ce dossier conserve la mémoire réutilisable des travaux graphiques/reverse-engineering Last War.

## Couverture historique

Chaîne reconstruite et indexée :

`MASTER V002 (inclut V001 + 0002-0005) → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012`

Le checkpoint historique terminal est l'incrément **0012 du 29/08/2026**.

## Fichiers canoniques

- `lastwar-graphics-master-index-v1.json` : état de l'installation courante, chemins `assetPath → bundle → fragment/groupe/offset/span → dépendances`.
- `lastwar-graphics-history-v002-0012-v1.json` : connaissances historiques importées depuis les archives V002/0006-0012, y compris les chemins héros, familles World/terrain, phases, assets compagnons et jalons de reconstruction.
- `lastwar-graphics-history-evidence-v1.json` : registre des rapports historiques graphiques retrouvés dans les archives.
- `lastwar-graphics-asset-path-index-v1.tsv` : lookup rapide des chemins de l'installation courante.

## Migration d'archives effectuée

- 8 sources de la chaîne V002→0012 analysées.
- 336 documents texte/JSON/TSV analysés.
- 4 022 entrées d'archives inventoriées, y compris les ZIP imbriqués utiles.
- 122 rapports/documents graphiques majeurs inscrits dans le registre d'évidence.
- Les phases Last War historiques couvrent notamment 6→31 puis 39→54.

Les offsets physiques historiques ne doivent pas être réutilisés aveuglément après une mise à jour du jeu. Les connaissances d'identité, chemins, bundle IDs et relations servent de point de départ ; les coordonnées physiques sont re-résolues par l'index de l'installation courante.

## Requêtes

```bash
python scripts/lastwar-graphics-index-query.py --contains formation
python scripts/lastwar-graphics-index-query.py --contains WorldCityGrass
python scripts/lastwar-graphics-index-query.py --bundle 17794
python scripts/lastwar-graphics-index-query.py --phase 45
python scripts/lastwar-graphics-index-query.py --phase 51C
python scripts/lastwar-graphics-index-query.py --evidence HERO_ICONS_EXACT
```

## Règle de projet

Avant tout nouveau scan global graphique :

1. interroger l'index courant ;
2. interroger l'historique V002→0012 ;
3. consulter les rapports d'évidence déjà identifiés ;
4. seulement si aucune piste n'existe, lancer un nouvel audit ciblé ;
5. tout nouveau résultat doit ensuite enrichir `master-assets-v2/meta/` et/ou cet index historique.

Cette règle vise explicitement à éviter de recommencer les longues chaînes d'extraction déjà effectuées.
