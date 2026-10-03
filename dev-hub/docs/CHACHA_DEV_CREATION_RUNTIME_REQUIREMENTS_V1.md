# ChaCha DEV — Cahier des charges de la chaîne de création V1

## Objet
ChaCha DEV doit transformer une demande fonctionnelle, éventuellement accompagnée de fichiers, en un livrable réalisable, spécialisé, construit en parallèle lorsque les ressources le permettent, validé sur les systèmes cibles et restitué comme artefact versionné.

## Chaîne canonique
1. Cerveau central : compréhension fonctionnelle.
2. Infrastructure Feasibility Auditor : audit obligatoire de l'architecture disponible et verdict FIT / FIT_WITH_CONSTRAINTS / NOT_FIT.
3. Solution Composer : conception du produit, découpage en modules et sous-modules, interfaces, responsabilités, données et contraintes.
4. Recursive Specialization Fabric : reclassification possible à chaque nœud du projet.
5. Artifact Fabric : fichiers entrants/sortants persistants, versionnés, intègres et gouvernés.
6. Specialist Cell Resolver : composition des Têtes + Bras + spécialistes transversaux.
7. Capability/Component reuse gate : réutiliser avant de recréer.
8. Execution Planner : transforme le graphe de solution en graphe exécutable.
9. Resource-Aware Parallel Orchestrator : parallélise selon dépendances, contrats et ressources réelles.
10. Virtual Device & OS Lab : construit et valide sur les plateformes cibles appropriées.
11. Scheduler + Run Controller : exécution.
12. Intégration, Guardian, Sentinelle et livraison d'artefacts.

## Audit de faisabilité infrastructure
Aucune conception détaillée ne doit démarrer sans un audit de CPU, RAM, GPU, stockage, I/O, réseau, OS, runtimes, virtualisation, accès périphériques, disponibilité, sauvegarde/reprise et contraintes de coût. En cas de NOT_FIT, ChaCha DEV doit proposer une architecture cible minimale et une architecture recommandée, sans engager de dépense automatiquement.

## Conception récursive
Un projet peut contenir des modules de nature différente. Chaque module ou sous-module complexe peut être reclassifié comme un nouveau livrable spécialisé. La structure fonctionnelle est hiérarchique, mais les dépendances réelles sont représentées par un graphe afin d'éviter de dupliquer les composants partagés. Les contraintes globales sont héritées ; les contraintes locales les complètent.

## Multitâche
Le parallélisme n'est autorisé que lorsque les dépendances et les contrats d'interface le permettent. L'orchestrateur adapte le nombre de workers à la charge CPU/RAM/GPU/I/O/réseau, conserve une réserve de sécurité pour l'hôte, favorise le chemin critique, applique le backpressure et peut différer les tâches non critiques. L'objectif est de réduire le temps total du projet, pas de maximiser artificiellement le nombre de tâches simultanées.

## Artifact Fabric
Le chat et l'API ChaCha DEV doivent accepter et restituer des fichiers : documents, images, photos, vidéos, audio, code, archives, jeux de données, logs, binaires et configurations. Chaque artefact possède un identifiant, une version, un SHA-256, une provenance, un état de sécurité et un rattachement projet/conversation. Les gros fichiers sont référencés et lus par plages ou représentations dérivées plutôt que dupliqués dans chaque agent. Aucun fichier entrant n'est exécuté automatiquement.

## Virtual Device & OS Lab
Le laboratoire doit fournir des environnements reproductibles et versionnés pour Windows, Linux, Unix/FreeBSD, Android, iOS, macOS, Linux embarqué et runtimes Web. Les images de base sont immuables, vérifiées par checksum et combinées avec des overlays projet.

### Placement initial
- QNAP NAS : stockage des images, snapshots et artefacts ; VM x86 légères et environnements de compatibilité lorsque les ressources le permettent.
- VPS : builds Linux, conteneurs, services et tests headless légers.
- Runner Apple natif : obligatoire lorsqu'un projet exige build iOS/Xcode Simulator ou validation macOS native ; aucune dépense cloud automatique.
- Appareils physiques : utilisés lorsque la validation dépend réellement du matériel, des capteurs ou des performances réelles.

## Gouvernance
Guardian, Sentinelle, STOP, Universal Materialization Gate et Canonical Component Registry restent applicables. Aucune nouvelle spécialisation, VM, capacité, dépendance externe ou dépense ne gagne d'autorité du seul fait d'avoir été créée. Toute activation production reste séparée du travail de conception et de qualification.

## Continuité avec l'architecture historique
Ce cahier des charges **étend** la Reference Architecture V5 et ne la remplace pas. Manifest V3, les 18 domaines qualité, Capability Registry, Golden Paths, Lifecycle/Evidence, Object Factory, Foundries, UMG/CCR, Guardian, Sentinelle, Architecture Council, Technology Watch et les canaux Direct Operator/Conversation restent applicables selon l'audit de convergence. Les règles explicitement supersédées sont documentées dans `master-roadmap.v1.json`. La `autonomy-gap-roadmap.v1.json` est une vue dérivée et ne doit plus être utilisée comme backlog maître.

Aucun candidat issu de ce cahier des charges ne peut être promu s'il n'est pas reconstruit/convergé sur la production active la plus récente et requalifié pour le périmètre matériellement modifié.
