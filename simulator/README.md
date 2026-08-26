# WfGg Simulator — module autonome

Ce dossier lance le simulateur comme module indépendant. Il n'est pas relié au Portail WfGg à ce stade.

## Principe de calcul

Le comparateur ne doit pas additionner aveuglément toute la puissance d'un compte. Il retient en priorité les effets qui peuvent modifier le classement relatif de deux compositions :

- effet ciblant Tank, Aircraft ou Missile Vehicle ;
- effet dépendant du nombre de héros d'un même type dans l'escouade ;
- effet lié au type de l'adversaire / au triangle de contre ;
- effet lié à un contexte précis (Wanted Boss 39/64/87, PvP, saison, etc.) ;
- effet fourni par un héros, une arme exclusive ou une carte tactique et dépendant de la composition.

Un bonus strictement global, appliqué de façon identique à toutes les compositions comparées, est classé `global-common` et exclu du score différentiel initial.

## Modèle de données

Chaque buff possède au minimum :

- `scope`: `global-common`, `tank`, `aircraft`, `missile`, `composition`, `opponent`, `context` ;
- `context`: `permanent`, `pvp`, `pve`, `wanted-39`, `wanted-64`, `wanted-87`, `season-1` ... `season-6` ;
- `stat`: `attack`, `defense`, `hp`, `damage`, `damageReduction`, etc. ;
- `stacking`: `flat`, `percent`, `per-level`, `per-matching-hero`, `conditional` ;
- `confidence`: `verified`, `strong-community`, `needs-in-game-validation`.

Le fichier `data/differential-buffs.v1.json` contient la première base documentée.

## Inventaire d'équipement

Le futur menu Armes / Équipement sera structuré en quatre familles :

1. Gun / Cannon / Railgun — offensif, ATK ;
2. Data Chip — offensif, critique / dégâts ;
3. Armor / Reactive Armor — défense physique / survie ;
4. Radar — défense énergie / compétence / survie.

Chaque pièce devra pouvoir enregistrer au minimum : rareté, niveau, étoiles/promotion, héros actuellement équipé, et disponibilité pour une réaffectation virtuelle dans le simulateur.

## Points déjà considérés comme essentiels

- recherches Hero et Mastery propres aux trois types ;
- recherches Synergy qui évoluent avec le nombre de héros du même type ;
- bonus de formation 3 / 3+2 / 4 / 5 héros ;
- Tank/Air/Missile Centers et effets type-specific ;
- armes exclusives avec buff de type ;
- triangle de contre ;
- Wanted Boss 39 / 64 / 87 ;
- bâtiments saisonniers différentiels ;
- Tactics Cards qui changent les règles de composition (notamment 4+1) ;
- équipement des héros.

## Prudence sur la formule finale

Les pourcentages visibles et documentés peuvent être modélisés précisément. En revanche, la formule interne complète de dégâts (ordre des multiplicateurs, mitigation, critique, résistances et interactions) n'est pas publiée de façon exhaustive. Le premier moteur donnera donc un score relatif traçable, puis sera calibré à partir de rapports de combat si nécessaire.
