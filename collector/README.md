# WfGg Collector V1

Collector V1 is an isolated VPS-side cache for player data. It does not modify the production Radar branch or replace the current Radar binaries.

## Goals

- keep one local SQLite cache of player records;
- preserve a change-only observation history;
- expose a localhost-only API that Radar can query quickly;
- accept normalized player records from the existing READONLY scan path;
- never store or log Last War access tokens in Collector V1.

## Isolation

Branch: `collector-v1`

Runtime root: `/opt/wfgg-collector`

Service: `wfgg-collector.service`

The API binds only to `127.0.0.1:8790`. Collector V1 is therefore not publicly reachable unless another trusted WfGg component explicitly proxies it.

## Data model

SQLite stores the latest known player record plus an observation row only when the record changes. Initial fields are:

- UID;
- pseudo;
- server;
- alliance ID and tag;
- x/y coordinates;
- HQ level;
- power when available;
- first seen and last seen timestamps.

## API

- `GET /health`
- `GET /stats`
- `GET /player?q=<pseudo-or-uid>`
- `GET /search?q=<text>&limit=20`
- `POST /ingest`

`POST /ingest` accepts either one player object, `{ "players": [...] }`, or a JSON array of player objects.

## Helpers

- `install-from-termux.sh` installs the isolated VPS service.
- `query-from-termux.sh` queries the cache through SSH.
- `ingest-json-from-termux.sh` imports a JSON file through SSH without exposing the collector port.

## Deliberate V1 boundary

V1 is the storage/query layer first. It does not contain a server-wide autonomous player harvester and it does not keep Last War credentials. The next integration step is to feed successful READONLY Radar player results into `/ingest`, so each lookup automatically becomes reusable cached data. This lets us validate the cache/API independently before changing the live Radar scan path.
