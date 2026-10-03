# ChaCha DEV — Audit de convergence historique et Roadmap maître — 03/10/2026

## Conclusion
L'ancienne `autonomy-gap-roadmap.v1.json` ne représente qu'une vue des écarts d'autonomie. Elle ne remplace ni le Blueprint V4.1, ni la Reference Architecture V5, ni les couches V6/V7/V8, ni les chantiers Canonical Path / Remote MCP. Le produit doit désormais avoir une Roadmap maître unique ; la roadmap autonomie devient une vue dérivée.

## Décision de continuité
- **V4.1** : document historique supersédé, mais ses exigences restent absorbées par V5.
- **V5** : reste le socle architectural officiel : composants, Manifest V3, 18 domaines qualité, capability registry, evidence gates, stockage, lifecycle, golden paths.
- **Project Planner** : n'est pas jeté ; il évolue en **Solution Composer**.
- **Technical Design Router** : reste valable en aval du Solution Composer.
- **V6 Domain Orchestration** : concepts conservés, mais migration obligatoire. L'invariant « Agent Foundry avant toute exécution domaine » devient obsolète ; Foundry intervient après classification/réutilisation. Les tests historiques montrent aussi un drift de routage et du contrat Guardian/Technology Watch.
- **Lifecycle** : reste le gate de progression, mais la règle « un seul writer global » doit être remplacée par des lanes d'écriture isolées et des barrières d'intégration pour permettre le multitâche.
- **Object Factory** : toujours actuel et vérifié ; devient une sous-fabrique spécialisée.
- **Human Conversation / Direct Operator** : toujours actuels ; l'Artifact Fabric les étend au multimodal et aux fichiers produits.
- **UMG/CCR** : restent obligatoires pour tout composant évolutif.
- **Canonical Path** : la branche standalone du 29/09 est supersédée par la version enrichie incluse dans `structural-architecture-gates-20261002`.
- **Structural Architecture Gates** : toujours nécessaires et à converger.
- **Remote MCP propriétaire** : toujours nécessaire comme track parallèle et future route distante prioritaire à coût incrémental nul lorsqu'il sera suffisamment mature.
- **Cognitive Memory Fabric** : toujours nécessaire, sans créer une deuxième mémoire concurrente.
- **Specialization Fabric 2D** : concept valide mais doit devenir récursif (livrable → archétype → module/sous-module → domaine → capacité).
- **Autonomy roadmap** : conservée uniquement comme sous-vue.
- **WfGg/Radar** : projets consommateurs/pilotes, pas la roadmap cœur de ChaCha DEV.

## Point critique découvert
La production active est `d84d389b...`, tandis que la branche de création actuelle `f3a7e86b...` diverge depuis `3d403f60...` et **n'est pas descendante de la production actuelle**. Toute suite doit donc commencer par une convergence de baseline ; aucune promotion du candidat actuel n'est admissible telle quelle.

## Vérifications ciblées
- Object Factory V7.7 : PASS.
- Human Conversation V8.1 : PASS.
- Capability atomic execution V8.21 : PASS.
- Domain execution continuation V8.28 : PASS.
- Architecture authority constitution/propagation : PASS.
- Ancien Domain Orchestration V6 : tests non intégralement PASS aujourd'hui (drift routage + contrat Guardian/Technology Watch), donc **MIGRATE**, pas suppression.
- Ancien Build Path V8.22 : comportement fail-closed conservé mais assertion historique `MISSING` vs `INVALID` devenue obsolète ; test à réaligner au contrat actuel.

## Règle de production
Les développements indépendants peuvent être parallélisés dans des worktrees/branches isolés. Les promotions production restent sérialisées, exact-SHA, avec réutilisation des preuves inchangées, Guardian/Sentinel, rollback et approbation humaine explicite.

Le détail machine-readable est `dev-hub/config/master-roadmap.v1.json`.
