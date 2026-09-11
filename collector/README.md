# WfGg Collector V1

Collector V1 turns the current Last War READONLY scanner into a persistent VPS-side data agent.

## Goals

- keep Radar queries fast by querying a local database instead of reconnecting for every lookup;
- harvest player-base metadata from `world.get.block` in bulk using the existing audited native client;
- persist normalized observations in SQLite;
- expose a localhost-only API for Radar and diagnostics;
- never log or return Last War session secrets.

## Native bulk mode

The collector branch keeps the existing `--scan-player` entry point and reserves query `*` for a bounded live server harvest. In this mode:

- the native binary performs a fresh synthetic `world.get.block` sweep;
- every decoded player base (`f2=6`, player detail in `f3`) is accepted;
- results are deduplicated by UID/pseudo;
- per-player `get.user.info.multi` enrichment is skipped during the bulk pass so one harvest does not explode into thousands of RPCs;
- ordinary exact-name / exact-UID scans keep their previous behavior.

The bulk result already contains the map data available on the player-base tile: UID, pseudo, server, alliance, coordinates and HQ level. Profile enrichment (power, kills, SVIP, etc.) is intentionally a second-stage Collector task.

## Service layout

```text
/opt/wfgg-collector/
  bin/
    radar-native-collector
    wfgg_collector.py
  private/
    session.json              # mode 0600, never logged
  data/
    collector.db              # SQLite/WAL
  collector.env
```

The existing READONLY capture remains shared from:

```text
/opt/wfgg-radar/private/lastwar-native-capture.pcap
```

The collector does **not** replace the production Radar native binary.

## Local API

The service binds only to `127.0.0.1:8791`.

```text
GET  /health
GET  /stats
GET  /player?q=zazavibes
GET  /players?prefix=zaza&limit=50
POST /scan
```

`/player` accepts an exact pseudo (case-insensitive) or an exact game UID.

## Database

`players` stores the latest normalized state for each UID. `observations` keeps the historical map observations. `scans` records one row per collection cycle with only safe status/error metadata.

Reserved profile columns are already present for the next stage:

- `power`
- `army_power`
- `army_kill`
- `svip_level`
- `profile_updated_at`

## Safety boundary

Collector V1 is READONLY. It only requests data that the connected account can normally receive from the game server. It does not automate gameplay actions. Session/token/device material is never exposed through the API and is not written into the database.

## Branch isolation

Development lives on `radar-collector-v1`. The collector build publishes binaries back to that branch only. The production branch `radar-production-v1` is not modified by Collector V1 testing.
