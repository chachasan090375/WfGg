# Collector Knowledge Engine - architecture cible continue

## Mission

Le Collector devient la mémoire technique et fonctionnelle de Last War et de WfGg.

Il ne se limite plus aux profils joueurs. Il doit indexer progressivement toutes les couches observables du jeu, relier les informations entre elles et rendre cette connaissance interrogeable sans recommencer manuellement une décompilation à chaque question.

La cible est l'exhaustivité. Le système ne prétend toutefois jamais connaître un élément sans preuve : ce qu'il ne comprend pas encore est conservé comme travail à faire.

## Couches couvertes

- protocole réseau et commandes ;
- modèles de données, champs et structures ;
- backend, API et services ;
- règles métier, formules, saisons, classements et limites ;
- cartes, régions, serveurs et coordonnées ;
- UI, vues, contrôleurs et navigation ;
- assets graphiques, sprites, atlas, icônes et textures ;
- animations, timelines, Spine, squelettes, particules et effets ;
- audio ;
- configuration et localisation ;
- relations entre toutes ces couches.

## Graphe de connaissance

La base sépare :

- artifacts : fichiers, bundles, modules, assets ;
- entities : commandes, champs, modules, assets, règles, écrans, serveurs ;
- evidence : preuve exacte et digest ;
- assertions : propriétés d'une entité ;
- edges : relations entre entités ;
- tasks : éléments non encore compris à retraiter ;
- sources et scan_runs : provenance, versions et historique.

Les états de connaissance restent OBSERVED, INFERRED, CONFIRMED et OBSOLETE.

Les formats non compris ne sont jamais jetés. Ils deviennent NEEDS_DECODER et génèrent automatiquement une tâche persistante.

## Fonctionnement permanent

Le worker tourne en arrière-plan et rescane périodiquement les sources enregistrées.

Le traitement est incrémental : un artefact dont le digest n'a pas changé n'est pas retraité.

Lorsqu'une nouvelle version du jeu apparaît, elle doit être ajoutée comme nouvelle version de source ; l'ancien savoir est conservé. Cela permet de comparer les mécanismes entre versions et saisons.

## Décodeurs

Les décodeurs sont spécialisés :

- texte, JSON et source ;
- bundle LWLF et bytecode Lua ;
- protocoles réseau ;
- assets et références ;
- images et métadonnées ;
- animations et timelines ;
- futurs formats propriétaires.

Un décodeur peut enrichir le graphe, créer des preuves et ajouter de nouvelles tâches.

## Questionnement

L'API locale read-only expose :

- GET /knowledge/health
- GET /knowledge/stats
- GET /knowledge/search?q=...
- GET /knowledge/ask?q=...
- GET /knowledge/entity?id=...

Une réponse doit toujours pouvoir remonter aux preuves qui la justifient.

## Sécurité

Le Knowledge Engine ne nécessite aucun token Last War pour analyser les sources statiques.

Les observations runtime restent limitées aux opérations déjà qualifiées en lecture seule. Le moteur n'expose aucune primitive de mutation du jeu et ne stocke aucun credential.

## Objectif long terme

Une question telle que « Où Last War expose-t-il le nombre total de joueurs d'un serveur ? » doit devenir une interrogation normale de la base.

Si la réponse n'est pas encore connue, le Collector doit montrer les candidats, les preuves disponibles et les tâches de décodage ouvertes, puis continuer à travailler en arrière-plan au lieu de repartir manuellement de zéro.
