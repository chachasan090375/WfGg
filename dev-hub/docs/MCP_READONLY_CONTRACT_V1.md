# ChaCha DEV HUB V5 — MCP Read-only Contract V1

## But

Ce contrat est le sas commun minimal pour tout MCP local ou distant avant l'autorisation de la moindre écriture.

Il ne connecte aucun provider et ne vaut pas promotion. Il définit les invariants qu'un adapter MCP doit respecter pour pouvoir prétendre à `CONTRACT_OK`.

## Baseline MCP

- version cible : `2026-07-28` ;
- découverte : `server/discover` ;
- outils : `tools/list` puis `tools/call` ;
- distant : Streamable HTTP ;
- local : `stdio` ;
- une compatibilité avec une version antérieure doit être explicite dans l'adapter du provider.

## Boundary DEV HUB

L'extérieur ne parle jamais directement au moteur d'orchestration.

Entrée adapter : `chacha.dev/dispatch-envelope/v1`.

Sortie adapter : `chacha.dev/task-result/v1`.

Le shell n'est pas utilisé comme couche de transport et tout résultat du provider est marqué `UNVERIFIED` jusqu'au passage du Verification Broker.

## Politique outils

Principe : **default DENY**.

Pour un provider sous contrat read-only :

- chaque outil autorisé doit appartenir à une allowlist explicite du provider ;
- un outil inconnu est refusé ;
- un outil de mutation est refusé ;
- un outil destructif est refusé ;
- un outil dont le caractère read-only est ambigu est refusé ;
- une mutation de production est toujours refusée par ce contrat ;
- les annotations ou métadonnées du provider sont informatives mais ne remplacent pas notre propre allowlist.

Une capacité d'écriture future exige un **contrat séparé** et ne doit jamais être ajoutée implicitement au contrat read-only.

## Authentification et secrets

Le contrat ne stocke aucune valeur de secret dans Git.

Selon le provider, l'identité peut être fournie par OAuth externe, secret store externe ou référence opaque. Les en-têtes d'autorisation sont redacted dans les preuves et les credentials ne doivent jamais être reflétés dans un `task-result`.

## Santé

Avant exécution :

1. `server/discover` doit réussir ;
2. `tools/list` doit réussir ;
3. le snapshot de santé doit dater de 300 secondes maximum ;
4. le probe expire après 10 secondes ;
5. un échec place le provider en `UNAVAILABLE`.

## Bornes d'exécution

- durée maximale d'un appel : 30 secondes ;
- taille maximale du résultat brut accepté : 2 Mio ;
- au-delà, l'adapter doit échouer proprement et produire une preuve structurée sans données sensibles.

## Evidence et vérification

Un provider ne peut jamais certifier lui-même que sa propre sortie est correcte.

Les preuves doivent enregistrer au minimum :
- provider ;
- outil appelé ;
- version protocolaire ;
- timestamp ;
- état du health probe ;
- résultat structuré ;
- informations de redaction.

Le verdict appartient au `verification-broker`.

## Rollback

Le rollback minimum d'un MCP admis est `DISABLED`.

La désactivation doit :
- fonctionner même si le provider est indisponible ;
- ne pas dépendre d'une rotation de secret ;
- couper le dispatch avant toute autre action de nettoyage.

## Relation avec le lifecycle

`CATALOG_ONLY -> DESIGNED` signifie que le provider possède une définition suffisamment précise pour construire son adapter.

`DESIGNED -> CONTRACT_OK` exige ensuite une exécution du contract harness spécifique au provider et une preuve indépendante.

Ce fichier ne fait passer **aucun provider** à `CONTRACT_OK`, `PILOT` ou `ENABLED`.

## Premier usage prévu

Le contrat servira d'abord à formaliser une intégration read-only à faible risque, puis aux volets lecture/observabilité des providers plus puissants comme Cloudflare.

Pour Cloudflare, les capacités de déploiement, modification Worker/D1/R2, DNS ou secrets devront rester hors de ce contrat et disposer chacune de gates supplémentaires.
