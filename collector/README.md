# WfGg Collector V1

Collector V1 is an isolated VPS-side cache for player lookups. It is built on the existing READONLY Last War native client and does not modify the production Radar branch.

## Goals

- keep one local cache of player records in SQLite;
- refresh only player names or UIDs explicitly added to the watch list;
- expose a localhost-only HTTP API for Radar and diagnostic tools;
- make profile enrichment best-effort so a profile lookup failure never discards a valid map hit;
- never print the access token or session contents.

## Isolation

Branch: `collector-v1`

Runtime root: `/opt/wfgg-collector`

The agent uses its own copy of the native binary. It does not replace `/opt/wfgg-radar/bin/radar-native-template` and therefore cannot change the current Radar service while Collector V1 is being tested.

## Data model

SQLite stores the latest player record plus a change-only observation history. Initial fields are the ones already decoded from player-base tiles and profiles: UID, pseudo, server, alliance, coordinates, HQ level, power, first seen and last seen.

## API

The service binds only to `127.0.0.1:8790`.

- `GET /health`
- `GET /stats`
- `GET /player?q=<pseudo-or-uid>`
- `GET /search?q=<text>&limit=20`
- `POST /watch?q=<pseudo-or-uid>`
- `DELETE /watch?q=<pseudo-or-uid>`

Only watch-list entries are refreshed automatically. This keeps the collector bounded and avoids turning the service into a bulk player-harvesting scanner.

## Session handling

Autonomous operation requires a Last War session on the VPS. The installer places it in `/opt/wfgg-collector/private/session.json`, owned by the service account and mode `0600`. The agent never returns or logs its contents.

V1 deliberately favors a small, auditable cache and reliable player retrieval. A later version can ingest additional events the connected client already receives without changing the public Radar API.
