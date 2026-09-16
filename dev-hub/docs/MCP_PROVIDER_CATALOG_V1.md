# ChaCha DEV HUB V5 — MCP Provider Catalog V1

## Objet

Le catalogue MCP étend le modèle Provider/Adapter du DEV HUB V5 sans créer de voie parallèle ni de privilège implicite.

Un provider présent dans `mcp-provider-catalog.v1.json` n'est **pas** autorisé à s'exécuter. Le catalogue décrit uniquement l'intention d'intégration, les risques, les capacités visées et les restrictions minimales.

## Règle fondamentale

Le chemin d'admission reste :

`CATALOG_ONLY -> DESIGNED -> CONTRACT_OK -> PILOT -> ENABLED`

Les étapes `DESIGNED -> CONTRACT_OK -> PILOT -> ENABLED` restent gouvernées par les contrats adapters existants du DEV HUB V5.

Aucun MCP ne bénéficie d'une exception au Run Controller, au Verification Broker, au Storage Governor, aux approvals ou aux règles de preuve.

## Vague 1

### GitHub

Décision : `ADOPT`

Le connecteur GitHub géré existant reste le chemin privilégié. Le catalogue MCP ne remplace pas automatiquement ce connecteur.

Usages :
- lecture de dépôts ;
- branches ;
- fichiers ;
- Pull Requests ;
- GitHub Actions ;
- artefacts.

Les écritures restent branch-scoped. Les changements conséquents restent soumis aux gates du DEV HUB.

### Cloudflare MCP

Décision : `ADOPT`, mais `CATALOG_ONLY` au départ.

Capacités visées :
- Workers ;
- Pages ;
- D1 ;
- R2 ;
- observabilité ;
- déploiements preview.

Interdictions initiales :
- aucun changement DNS automatique ;
- aucune suppression D1/R2 ;
- aucun secret manipulé par le catalogue ;
- aucun déploiement production sans approval explicite et evidence PASS.

### Playwright MCP

Décision : `ASSESS`.

Le DEV HUB possède déjà un runner Playwright de projet. Le MCP doit démontrer une valeur supplémentaire avant promotion : pilotage navigateur interactif, inspection structurée et recette agentique.

Le premier PILOT doit utiliser une cible preview/non-production et un compte de test.

### Chrome DevTools MCP

Décision : `ASSESS`.

Rôle : diagnostic navigateur complémentaire à Playwright :
- console ;
- réseau ;
- erreurs JavaScript ;
- performance ;
- inspection runtime.

Il ne doit pas devenir un chemin de déploiement ni un moyen de mutation de production.

## Vague 2

### Filesystem MCP

Décision : `ASSESS` avec risque `CRITICAL`.

Il est interdit d'exposer `/`.

Racines autorisées proposées :
- `/opt/chacha-dev/workspaces`
- `/opt/chacha-dev/adapters`
- `/opt/chacha-dev/evidence`

Le premier contrat doit être **read-only**. Toute permission d'écriture ultérieure doit être accordée par racine et passer le Storage Governor.

Racines explicitement interdites : `/`, `/etc`, `/root`, `/home`, `/var/lib`, `/opt/chacha-dev/secrets`.

### Context7 MCP

Décision : `ADOPT`.

Déjà représenté dans le DEV HUB V5 comme provider de documentation de librairies. Son rôle reste read-only.

Préférence : lorsqu'un fournisseur dispose d'une documentation officielle spécialisée et contrôlée, celle-ci peut être préférée à Context7.

### Sentry MCP

Décision : `ASSESS`.

Premier contrat : lecture seule des projets, événements, stacktraces et release health.

La mutation d'issues, la gestion de releases ou toute action corrective externe doivent faire l'objet d'un contrat séparé.

## Vague 3

### Exa MCP

Décision : `WATCH`.

Candidat pour recherche technique récente et résolution de bugs obscurs. Il ne fait pas partie du chemin critique initial.

### Firecrawl MCP

Décision : `WATCH`.

Candidat pour ingestion de documentation, extraction structurée et crawl contrôlé. À activer uniquement lorsqu'un projet en a un besoin explicite.

### Figma MCP

Décision : `WATCH`.

À utiliser lorsque Figma devient une source de vérité design d'un projet.

## Providers différés

### Vercel MCP

Décision : `DEFER`.

WfGg utilise actuellement Cloudflare. Vercel ne doit être admis que pour un projet qui choisit explicitement Vercel.

### Supabase MCP

Décision : `DEFER`.

WfGg utilise actuellement Cloudflare D1. Supabase/PostgreSQL sera réévalué uniquement pour un futur projet qui choisit cette stack.

## Contrat d'admission MCP

Avant de passer de `CATALOG_ONLY` à `DESIGNED`, un provider doit avoir :

1. un owner identifié ;
2. les capacités demandées ;
3. les scopes read/write séparés ;
4. le mode d'authentification sans secret en Git ;
5. un health probe fonctionnel ;
6. une stratégie de timeout ;
7. une stratégie de rollback/désactivation ;
8. une politique de redaction des preuves ;
9. un mapping vers `dispatch-envelope/v1` et `task-result/v1` ;
10. une preuve que le provider ne peut pas s'auto-promouvoir.

## Règles de sécurité

- `CATALOG_ONLY` signifie zéro exécution autorisée par le DEV HUB.
- Le catalogue ne contient jamais de valeur de secret.
- Les tokens/OAuth/API keys restent dans le mécanisme de secret externe du provider ou du runtime.
- Aucun provider producteur ne vérifie lui-même sa propre preuve.
- Toute action production reste explicitement approuvée.
- Toute capacité destructive doit être séparée d'une capacité read-only.
- Les actions filesystem doivent être limitées à des racines déclarées.
- Le Run Controller reste dispatch-only tant que la politique globale V5 ne l'autorise pas autrement.

## Ordre d'intégration proposé

1. GitHub — valider l'adapter managed connector existant.
2. Cloudflare — créer un contrat read/observability puis preview deploy.
3. Playwright MCP — contrat preview/test-account.
4. Chrome DevTools MCP — contrat diagnostic read-mostly.
5. Filesystem MCP — contrat read-only roots.
6. Context7 — formaliser l'adapter MCP générique read-only.
7. Sentry — contrat observability read-only.
8. Exa / Firecrawl / Figma — seulement selon besoin projet.

## Non-objectifs de cette première phase

Cette phase ne :
- connecte aucun nouveau compte ;
- ne crée aucun token ;
- ne déploie rien ;
- ne modifie pas WfGg production ;
- ne promeut aucun adapter ;
- ne change pas le statut `PILOT` de `http-smoke-adapter`.

Le prochain lot doit définir le **contrat MCP générique read-only** et choisir le premier provider à faire passer `CATALOG_ONLY -> DESIGNED`, sans perturber le travail parallèle `http-smoke PILOT -> ENABLED`.
