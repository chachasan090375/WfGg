# Contrôles prioritaires de sécurité — candidat local

Statut : code local et tests ; non déployé et non attesté en production.
Base : ea50e45460236b011fda824fc561c2ebe8601234.

| Exigence | Mise en œuvre | Preuve locale |
|---|---|---|
| STOP absent, illisible ou invalide bloque | stop_state.inspect_stop retourne UNKNOWN ; les deux lecteurs centraux bloquent tout état différent de CLEAR | test_platform_safety_failures.py / StopTests |
| Toute étape approuvée en PRE tente POST, même sur échec | finally autour du sous-processus ; même action_id ; outcome SUCCESS/FAILED/TIMEOUT/ERROR transmis | ActionTests et GuardianEventTests |
| POST impossible ne donne jamais un retour de succès | GUARDIAN_POST_ACTION_UNCONFIRMED ; cause originale conservée | ActionTests |
| JSON PASS avec code d’erreur du client reste bloquant | Contrôle de client_returncode avant acceptation ; code conservé dans le verdict écrit | ProcessIntegrationTests |
| PASS accompagné d’une demande de remédiation ou de STOP bloque | Refus explicite de remediation_required et stop_recommended ; réponse JSON non objet enregistrée comme indisponible | ProcessIntegrationTests |
| Échec du Conseil ne revendique pas une décision finale | REPORT_DECISION sur outcome non SUCCESS | GuardianEventTests |
| Inventaire critique incomplet ne permet pas de lever un latch | Refus des réponses de 100 éléments ou plus et des éléments malformés ; comportement fail-closed existant | test_guardian_stop_latch_reconciliation.py |
| Pas de déploiement automatique | Tests ajoutés au workflow candidate-qualification-only, déclenché manuellement | Revue du workflow |

## Limites et décisions

Le lecteur STOP renvoie une information structurée CLEAR/ACTIVE/UNKNOWN. Les
interfaces booléennes existantes sont conservées : UNKNOWN se traduit par blocage.
Cela peut bloquer les parcours hors production qui supposaient un STOP absent
équivalent à false ; ces parcours doivent fournir un état explicite et isolé.

Le POST est tenté après chaque lancement approuvé par PRE, même si le démarrage
échoue. PRE refusé n’entraîne ni lancement ni POST. Aucun retry ou replay ajouté.
Un processus tué brutalement ne peut pas exécuter finally : les événements PRE,
POST et verdicts existants, puis la réconciliation gouvernée restent nécessaires.
Ce correctif ne garantit pas la livraison d’un POST quand Guardian est indisponible.

L’API actuelle ne pagine pas et limite à 100 éléments. Une liste de 100 peut être
complète ou tronquée : le candidat refuse de conclure qu’elle est complète.
C’est volontairement conservateur ; même 100 éléments non critiques exactement
maintiennent un blocage indéterminé. Pagination ou compte exhaustif des critiques
constitue une étape ultérieure. Un inventaire incomplet ne déclenche aucun reset.

Les fixtures ne représentent pas une attestation Guardian/Sentinelle runtime.
Le latch Guardian réel reste actif ; les anciennes remédiations ne sont ni
acquittées, ni rejouées, ni déclarées résolues. L’ancien MCP est inchangé.

## Suite

La validation de processus ajoute onze tests avec vrais enfants Python et
événements PRE/POST écrits sur disque. Le client Guardian reste une fixture locale
qui simule les décisions, sans connexion à une autorité. Ces tests ne couvrent
pas l’authentification réseau, les signatures ou les contrats effectivement
enregistrés en production. Le protocole MCP n’est pas impliqué dans cette livraison.

Revue du diff et qualification exacte du candidat, puis attestations des autorités
et autorisation explicite avant activation production. Conftest/OPA est un binaire
local isolé utilisé pour les preuves ; aucun service Prometheus/Grafana n’est
installé par ce changement ; le coffre Obsidian
et Antigravity ne sont pas modifiés. Cette note Markdown peut servir de première
matrice de traçabilité dans la future documentation reliée.
