# Portail WfGg v0.7.0 — cahier des charges exécuté

## Navigation
Après authentification, le portail ouvre toujours la page de garde : Guides / Train / Paramètres. Un profil incomplet affiche un rappel mais ne force plus l’ouverture des paramètres.

## Droits
- R4/R5 : paramètres complets, alliance, membres, rangs, fonctions R4, changement R5, réglages application.
- R1/R2/R3 : paramètres de leur propre profil uniquement.
- OWNER reste un rôle système séparé et protégé.
- Les droits sont vérifiés côté API. Les changements de rang/fonction invalident les sessions concernées.

## Membres
- Ergonomie issue de WfGg Train, palette violette du portail.
- Recherche compacte, sans grand cadre englobant.
- Filtres multi-sélection R5/R4/R3/R2/R1. Aucun filtre = tous ; TOUS réinitialise.
- Avatars carrés 1:1 : 90 photos historiques à correspondance certaine sont intégrées directement au portail ; les 9 correspondances non certaines restent en initiales.

## Paramètres transférés au portail
- Profil : pseudo, photo, langue, code et sessions.
- Alliance : identité, serveur, logo, membres, rangs, fonctions, leadership.
- Application : texte d’accueil, titres/URLs Guides et Train.
- Droits : matrice de politique et rôle courant.

Restent dans Train : heure/date d’ancrage, pools et ordre de rotation, overrides, indisponibilités, hors rotation, alertes Train, échanges, historique/statistiques de rotation.
