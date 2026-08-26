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

## Wanted Codes 39 / 64 / 87

Les Codes sont traités comme des objectifs offensifs de 90 secondes : le boss n'attaque pas. Le classement ne doit donc pas utiliser la puissance globale affichée comme raccourci.

Pour ces trois objectifs :

- `displayedPower` a un poids de 0 ;
- DEF a un poids de 0 ;
- HP/PV a un poids de 0 ;
- l'ancre visible initiale est l'ATK affichée ;
- le score final doit représenter les dégâts offensifs estimés sur 90 s en ajoutant les compétences, multiplicateurs de dégâts, critique, vitesse d'attaque, cooldown, bonus PvE/monstres, buffs d'équipe, buffs de placement et debuffs offensifs vérifiés ;
- une statistique normalement défensive ne peut réentrer dans le calcul que si une compétence offensive vérifiée scale explicitement dessus ou est déclenchée par elle.

Bonus spécifiques déjà gelés : Code 39 = Aircraft +50 % dégâts ; Code 64 = Missile +50 % ; Code 87 = Tank +50 %.

Le moteur `positioning-engine.v1.js` expose actuellement un **score offensif relatif de recherche**, pas encore une prédiction exacte des dégâts 90 s.

## Placement des 5 héros

La composition et le placement sont deux variables distinctes. Le schéma `data/formation-positioning.v1.json` définit les cinq positions :

- front-left ;
- front-right ;
- back-left ;
- back-center ;
- back-right.

Lorsqu'un buff actif dépend du placement, d'une ligne, d'un héros adjacent ou d'une position relative, le moteur doit évaluer les **120 permutations (5!)** de la même composition et conserver le meilleur placement.

La géométrie générique du mot « adjacent » reste marquée `needs-in-game-validation`. Elle ne doit pas modifier une recommandation de production tant qu'une capture du client ou un test validé ne confirme pas le ciblage exact. Les effets de héros non vérifiés ne sont pas inventés : `verifiedHeroEffects` est volontairement vide à ce stade.

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
- équipement des héros ;
- placement exact des cinq héros et buffs d'adjacence / ligne / position.

## Prudence sur la formule finale

Les pourcentages visibles et documentés peuvent être modélisés précisément. En revanche, la formule interne complète de dégâts (ordre des multiplicateurs, mitigation, critique, résistances et interactions) n'est pas publiée de façon exhaustive. Le premier moteur donne donc un score relatif traçable, puis sera calibré à partir de rapports de combat si nécessaire.
