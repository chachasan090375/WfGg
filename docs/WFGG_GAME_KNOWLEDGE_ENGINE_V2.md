# WfGg Game Knowledge Engine V2

## Mission

Le Game Knowledge Engine doit devenir la base de connaissance technique et fonctionnelle de Last War utilisée par WfGg.

Il ne répond plus ponctuellement à une question : il reconstruit automatiquement, version après version, tout ce qui est observable et démontrable depuis le client Android, les APK/splits, les bundles Unity, les modules Lua, les configs, les localisations, les UI, les animations, les protocoles et les observations runtime READ-ONLY.

La cible est une connaissance maximale et prouvable. Toute logique purement serveur qui n'est jamais exposée au client ou au protocole reste explicitement UNKNOWN jusqu'à apparition d'une preuve.

## Automatisation obligatoire

Chaque nouvelle version du jeu doit déclencher automatiquement : acquisition des artefacts, inventaire, extraction/décompilation/désassemblage, normalisation, classification, création des relations, diff avec la version précédente, consolidation des règles, génération du graphe de connaissance et production d'une file UNRESOLVED.

La file UNRESOLVED n'est pas une tâche manuelle obligatoire : elle alimente le cycle automatique suivant avec de nouveaux extracteurs ou de nouvelles preuves.

## Couches

### File / Package
Chaque fichier possède stable_id, SHA256, provenance, version client, split/APK/bundle d'origine, taille, type et relations physiques.

### Graphics & Reconstruction
Le moteur reprend la taxonomie historique du viewer WfGg : entité/sujet, usage, état, variantes, 2D/3D, statique/animé, transparence, dimensions, langue/région, saison/événement, provenance, alias multilingues, confiance par champ et statut d'exploration.

Les relations BELONGS_TO et USED_BY restent distinctes. Le graphe supporte aussi REFERENCES, LOADS, RENDERS_WITH, USES_TEXTURE, USES_MATERIAL, USES_MESH, ANIMATES et VARIANT_OF.

Il doit pouvoir reconstruire automatiquement une chaîne Hero -> prefab -> GameObjects/Transforms -> mesh -> material -> textures -> Animator -> AnimationClips -> camera -> RenderTexture -> RawImage UI, y compris les rendus injectés à runtime.

### UI
Indexation des fenêtres, prefabs UI, boutons, toggles, listes, textes/localisations, contrôleurs, callbacks, événements, modèles/data providers et commandes réseau. Une donnée affichée doit pouvoir être suivie jusqu'à sa source.

### Animation
Pour chaque animation : clip, durée, pistes, bones/transforms ciblés, propriétés animées, Animator state, transitions, conditions, blend trees, prefab consommateur, événement Lua/C# déclencheur et rendu final.

### Rules
Chaque règle est structurée : formule, opérateurs, ordre, caps/planchers, conditions, portée, saison, événement, version et preuves. Valeur affichée, config statique, calcul et observation runtime restent des preuves distinctes.

### Protocol
Pour chaque commande : nom, transport, direction, READ/WRITE, constructeur, schéma requête/réponse, champs, types, erreurs, cooldown/rate limit observables, UI/règle consommatrice et versions.

Une commande mutante identifiée n'est jamais automatiquement exécutable. Radar reste READ-ONLY ; toute capacité d'écriture vit dans un composant séparé.

### Runtime Observation
Collector fournit uniquement des preuves READ-ONLY : structures, états, coordonnées, entités, erreurs, transitions, compteurs, saison/version, serveur/région. Aucun token ou credential n'entre dans le Knowledge Engine.

## États de connaissance

OBSERVED = preuve directe ; INFERRED = déduction explicite ; CONFIRMED = corroboration indépendante ; OBSOLETE = anciennement valide ; UNKNOWN = donnée connue comme manquante, jamais devinée.

Chaque propriété peut avoir son propre statut, confidence, evidence_ids, first_seen, last_seen et versions.

## Périmètres temporels

Valeurs normalisées : permanent, recurring, interseason, season, limited, collaboration, regional, event.

## Stable IDs

Exemples : file:<sha256>, lua:<module>, unity:<bundle>:<path_id>, ui:<window>, protocol:<command>, localization:<key>, rule:<namespace>:<name>.

## Diff version à version

Le moteur produit automatiquement ajouté, supprimé, modifié, déplacé/renommé probable, relation ajoutée/supprimée, règle modifiée, schéma protocolaire modifié, localisation modifiée, asset visuel modifié et animation modifiée.

## Stockage

JSONL immuable pour les preuves, graphe versionné pour les relations, index SQLite/FTS généré pour la recherche, gros corpus sur le NAS WfGg, GitHub pour code/schémas/workflows/manifests.

## Viewer / recherche

Arborescence dossier -> sous-dossier -> fichier ; recherche multi-mots-clés ET ; expressions entre guillemets ; filtres famille/type/2D/3D/statique/animé/langue/saison/événement/héros ; vu/non-vu ; chemin ; similarité ; dépendances entrantes/sortantes ; reconstruction visuelle ; capture documentée.

La capture documentée contient nom, chemin, stable_id, SHA/version, type, famille, dimensions, sujet/héros/événement, provenance et relations principales.

## API cible

/knowledge/entity/:id
/knowledge/search
/knowledge/relations/:id
/knowledge/path/children
/knowledge/protocol/:command
/knowledge/ui/:window
/knowledge/rule/:id
/knowledge/animation/:id
/knowledge/diff/:versionA/:versionB
/knowledge/unresolved

Radar, Guides, Team Simulator et les agents WfGg doivent consommer cette API au lieu de réimplémenter leur propre compréhension du jeu.

## Premier bootstrap V2

Premier jalon : indexer automatiquement les 18 514 chunks Lua du client actuellement analysé, leurs SHA256 et chemins, leurs symboles observables, les candidats UI/protocoles/règles/saisons/animations/data managers, les références croisées de modules, l'inventaire APK/splits et la file UNRESOLVED.

Le bootstrap est entièrement statique : connexion Last War NONE ; mutation Last War NO ; scan jeu NO ; token NONE.

## Définition de COMPLETE

Pour une version donnée, un périmètre n'est COMPLETE que si tous les artefacts détectés sont inventoriés, tous les formats connus sont parsés ou explicitement UNSUPPORTED, toutes les relations détectables sont calculées, aucune file d'extraction n'est en attente et les inconnues restantes sont explicitement UNKNOWN.

Cette définition doit remplacer progressivement les faux COVERAGE_COMPLETE fondés uniquement sur l'épuisement d'un heuristique.