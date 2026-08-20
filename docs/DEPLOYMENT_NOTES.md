# Déploiement — non exécuté dans V0.2.0

## Ressources prévues

- Worker : `wfgg-api`
- D1 : `wfgg-db`
- R2 : `wfgg-avatars`
- Pages : `wfgg`
- URL Pages attendue : `https://wfgg.pages.dev/`

## Ordre recommandé

1. créer le dépôt `chachasan090375/WfGg` ;
2. dans `worker/`, installer Wrangler ;
3. déployer/provisionner D1 + R2 avec les bindings du `wrangler.jsonc` ;
4. appliquer `migrations/0001_initial.sql` à D1 ;
5. créer les secrets Worker `APP_SECRET` et `BOOTSTRAP_SECRET` ;
6. déployer le Worker ;
7. vérifier `/api/health` ;
8. créer/déployer Pages depuis le dossier `frontend/` ;
9. vérifier que `PORTAL_ORIGINS` et la CSP correspondent à l'URL Pages réelle ;
10. appeler une seule fois `/api/bootstrap` pour créer l'alliance et le premier R5 ;
11. tester un R1/R2/R3, un R4 et un R5 ;
12. ne toucher au portail historique de Train qu'après validation de cette nouvelle entrée autonome.

## Commandes Wrangler indicatives

```bash
cd worker
npm install
npx wrangler secret put APP_SECRET
npx wrangler secret put BOOTSTRAP_SECRET
npx wrangler deploy
npx wrangler d1 execute wfgg-db --remote --file=migrations/0001_initial.sql
```

Pour Pages en Direct Upload, Cloudflare accepte le dossier de fichiers statiques avec Wrangler ; le ZIP est réservé au glisser-déposer dans le dashboard.

```bash
npx wrangler pages deploy ../frontend --project-name=wfgg
```

Aucune de ces commandes n'est marquée comme exécutée dans ce pack.
