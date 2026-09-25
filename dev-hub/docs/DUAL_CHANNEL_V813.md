# ChaCha DEV — Dual Channel V8.1.3

## Objectif

V8.1.3 sépare la conversation quotidienne du pipeline lourd de création.

Le widget expose deux canaux partageant le même fil, le même profil humain et les mêmes personas :

- 💬 ChaCha
- 🛠️ Créer

Le switch manuel est souverain.

## Canal 💬 ChaCha

Le canal Conversation est conçu pour :
- discuter ;
- répondre à des questions ;
- consulter la mémoire centrale ;
- exploiter le Centre Humain en lecture ;
- consulter les connaissances technologiques déjà matérialisées ;
- préparer une demande de création sans l'exécuter.

Il ne passe pas par :
- Functional Translator ;
- Central Build Orchestrator ;
- Scheduler ;
- Run Controller ;
- Foundries.

Il ne possède aucune autorité de mutation.

Si une demande ressemble à une action de création ou de modification, le routeur renvoie :

BUILD_HANDOFF_REQUIRED

avec une Creation Brief.

Le widget propose ensuite de passer manuellement à 🛠️ Créer. La demande est remise dans la zone de saisie mais rien n'est envoyé automatiquement.

## Canal 🛠️ Créer

Le canal Build conserve le pipeline ChaCha DEV existant et toute sa gouvernance.

Il continue à utiliser les garde-fous existants :
- Guardian ;
- Sentinel ;
- approvals ;
- Scheduler ;
- Run Controller ;
- Foundries ;
- rollback et preuves.

V8.1.3 ne réduit aucune de ces protections.

## Advisory Bus

Le Conversation Advisory Bus expose des vues READ-ONLY :
- mémoire centrale ;
- état documentaire du Centre Humain ;
- résultat du Research Broker.

Les données sont consultatives uniquement.

Le bus ne peut pas appeler Scheduler, Run Controller ou une Foundry.

## Research Broker

Technology Watch est actuellement gouverné par Guardian, y compris pour certains appels consult.

Pour éviter de rendre la conversation dépendante de D1 sans contourner Guardian, le Research Broker lit uniquement le snapshot déjà matérialisé :

/opt/chacha-dev/runtime/technology-watch/optimizer-input.json

Il ne déclenche pas de refresh.

Il ne fait aucun appel réseau.

La recherche web générale reste explicitement :

UNBOUND

Elle sera ajoutée ultérieurement derrière un provider de recherche read-only avec provenance des sources et garde économique.

## Conversation Reasoner

Le Conversation Reasoner peut exploiter :
- message utilisateur ;
- historique récent ;
- profil conversationnel autorisé ;
- persona fictive de ChaCha ;
- Advisory Brief ;
- Research Brief.

Il n'a aucun outil d'exécution.

Son provider candidat est agy-gemini-conversation.

Comme V8.1.1, aucun modèle externe n'est appelé sans attestation zéro-coût valide.

Sans attestation, la conversation reste disponible via un fallback déterministe read-only.

## Séparation utilisateur / persona

L'âge et le genre éventuellement déclarés par l'utilisateur ne sont pas transmis comme instructions de style au Conversation Reasoner.

La persona de ChaCha est distincte et peut, elle, définir explicitement :
- âge fictif ;
- genre de présentation ;
- région ;
- culture ;
- milieu social ;
- sociolecte ;
- tempérament ;
- réactions ;
- humour.

## Continuité de session

Conversation et Build partagent la timeline mais possèdent des pointeurs de reprise distincts.

Les échanges Conversation mettent à jour :
- last_conversation_request_id ;
- last_conversation_response.

Ils ne modifient jamais :
- last_response_path ;
- last_response_digest ;
- le pointeur Build utilisé par Continue / Go.

Un PILOT a confirmé qu'une série de conversations laisse le pointeur Build bit-for-bit inchangé.

## Stop

Stop reste global.

Même si le widget est sur 💬 ChaCha, le bouton Stop est envoyé au chemin de contrôle Build afin de conserver la capacité d'arrêt d'urgence.

## Gouvernance

Nouveaux rôles Guardian :
- role:conversation-channel-router
- role:conversation-advisory-bus
- role:conversation-reasoner
- role:research-broker

Tous interdisent notamment :
- mutation projet ;
- déploiement production ;
- Scheduler ;
- Run Controller ;
- Foundry ;
- extension de permissions ;
- auto-switch vers Build ;
- upgrade payant automatique.

Research Broker interdit également :
- NETWORK_RESEARCH
- REFRESH_TECHNOLOGY_WATCH

dans cette version.

## État V8.1.3

Implémenté :
- switch 💬 ChaCha / 🛠️ Créer ;
- Conversation par défaut dans la nouvelle UI ;
- API rétrocompatible BUILD par défaut ;
- idempotence isolée par canal ;
- routeur léger ;
- Creation Brief ;
- Advisory Bus READ-ONLY ;
- Research Broker sur snapshot local ;
- Conversation Reasoner ;
- zéro-cost gate ;
- persona sur canal Conversation ;
- timeline partagée ;
- continuité Build préservée ;
- Stop global ;
- contrats Guardian ;
- instrumentation d'assurance ;
- PILOT HTTP sans Guardian ;
- dépense automatique 0 €.

Non implémenté :
- recherche web générale ;
- TTS ;
- conversation vocale continue ;
- barge-in.

Ces fonctions viendront dans les versions suivantes.
