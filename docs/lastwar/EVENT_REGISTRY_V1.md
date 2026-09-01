# Last War: Survival — Registre canonique des événements WfGg V1

**Gel de référence : 1 septembre 2026**  
**Source machine :** `data/lastwar/event-registry-v1.json`

Ce registre est volontairement commun à deux futurs usages :

1. le classement des assets graphiques Last War dans le catalogue V31 ;
2. le générateur de notifications WfGg (mêmes IDs canoniques, mêmes noms et mêmes cadences).

Il couvre le lancement d'un serveur, les événements permanents/récurrents, les saisons 1 à 6, les phases d'inter-saison/off-season et les événements limités/exceptionnels documentés jusqu'au 01/09/2026.

## Comptage V1

Le registre contient **189 entrées** :

- **98** entrées de type `season` ;
- **49** entrées de type `recurring-event` ;
- **32** entrées de type `limited` (fêtes, événements exceptionnels et sous-événements limités) ;
- **7** entrées de type `interseason` ;
- **3** événements ponctuels de lancement serveur.

Ce total ne signifie pas « 189 marques officielles d'événements distinctes ». Une entrée peut être un événement principal, un sous-événement, une campagne, une variante saisonnière ou un écran événementiel distinct. Cette granularité est voulue : deux sous-événements peuvent avoir des icônes, textures, bannières et notifications différentes.

## Saisons couvertes

- **S1 — The Crimson Plague** : 9 entrées propres à S1 + 5 entrées saisonnières transversales = **14** entrées liées à S1.
- **S2 — Polar Storm** : 9 + 5 = **14**.
- **S3 — Golden Kingdom** : 13 + 5 = **18**.
- **S4 — Evernight Isle** : 15 + 5 = **20**.
- **S5 — Wild West / Golden Wasteland / Land of Liberty** : 20 + 5 = **25**.
- **S6 — Shadow Rainforest / Lost Rainforest** : 27 + 5 = **32**.

La **Saison 7** est enregistrée uniquement comme futur élément non confirmé et reste désactivée pour la classification automatique tant qu'une liste publique suffisamment fiable des événements/mécaniques n'est pas disponible. Le registre ne doit pas transformer des rumeurs en vérité de catalogue.

## Événements récurrents / rotatifs — 49

Arms Race; Secret Mobile Squad; Hidden Treasure; Intercity Trade; Wanted; Alliance Duel; Warzone Duel; Capitol Conquest; Desert Storm; Winter Storm; Alliance Exercise; Rift Battlefield; Frontline Breakthrough; Math Master; General's Trial; Zombie Siege; Zombie Invasion; Doomsday; Ghost Ops; Rampage Boss; Dominator Growth Support; Street Rush; Bounty Hunter / Chasseur de prime; Glittering Market; Black Market; Champion Duel; Transfer Surge; Dominator Training Pass; Hero Shard Roulette; Bullseye; Hero Trial; Maxwell's Obsession; Mason's Counterattack; Violet's Determination; Scarlett's Investigation; Hero Battle Pass; Flash Gold Exchange; Drone Training Pass; Radar Pass; Treasure Hunt; Moonstone Blessing; War Preparation; Hero Growth Pass; Sarah's Ninja Way; Venom's Bandit Hunt; Ammo Bonanza; Energy Loot Quest; Alliance Train; Zombie Rush / Zombie Cataclysm.

Les cadences sont stockées individuellement (`daily`, `weekly`, `biweekly`, `monthly-ish`, `rotating`, etc.) et pourront être affinées sans changer l'ID canonique.

## Inter-saison / off-season explicite — 7

Meteorite Iron War; Sky Battlefront; Canyon Storm Battlefield; Season Celebration; Bingo Task; Black Market Challenge; Console Contest.

Attention : certains événements récurrents (Black Market, Champion Duel, Transfer Surge, etc.) peuvent aussi être vus pendant une transition de saison. Ils restent classés `recurring-event` avec une phase `cross-season` afin de ne pas confondre **nature de l'événement** et **fenêtre d'apparition**.

## Événements limités / exceptionnels — 32

### Parents / événements principaux

Music Festival; Gourmet Festival; Grand Sports Meet; Halloween Celebration; Ghost Town Escape; Halloween Treasure Hunt; Thanksgiving Event; Christmas Celebration; Holy Night Treasure Hunt; Valentine's Event; Easter Event; New Year Celebration; Chinese New Year (confiance moyenne); Crystal Event 2026.

### Sous-événements documentés

Crazy Rock; Rock Festival; Music Festival Exchange; Lucky Egg; Egg Journey; Easter Fest; Christmas Time; Snowopoly; Christmas Store; Double Joy; Christmas Carnival; Holiday Challenge; Christmas Gift; New Year Battle Pass; New Year Rhythm; New Year Mega Deals; New Year Celebration (onglet/sous-événement 2026); New Year Gift.

