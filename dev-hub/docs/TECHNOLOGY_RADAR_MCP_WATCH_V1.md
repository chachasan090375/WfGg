# ChaCha DEV HUB V5 — Technology Radar MCP Watch V1

## Objet

Le `technology-radar-agent` surveille automatiquement l'écosystème MCP utilisé ou évalué par le DEV HUB.

Le catalogue `dev-hub/config/mcp-provider-catalog.v1.json` est la source d'inventaire. Le mode `DYNAMIC_ALL_PROVIDERS` signifie qu'un provider ajouté au catalogue entre automatiquement dans le périmètre de veille, quel que soit son statut (`ADOPT`, `ASSESS`, `WATCH`, `DEFER`, `REJECT`) ou son état runtime.

Aucune liste manuelle de providers n'est maintenue en parallèle.

## Deux niveaux de veille

### 1. Protocole MCP

Le Radar surveille la spécification MCP elle-même :
- nouvelles révisions de spécification ;
- breaking changes ;
- transports ;
- extensions ;
- SDK et guides de migration ;
- authentification / autorisation ;
- dépréciations ;
- changements de sécurité.

Baseline actuelle : `2026-07-28`.

Sources canoniques prioritaires :
- `https://modelcontextprotocol.io`
- `https://blog.modelcontextprotocol.io`

Une évolution de protocole ne modifie jamais automatiquement les contrats du DEV HUB. Elle produit une analyse d'impact et, si nécessaire, une proposition de migration.

### 2. Providers / connecteurs

Chaque provider du catalogue est suivi sur les dimensions suivantes :
- release ;
- nouvelles capacités et nouveaux outils ;
- API ;
- breaking changes ;
- dépréciations ;
- authentification et autorisation ;
- avis de sécurité ;
- SDK ;
- transports ;
- quotas / limites ;
- modèle tarifaire ;
- état de service ;
- compatibilité avec le DEV HUB.

Le Radar peut également détecter de nouveaux providers MCP non encore catalogués. Ils restent de simples candidats tant qu'une décision humaine / architecturale ne les ajoute pas au catalogue.

## Gouvernance

Le Radar est un système de veille et de recommandation, pas un moteur de promotion.

Il ne peut pas :
- modifier le catalogue ;
- changer le statut runtime d'un provider ;
- promouvoir un adapter ;
- modifier la production ;
- contourner les gates du DEV HUB.

Les recommandations doivent être sourcées et accompagnées d'evidence.

Tout changement de décision catalogue nécessite une validation humaine.

Une évolution de sécurité déclenche une revue `security-reviewer`.
Une évolution de protocole ou transport déclenche une revue `platform-cloud-engineer`.

## Analyse d'impact

Chaque découverte est comparée au minimum contre :
- MCP Provider Catalog ;
- MCP Read-only Contract ;
- Provider Adapters ;
- Provider Health Probes ;
- Capability Registry ;
- Agent Routing.

Classification d'impact :

`NO_IMPACT | DOC_ONLY | RETEST | RECONTRACT | SECURITY_REVIEW | MIGRATION_REQUIRED | DEPRECATE_PROVIDER`

## Alertes

Revue immédiate :
- breaking change protocolaire ;
- alerte sécurité critique ;
- rupture d'authentification ;
- dépréciation d'un provider ;
- dépréciation d'un transport.

Revue standard :
- nouvelle release ;
- nouvelle capacité ;
- nouvel outil ;
- release majeure SDK ;
- changement quota ;
- changement tarifaire.

## Planification

Le watch MCP hérite de la planification du Technology Radar existant. Ce lot ne crée pas un second scheduler indépendant.

## Garantie CI

`technology-radar-mcp-watch-validate.py` garantit notamment :
- inventaire dynamique de tous les providers ;
- aucune exclusion ;
- couverture de tous les statuts présents dans le catalogue ;
- veille protocole active ;
- recommandations uniquement ;
- aucune mutation/promotion/production ;
- capacités et mots-clés de routage présents dans `agent-routing.v1.json`.

Ainsi, l'ajout futur d'un provider au catalogue ne peut pas silencieusement sortir du périmètre de veille.
