# WfGg — Last War LAB D1 setup

Cette procédure concerne uniquement le laboratoire Preview.

## Principe de sécurité

- Le portail Preview conserve l'authentification WfGg existante.
- Le Worker `wfgg-api-lastwar-preview` ne possède **aucun binding vers la D1 de production**.
- Pour valider le bearer token WfGg, le Worker appelle en lecture l'endpoint stable `https://wfgg-api.chachasan090375.workers.dev/api/me`.
- Toutes les écritures Last War vont exclusivement dans la D1 `wfgg-lastwar-lab` via le binding `LAB_DB`.
- Une déclaration d'UID est créée en `PENDING` et ne permet jamais de se connecter.

## Ressources à créer dans Cloudflare

1. D1 : `wfgg-lastwar-lab`.
2. Appliquer `worker/migrations/0003_external_identities.sql` à cette D1.
3. Worker Preview : `wfgg-api-lastwar-preview` avec `worker/src/index-lastwar-preview.js`.
4. Binding D1 du Worker : `LAB_DB` -> `wfgg-lastwar-lab`.
5. Variables :
   - `PORTAL_ORIGINS=https://portal-auth-mobile-debug-v24.wfgg.pages.dev`
   - `AUTH_API_BASE=https://wfgg-api.chachasan090375.workers.dev`

Le modèle de configuration est dans `worker/wrangler-lastwar-preview.example.jsonc`.

## Endpoints du laboratoire

- `GET /api/health`
- `GET /api/auth/providers`
- `GET /api/me/identities`
- `POST /api/me/identities/lastwar/claim`
- `DELETE /api/me/identities/lastwar/:id`

## Invariant

Ne jamais ajouter `wfgg-db` comme binding à ce Worker laboratoire. La production ne doit recevoir aucune écriture issue des tests Last War.