## Événements saisonniers transversaux — 5

Season Boost; Season Preview; Faction Awards; Purge Action; Hero Swap.

Ils sont rattachables aux saisons 1 à 6 dans le registre mais ne sont pas dupliqués six fois.

## Saison 1 — The Crimson Plague

Purge the Polluted Area; Genetic Recombination; City Clash S1; Crimson Legion; Warzone Expedition S1 (confiance moyenne); Infinite Octagon (confiance moyenne); Crimson Plague Warm Up (confiance moyenne); Crimson Plague Final Battle (confiance moyenne); Season 1 Celebration.

## Saison 2 — Polar Storm

Polar World; Cold Wave Incoming; Frost Boost; Polar Dishes; Beast Crisis; Rare Soil War; Reactivate Nuclear Furnace; The Age of Oil; Season 2 Celebration.

## Saison 3 — Golden Kingdom

Oasis Project; Archaeology & Digging; Return of the Dead; Desert Artifacts; Sandworm Hunter; Digging Stronghold Clash; City Clash S3; Spice War; Faction Duel S3; War's Eve S3; Capitol War S3; Trade Post S3; Season 3 Celebration.

## Saison 4 — Evernight Isle

Digging Stronghold Clash S4; Maneki-neko Light On; Blood Night Descends; City Clash S4; Ryōtei Restaurant; Blood Night Hunter; Divine Tree; Hunt for Wandering OniWagon; Trade Wars S4; Copper War; Faction Duel S4; War's Eve S4; Capitol War S4; Holy Mountain; Season 4 Celebration.

## Saison 5 — Wild West

Gold Prospecting; Area Selection; High Noon; Bank Stronghold Conquest; Finance Tycoon; CrystalGold Tycoon; City Clash S5; Railroad Tycoon; Wasteland Trade; Warzone Expedition S5; Trade Post War; Grand Nexus; Warzone Declaration of War; Warzone Routes; Warzone Invasion; Capture Outpost; Golden Palace; Vanquish the Enemies; Goldvein War (confiance moyenne); Season 5 Celebration.

## Saison 6 — Shadow / Lost Rainforest

Alliance Safe Time; Fungus Secrets; Beneath the Ruins; Capture Fishing Grounds; Fishing Fest; Fishing Ground Conquest; Rainforest's Wrath; Faction Tech; Faction War Rank; City Clash S6; Trade War S6; Cross-Warzone Expedition; Win-Win Cooperation; Sanctuary Conquest / Duel des Sanctuaires; Global Expedition; Altar Conquest; Faction Clash; Faction Duel S6; Outpost Conquest / Avant-postes de zone de guerre; Season Conclusion S6; Kimberly Awakening; DVA Awakening; Tesla Awakening / Éveil de Tesla; Awakening Swap / Échange d'Éveil; Merit Store / Boutique de Mérite; Trade Post S6; Season 6 Celebration.

## Règle de classification graphique

Deux relations sont séparées :

- `belongs-to` : l'asset **appartient directement** à l'événement ;
- `used-by` : l'asset est **utilisé par** l'événement mais peut être générique ou appartenir à un autre module.

Le classifieur automatique V31 ne crée pour le moment que des relations directes `belongs-to` à partir de `assetTokens` curatés et suffisamment spécifiques. Une absence de correspondance ne signifie jamais « générique » : l'asset reste `unknown` s'il n'existe pas de preuve suffisante. Les futures relations `used-by` devront provenir d'une dépendance Unity exacte ou d'une validation humaine.

## Contrat pour le futur générateur de notifications

L'ID du registre doit être réutilisé tel quel par le générateur de notifications. Chaque événement peut déjà fournir ou hériter des champs suivants :

- `id` — identifiant canonique stable ;
- `name` et `aliases` ;
- `kind`, `category`, `phase` ;
- `seasons` ;
- `cadence` ;
- `confidence` ;
- `assetTokens` ;
- `sourceKeys` ;
- `parent` pour les sous-événements.

Les champs de notification à ajouter plus tard sans casser le registre seront : calendrier exact par âge de serveur, fenêtre serveur, fuseau/locale, rappels T-24h/T-1h, audience, importance, modèle de message et langues FR/IT/EN/ES.

## Sources et maintenance

L'index machine contient les références vers Game8, LastWarSurvival.com, R5TOOLS, Cpt Hedge, Last War Tutorial, Last War Handbook, le corpus WfGg Saison 6 et la source 2026 du Crystal Event. Les entrées à `confidence: medium` sont conservées comme candidats documentés mais ne doivent pas être présentées comme des certitudes officielles.

Lorsqu'un nouvel événement apparaît, il faut **ajouter une entrée au registre**, conserver l'ID stable ensuite et enrichir ses alias/tokens/cadence. On ne modifie pas les anciennes entrées uniquement parce que la traduction affichée en jeu change.
