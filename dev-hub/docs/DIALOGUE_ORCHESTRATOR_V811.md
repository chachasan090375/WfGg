# ChaCha DEV — Dialogue Orchestrator V8.1.1

## Objectif

V8.1.1 ajoute une couche de dialogue naturelle au-dessus de la réponse déjà décidée par ChaCha DEV.

Le Dialogue Orchestrator n'est pas un nouveau cerveau central. Il ne décide pas quoi faire, ne modifie pas les statuts, ne change pas les approvals et ne possède aucune autorité d'exécution.

Son rôle est limité à la formulation humaine.

## Chaîne

Utilisateur
→ Direct Operator
→ cerveau central
→ conversation-interface-agent
→ Dialogue Orchestrator
→ réponse humaine
→ timeline

Le conversation-interface-agent produit toujours une réponse déterministe sûre.

Le Dialogue Orchestrator peut ensuite reformuler uniquement le message humain, lorsque son provider est autorisé.

## Provider conversationnel

Provider candidat :
- id : agy-gemini-conversation
- runtime : /usr/local/bin/agy-dev
- modèles candidats : Gemini Flash Low
- sandbox : oui
- outils : aucun

Le provider est remplaçable. Le contrat du Dialogue Orchestrator ne dépend pas d'un modèle particulier.

## Verrou économique

Aucun appel modèle externe n'est autorisé sans une attestation explicite :

chacha.dev/conversation-provider-zero-cost-attestation/v1

Pour un provider de classe quota, l'attestation doit confirmer :
- quota_available = true ;
- une date valid_until future ;
- automatic_external_spend_eur = 0.

En l'absence de cette preuve, le système reste en :

DETERMINISTIC_BASE_RESPONSE

et le provider n'est pas appelé.

Le simple fait qu'une clé API existe ou qu'un modèle soit disponible ne constitue pas une preuve de gratuité.

## Autorité

Les champs suivants sont toujours copiés depuis la réponse centrale :
- status ;
- next_action ;
- central_authority_preserved ;
- decision_modified.

Le modèle ne peut produire que le texte message.

Toute nouvelle donnée technique suspecte introduite par la reformulation, notamment une nouvelle version, un SHA, une URL, un chemin, un code interne ou un montant, entraîne le rejet de la reformulation et un retour immédiat à la réponse déterministe.

## Human Context

Le provider peut recevoir :
- prénom préféré ;
- tutoiement/vouvoiement ;
- langue(s) ;
- contexte culturel explicite ;
- contexte régional explicite ;
- registre ;
- directivité ;
- verbosité ;
- humour ;
- signaux d'interaction explicites et éphémères.

L'âge et le genre peuvent être conservés volontairement dans le profil utilisateur, mais V8.1.1 ne les utilise pas automatiquement pour choisir le style conversationnel. Cela évite qu'une préférence soit inventée à partir d'un groupe démographique.

Aucune inférence de culture, âge, genre ou personnalité à partir du nom, de la voix, de l'accent ou de la localisation.

## État V8.1.1

Implémenté :
- Dialogue Orchestrator ;
- provider interchangeable ;
- runtime agy-dev/Gemini contractuellement compatible ;
- sandbox sans outils ;
- zéro-cost gate fail-closed ;
- fallback déterministe ;
- contexte multi-tours borné ;
- contexte humain volontaire ;
- validation anti-invention de nouveaux identifiants techniques ;
- conservation stricte de status et next_action ;
- intégration Direct Operator ;
- diagnostics du mode de dialogue dans les détails techniques ;
- tests HTTP isolés ;
- coût automatique 0 €.

Non activé :
- appel Gemini réel en production.

Raison :
aucune attestation économique actuelle ne prouve encore que l'appel conversationnel supplémentaire est gratuit ou inclus.

## Étape suivante

Produire une preuve économique fiable pour un provider conversationnel, ou brancher un provider local/inclus attesté.

Une fois cette preuve disponible, aucun changement d'architecture n'est requis : V8.1.1 sait déjà passer automatiquement en MODEL_REPHRASE.
