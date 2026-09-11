# WfGg Collector

Collector is the local player-cache and incremental map state service for WfGg Radar.

## Security boundary

Collector runs on the VPS and stores player/map state only. It does not persist Last War credentials. Authenticated Last War access is supplied transiently by the trusted executor path.

## Local service

- Root: `/opt/wfgg-collector`
- API: `127.0.0.1:8790`
- Database: `/opt/wfgg-collector/data/collector.db`
- Master snapshots: `/opt/wfgg-collector/data/masters`

## Master + increments

The first deployment creates a physical Master snapshot of the current Collector database. Later refreshes run as cycles. A cycle records only actual player-state deltas against its baseline.

Player identity is the Last War `game_uid`. Server, alliance, pseudo, coordinates, HQ and power are mutable properties.

Recognized changes include:

- `NEW`
- `SERVER_TRANSFER`
- `ALLIANCE_CHANGE`
- `PSEUDO_CHANGE`
- `RELOCATED`
- `HQ_CHANGE`
- `POWER_CHANGE`
- `UPDATED`

A player missing from a sweep is **not** removed, retired or marked inactive. The last known record is preserved indefinitely. This protects the cache from partial scans and from treating server transfers as deletions.

## Fresh search contract

The target UI contract is:

`Search click -> incremental refresh -> successful cycle -> local Collector lookup -> result`

Concurrent search refreshes must share one running cycle rather than launch duplicate scans.

## Sentinel

Sentinel supervises Collector health, binary integrity and queued enrichment. Sentinel remains credential-blind.
