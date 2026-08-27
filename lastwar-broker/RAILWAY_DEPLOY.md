# WfGg Last War broker — Railway staging

Target branch: `connector-readonly-v1`

## Railway service

Create one persistent Railway service from GitHub repository `chachasan090375/WfGg`.

Settings:

- Branch: `connector-readonly-v1`
- Root Directory: `/lastwar-broker`
- Builder: Dockerfile auto-detection
- Replicas: 1
- Region: Europe West when available
- Healthcheck Path: `/ping`
- Public Networking: Generate Domain

Do not enable horizontal replicas: the public manager already contains an internal pool of isolated Last War child processes and owns transaction affinity.

## Railway variables

Required secret:

- `WFGG_BROKER_SHARED_SECRET` = a random value of at least 32 characters

Optional:

- `WFGG_BROKER_SLOTS=4` (default 4; raise later only after observing memory/traffic)

`PORT` is injected by Railway and must not be set manually.

## Cloudflare staging Worker variables

On `wfgg-api-staging`, configure:

- `LASTWAR_BROKER_URL` = the generated Railway HTTPS domain, without trailing slash
- `LASTWAR_BROKER_SHARED_SECRET` = exactly the same secret as Railway, stored as a secret

The Worker derives a separate per-user state key from the WfGg account. The Last War reconnect state returned by the broker is AES-GCM sealed before it is persisted in D1. The browser never receives the reconnect state or the shared broker secret.

## Health path

After both sides are configured:

- Broker: `GET /ping`
- WfGg staging: `GET /api/lastwar/health`

Expected WfGg health mode: `read-only`, `external: true`, with at least one healthy slot.
