# Server Explorer — diagnostic INIT V3

## Verdict Sentinel

Le témoin serveur 992 atteint `LOGIN_OK` mais ne reçoit pas l'INIT dans la fenêtre du connecteur. Augmenter simplement le timeout n'est pas la bonne correction.

## Différence avec le client Last War de référence

Le client `ljagiello/lastwar-client` ne se contente pas d'attendre passivement le push `init`. Son `waitForInitPush` coupe la fenêtre en deux et, si le push n'est pas arrivé à mi-parcours, envoie la commande READONLY `login.init` avec `_id=2` et `dataConfigMd5=""` afin de déclencher le bootstrap.

Notre helper natif WfGg attend actuellement `init` passivement après `LOGIN_OK` et ne possède pas ce fallback. Cela explique le chemin Sentinel observé : `LOGIN_OK -> attente INIT -> timeout`.

## Correction cible

Avant de poursuivre les probes multi-serveurs :

1. conserver le serveur 992 comme témoin obligatoire ;
2. aligner le bootstrap du helper natif sur `waitForInitPush` du client de référence ;
3. n'envoyer `login.init` qu'après un délai borné si le push passif n'est pas arrivé ;
4. tracer uniquement les étapes Sentinel, sans token, UID, pseudo ni contenu de fiche ;
5. ne lancer `world.get.block` qu'après `INIT_OK` ;
6. ne tester les serveurs voisins qu'une fois 992 validé.

Broad Scan V4, Identity Index et Player Oracle restent inchangés pendant cette correction.
