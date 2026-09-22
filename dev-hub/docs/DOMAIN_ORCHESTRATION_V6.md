# ChaCha DEV V6 — Domain Orchestration Kernel

## But

ChaCha DEV V6 transforme une consigne fonctionnelle en travaux spécialisés sans imposer au Product Owner de choisir les technologies ou les agents.

Le noyau comprend :

1. **Core Orchestrator** — comprend la demande et la découpe ;
2. **Domain Orchestrators** — un orchestrateur par domaine métier/technique ;
3. **Provider Resolver** — choisit le meilleur provider selon compétence, santé, coût, preuve et Technology Radar ;
4. **Technology Radar transversal** — surveille tous les domaines et recommande les évolutions ;
5. **Run Controller / Gates / Evidence** — conservent la gouvernance déjà validée dans ChaCha DEV V5.

## Flux

```text
Consigne fonctionnelle
        |
        v
ChaCha Core Orchestrator
        |
        +--> Product
        +--> Development
        +--> Data / Backend
        +--> Documentation
        +--> UI / Layout
        +--> Graphics
        +--> Animation
        +--> Cybersecurity
        +--> QA
        +--> Platform / Release
        +--> Recovery
        +--> Knowledge / Research
                 |
                 v
        Domain Orchestrator
                 |
                 +--> Capability Registry
                 +--> Provider Health
                 +--> Provider Economics
                 +--> Technology Radar recommendations
                 |
                 v
           Best eligible provider
```

Un orchestrateur de domaine ne choisit jamais un fournisseur par nom en dur. Il demande un ensemble de capacités et fait résoudre les providers au moment de l'exécution.

## Branches logiques

Le mot *branche* désigne ici une branche d'orchestration logique, pas une branche Git permanente.

Les branches Git restent temporaires et servent au développement/qualification. Les branches logiques du noyau vivent dans `domain-orchestration.v1.json`.

### Product

Normalise le besoin, les règles métier et les critères d'acceptation.

### Development

Frontend, backend, services, intégrations et code.

### Data / Backend

Schémas, index, migrations, persistance, provenance et performances de requêtes.

### Documentation

Documentation technique et utilisateur, ADR et runbooks.

Outils gratuits par défaut : Context7 lorsqu'il est pertinent, Git, Markdown et Vale pour le lint de prose.

### UI / Layout

Mise en page, composants, responsive, accessibilité et régression visuelle.

Outils gratuits par défaut : Playwright, Chrome DevTools, Storybook, Lighthouse et axe-core.

### Graphics

Assets, textures, sprites, atlas, icônes, SVG et 3D.

Outils gratuits par défaut : Blender, Inkscape, ImageMagick et UnityPy.

La génération graphique par modèle payant n'est jamais automatique. Elle est un fallback humain ponctuel.

### Animation

Animation 2D/3D, transitions, timelines, VFX et médias.

Outils gratuits par défaut : Blender, FFmpeg, Lottie-web et UnityPy.

### Cybersecurity

SAST, dépendances, secrets, surface web et revue d'architecture.

Outils gratuits par défaut : Semgrep CE, Trivy, Gitleaks, OWASP ZAP, npm audit et pip-audit.

Les outils lourds comme ZAP sont déclenchés à la demande, pas en permanence sur le VPS 2 Go.

### QA

Tests unitaires, intégration, E2E, smoke, performance et non-régression.

### Platform / Release

CI, Cloudflare, VPS, services systemd, health, logs, déploiement et rollback.

### Recovery

Sauvegarde, restauration, RPO/RTO et exercices de reprise.

### Knowledge / Research

Collector Knowledge Engine, documentation officielle, recherche technologique et comparaison de solutions.

## Politique économique

Le mode normal est `ZERO_INCREMENTAL_COST_DEFAULT`.

Classes autorisées automatiquement :

- free ;
- owned ;
- local ;
- included ;
- quota uniquement tant qu'il s'agit d'un quota déjà disponible.

Un provider payant ou un dépassement de quota doit fournir :

- la raison pour laquelle les solutions gratuites sont insuffisantes ;
- une estimation du coût ;
- un identifiant d'approbation humaine.

Le coût automatique externe est donc **0 €**.

## Technology Radar transversal

Le Radar V2 surveille chaque domaine du noyau.

Dimensions minimales :

- releases ;
- capacités ;
- qualité et fiabilité ;
- sécurité ;
- breaking changes ;
- dépréciations ;
- licence ;
- prix et quotas ;
- besoins matériels ;
- compatibilité avec ChaCha DEV ;
- preuves de benchmark.

La collecte des faits doit être déterministe en priorité : releases GitHub, registres de paquets, documentation officielle, avis de sécurité et catalogues.

Un LLM peut aider à synthétiser les faits, mais n'est pas requis pour collecter les faits et n'est jamais une dépendance payante obligatoire.

Le Technology Radar écrit des recommandations, jamais des promotions automatiques.

## Questions simples

Une question mono-domaine n'ouvre pas un projet complet.

Exemple :

> « À quoi sert le champ totalNum ? »

Le Core Orchestrator route directement vers Knowledge / Research, qui peut interroger Collector Knowledge.

## Changements multi-domaines

Exemple :

> « Ajoute une nouvelle fiche joueur avec animation, nouvelle API et documentation. »

Le Core produit au minimum :

- Product ;
- Development ;
- Data / Backend ;
- UI / Layout ;
- Graphics/Animation si nécessaire ;
- QA ;
- Cybersecurity ;
- Documentation ;
- Platform / Release lorsque le changement doit être livré.

Les dépendances déterminent l'ordre, mais les lots indépendants peuvent s'exécuter en parallèle.

## Règle d'évolution

Aucun nouvel outil ne devient automatiquement le meilleur outil parce qu'il est nouveau.

Le cycle est :

`DISCOVER -> WATCH -> ASSESS -> PILOT -> RECOMMEND -> ADOPT`

avec preuves, coût, sécurité, compatibilité et rollback.
