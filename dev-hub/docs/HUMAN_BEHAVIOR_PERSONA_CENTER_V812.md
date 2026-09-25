# ChaCha DEV — Human Behavior & Persona Center V8.1.2

## Rôle

Le Centre Humain / Émotionnel / Personas est un composant documentaire et créatif du noyau ChaCha DEV.

Il a quatre fonctions :
1. Observer et documenter des comportements humains sous forme d'observations dérivées et sourcées.
2. Comparer les observations sans transformer des tendances en règles absolues.
3. Construire des personas fictives et des archétypes volontairement typés pour la conversation, les avatars et la création.
4. Apprendre progressivement des retours d'usage en produisant des deltas incrémentaux vers la mémoire centrale.

Il n'a aucune autorité technique, d'architecture, d'exécution ou de production.

## Sources

Les sources sont classées et pondérées.

Exemples :
- recherche évaluée par les pairs ;
- ouvrages académiques ;
- enquêtes ;
- documentaires et entretiens ;
- vidéos publiques ;
- représentations sur les réseaux sociaux ;
- films, séries et littérature ;
- retours d'usage sur une persona.

Chaque observation porte :
- sa provenance ;
- son type de source ;
- son domaine comportemental ;
- son contexte ;
- ses facettes ;
- sa confiance ;
- son périmètre de preuve.

## Séparation des niveaux de preuve

EMPIRICAL_HINT
: résultat utilisable comme indice empirique contextualisé.

CONTEXTUAL_OBSERVATION
: comportement observé dans un contexte donné, sans généralisation de population.

REPRESENTATION_ONLY
: façon dont une personne ou un milieu est représenté dans une œuvre de fiction ou un média narratif.

PERSONA_FEEDBACK
: retour d'usage sur l'effet produit par une persona.

Une œuvre de fiction ne peut jamais être promue automatiquement en vérité empirique.

Les contradictions sont conservées. Le Centre Humain n'est pas chargé de fabriquer une moyenne artificielle entre des sources divergentes.

## Personas et stéréotypes créatifs

Le mode Persona est explicitement :

FICTIONAL_ARCHETYPE

Une persona peut inclure :
- genre de présentation ;
- tranche d'âge ;
- région ;
- culture ;
- milieu social ;
- époque ;
- formation ;
- métier ;
- langues ;
- sociolecte ;
- tempérament ;
- valeurs ;
- style de langage ;
- notes créatives.

Le paramètre stereotype_intensity va de 0 à 3.

0
: les observations sont consultables mais aucune force caricaturale n'est appliquée.

1
: légère coloration.

2
: archétype marqué.

3
: persona volontairement typée / caricaturale pour un usage créatif.

Cette intensité est un contrôle de création, pas une probabilité statistique sur une personne réelle.

## Exemple d'usage

Une persona fictive peut être spécifiée comme :
- femme ;
- 35 ans ;
- Paris XVIe ;
- milieu BCBG ;
- français ;
- tempérament maîtrisé ;
- formulation soignée ;
- ironie légère.

Le Centre recherche les observations compatibles et construit une persona-card.

Les observations normandes, provençales ou appartenant à une tranche d'âge incompatible ne sont pas utilisées simplement parce qu'une autre caractéristique correspond.

## Dialogue Orchestrator

V8.1.2 ajoute SPEAKER_PERSONA au Dialogue Orchestrator.

La persona peut influencer :
- langage ;
- sociolecte ;
- humour ;
- expression émotionnelle ;
- style social ;
- façon de réagir.

Elle ne peut jamais influencer :
- status ;
- next_action ;
- faits techniques ;
- approvals ;
- autorité ;
- niveau d'incertitude de la décision centrale.

## Direct Operator

Le profil utilisateur possède maintenant une préférence distincte :

assistant_persona_id

Cette valeur décrit qui ChaCha doit incarner, pas qui est l'utilisateur.

L'API expose :
- GET /api/v1/personas ;
- GET/POST /api/v1/human-profile.

Le widget dispose d'un sélecteur « Persona de ChaCha ».

## Apprentissage

Le Centre conserve :
- observations documentaires ;
- retours sur les personas.

Il peut produire :

chacha.dev/human-behavior-evidence-delta/v1

vers la mémoire centrale.

Les deltas ne demandent jamais eux-mêmes :
- modification de politique ;
- extension de permission ;
- nouvelle autorité.

Tout changement matériel reste soumis aux mécanismes Guardian / Sentinel existants.

## Médias, vidéos et films

Le contrat prévoit l'analyse future de vidéos, interviews et films.

Le Centre stocke :
- observations dérivées ;
- provenance ;
- contexte ;
- confiance.

Il ne stocke pas automatiquement :
- fichiers vidéo complets ;
- audio complet ;
- films complets ;
- transcriptions intégrales protégées.

## Gouvernance

Contrat Guardian :
role:human-behavior-center

Actions permises :
- lire les preuves dérivées ;
- ingérer une observation dérivée ;
- synthétiser une persona fictive ;
- enregistrer un retour de persona ;
- émettre un delta d'apprentissage.

Actions interdites notamment :
- inférer des caractéristiques protégées d'une personne réelle ;
- diagnostiquer son état mental ;
- transformer une fiction en vérité de population ;
- modifier une application ;
- déployer en production ;
- étendre ses permissions ;
- modifier son propre contrat ;
- engager une dépense payante automatique.

## État V8.1.2

Implémenté :
- base documentaire SQLite ;
- ingestion idempotente avec provenance ;
- pondération des classes de sources ;
- conservation des contradictions ;
- filtrage de compatibilité des facettes ;
- synthèse de personas fictives ;
- intensité créative 0–3 ;
- feedback persona ;
- learning delta ;
- contrat Guardian ;
- instrumentation d'assurance ;
- universal learning uplink ;
- intégration Dialogue Orchestrator ;
- catalogue de personas ;
- sélection dans le widget ;
- PILOT HTTP complet ;
- coût automatique 0 €.
