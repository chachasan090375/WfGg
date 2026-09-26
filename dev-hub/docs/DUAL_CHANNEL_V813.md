# ChaCha DEV — Dual Channel V8.1.3

## Objectif

V8.1.3 sépare la conversation quotidienne du pipeline de création.

Le widget propose deux voies manuelles :
- 💬 ChaCha : discussion, mémoire, conseil et recherche locale en lecture seule.
- 🛠️ Créer : chaîne ChaCha DEV complète pour créer ou modifier.

Le choix manuel du canal est souverain.

## Canal Conversation

Le canal Conversation ne lance ni Functional Translator, ni pipeline Build.
Il utilise :
- Conversation Channel Router ;
- Conversation Advisory Bus ;
- Research Broker sur snapshot local ;
- Conversation Reasoner ;
- Human Context ;
- personas fictives du Centre Humain.

Une demande de création reçue dans ce canal renvoie BUILD_HANDOFF_REQUIRED.
Elle prépare une Creation Brief mais n'exécute rien avant le passage manuel sur 🛠️ Créer.

Le bouton Stop reste global.

## Recherche et conseil

Le Research Broker V8.1.3 lit uniquement le snapshot technologique déjà matérialisé.
Il ne déclenche aucun refresh et ne réalise aucun appel réseau.

La recherche web générale reste non branchée dans cette version.

L'Advisory Bus peut lire la mémoire centrale et le Centre Humain sans modifier ces sources.

## Conversation Reasoner

Un provider conversationnel n'est utilisé que lorsqu'une attestation zéro-coût valide existe.
Sans cette preuve, le canal Conversation reste disponible via un fallback local déterministe.

La persona de ChaCha est distincte du profil de l'utilisateur.
Les données démographiques déclarées par l'utilisateur ne deviennent pas automatiquement un style de persona.

## Gouvernance

Les composants Conversation possèdent des contrats Guardian statiques et sont instrumentés par l'assurance de release.
Le canal Conversation ne dépend pas d'un contrôle D1 temps réel à chaque message.

Le canal Build conserve intégralement Guardian, Sentinel, approvals, Scheduler, Run Controller et rollback.

## Qualification

Validé localement :
- routage manuel des deux canaux ;
- absence du pipeline Build dans Conversation ;
- handoff explicite vers Créer ;
- Advisory Bus en lecture seule ;
- Research Broker sans réseau ;
- zéro-cost gate ;
- persona conversationnelle ;
- Stop global ;
- rétrocompatibilité V7.30 ;
- régressions V8.1.0, V8.1.1 et V8.1.2 ;
- PILOT Direct Operator isolé sans cerveau Build ;
- dépense automatique : 0 €.
