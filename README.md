# WfGg Portal — bootstrap V0.2.0

Premier socle autonome du Portail WfGg. Cette version est **source uniquement** : elle n'est pas déclarée déployée et ne modifie pas le module Train.

## Fonctionnel déjà codé

- code d'authentification WfGg à 6 chiffres obligatoire pour établir la première session ;
- session persistante (365 jours, invalidée par déconnexion, désactivation, changement de rang ou reset de code) ;
- onboarding obligatoire du profil avant l'ouverture des modules ;
- profil individuel : pseudo affiché, langue FR/IT/EN/ES, avatar ;
- alliance, serveur et rang visibles dans le profil ;
- rangs réels R1 / R2 / R3 / R4 / R5 ;
- onglet `Mon profil` pour tous ;
- onglet `Alliance` généré uniquement pour R4/R5 ;
- contrôles d'autorisation également appliqués côté Worker ;
- gestion R4/R5 des membres, rangs, activation et codes ;
- R5 requis pour créer/gérer un R5 ;
- garde-fou empêchant de supprimer/dégrader le dernier R5 actif ;
- limitation des essais de connexion : 5 échecs sur 15 minutes -> blocage 15 minutes ;
- stockage D1 indépendant du Train ;
- stockage d'avatars prévu dans R2 ;
- dashboard : Train, Guides, Simulateur (Simulateur volontairement sans URL autonome pour l'instant) ;
- interface responsive mobile + desktop dans l'identité violet/gris WfGg.

## Architecture cible de ce bootstrap

- dépôt prévu : `chachasan090375/WfGg` ;
- Pages prévu : `wfgg` -> `https://wfgg.pages.dev/` ;
- Worker prévu : `wfgg-api` ;
- D1 prévu : `wfgg-db` ;
- R2 prévu : `wfgg-avatars`.

Ces ressources ne sont **pas marquées comme créées** dans ce pack.

## Principe de données

- `users` : identité et préférences personnelles ;
- `memberships` : appartenance à l'alliance + rang R1-R5 ;
- `alliances` : paramètres communs de l'alliance ;
- `sessions` : sessions persistantes ;
- `audit_log` : traçabilité des actions sensibles ;
- `auth_attempts` : limitation des essais de connexion.

## Important : Train

Le bouton Train pointe encore vers `https://wfgg-train-app.pages.dev/`. Aucune ligne du projet Train n'est modifiée ici. Le retrait du portail historique contenu dans Train sera une phase ultérieure, après validation du nouveau Portail autonome.

## Validation locale du pack

```bash
node --check frontend/app.js
node --check worker/src/index.js
node scripts/preflight.mjs
```

La migration D1 peut également être validée avec SQLite ou via Wrangler/D1 avant déploiement.
