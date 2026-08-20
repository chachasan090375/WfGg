# Architecture — WfGg Portal V0.2.0

```text
Joueur
  |
  v
WfGg Portal (Cloudflare Pages)
  |
  | HTTPS + Bearer session
  v
wfgg-api (Cloudflare Worker)
  |                         |
  v                         v
D1 wfgg-db       R2 wfgg-avatars

Dashboard
  |---- Train       -> wfgg-train-app.pages.dev   [inchangé]
  |---- Guides      -> wfgg-guides.pages.dev
  |---- Simulateur  -> URL autonome non confirmée
```

## Identité

Un joueur possède ses propres préférences : pseudo affiché, langue, avatar. Son rang appartient à son appartenance à l'alliance. Les informations globales (nom, serveur, logo) appartiennent à l'alliance.

## Rangs et permissions

| Rang | Profil | Modules | Onglet Alliance | Gestion R5 |
|---|---|---|---|---|
| R1 | oui | oui | non | non |
| R2 | oui | oui | non | non |
| R3 | oui | oui | non | non |
| R4 | oui | oui | oui | non |
| R5 | oui | oui | oui | oui |

L'onglet Alliance est masqué côté interface pour R1-R3, mais la sécurité ne repose pas sur ce masquage : toutes les routes d'administration vérifient le rang côté Worker.

## Première connexion

```text
Code 6 chiffres
      |
      v
Authentification Worker
      |
      v
Session persistante
      |
      v
Profil déjà complété ? -- non --> Paramètres / Mon profil obligatoire
      | oui                         |
      v                             v
Dashboard <------------------ Enregistrer profil
```

La photo est personnalisable mais n'est pas obligatoire. Le pseudo affiché et la langue doivent être enregistrés une première fois avant que Train/Guides puissent être ouverts depuis le nouveau portail.

## Future authentification inter-modules

Cette V0.2.0 ne prétend pas encore protéger les URLs directes des modules existants. Une phase SSO/jeton inter-modules devra être conçue plus tard, lorsque le portail autonome sera validé, sans casser Train.
