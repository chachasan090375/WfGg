# WfGg — préparation authentification Last War v1

Statut : **Preview / laboratoire uniquement**. Aucun changement de production et aucun remplacement de l’authentification WfGg actuelle.

## Objectif

Permettre à terme le flux :

1. authentification vérifiée par Last War ;
2. résolution de l’identité Last War vers un `user_id` WfGg ;
3. création d’une session WfGg normale ;
4. réutilisation de cette session par le portail, Train, le simulateur et les futurs modules via `/api/me`.

Les modules n’ont donc pas besoin de connaître la méthode de connexion utilisée.

## Modèle d’identité externe

La migration `0003_external_identities.sql` ajoute une table générique `external_identities`.

Pour Last War :

- `provider = lastwar`
- `provider_subject` = UID joueur Last War
- `server_id` = serveur Last War
- `alliance_subject` = identifiant alliance Last War si disponible
- `status = PENDING | VERIFIED | REVOKED`
- `verification_source` = mécanisme ayant réellement vérifié l’identité
- `verified_at` / `last_verified_at` = dates de preuve

La contrainte `(provider, provider_subject, server_id)` garantit qu’un compte Last War vérifié ne puisse correspondre qu’à un seul compte WfGg.

## Règle de sécurité fondamentale

Une identité déclarée manuellement est enregistrée au statut `PENDING` et **ne doit jamais permettre de se connecter**.

Seule une preuve externe fiable pourra passer une identité à `VERIFIED`. La méthode de preuve n’est volontairement pas implémentée tant qu’aucun mécanisme Last War suffisamment fiable n’est retenu.

Aucun mot de passe Last War, cookie de session Last War ou secret du jeu ne doit être stocké dans WfGg.

## Contrat API préparé

Le module `worker/src/lastwar-identities.js` prépare :

- liste des identités externes de l’utilisateur ;
- déclaration d’un UID Last War au statut `PENDING` ;
- révocation d’une liaison ;
- annonce des capacités du provider avec `login_enabled: false` tant que la vérification n’existe pas.

Ces fonctions sont volontairement non branchées sur le Worker de production dans cette étape.

## Futur flux de connexion

Quand une méthode de vérification Last War sera disponible :

1. le portail démarre le challenge Last War ;
2. le backend valide la preuve ;
3. il cherche `external_identities` en statut `VERIFIED` ;
4. il récupère `user_id` ;
5. il crée exactement la même session WfGg que l’authentification actuelle ;
6. `/api/me` reste inchangé pour les modules.

## Compatibilité

Le code WfGg à 6 chiffres reste une méthode de secours. L’authentification Last War pourra être ajoutée sans migration des modules métiers.
