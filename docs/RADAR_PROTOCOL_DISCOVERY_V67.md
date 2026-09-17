# Radar V6.7 — Protocol Discovery

## Findings proven from the current implementation

### 1. `*` was not a wildcard
Collector called `ScanPlayerRegion(..., "*", region)`, but the V3/V4 decoder accepted a decoded player only when the UID or pseudo exactly matched the query. Therefore a structurally valid player city could be decoded and still be discarded because no real player is named `*`.

V6.7 gives `*` one explicit meaning: Collector enumeration. It accepts only map objects already proven by the strict player-city decoder (kind 6 + UID + pseudo); it does not broaden decoding to arbitrary objects.

### 2. Region isolation was not physically selecting one origin
The connector exported `WFGG_COLLECTOR_ORIGIN_INDEX`, but the native V4 helper did not consume it. Every region call internally swept its own nine-origin list.

V6.7 makes the selector authoritative for Collector calls and maps the visible 1..9 regions row-major:

- R1 `(0,0)`
- R2 `(1000,0)`
- R3 `(2000,0)`
- R4 `(0,1000)`
- R5 `(1000,1000)` — centre
- R6 `(2000,1000)`
- R7 `(0,2000)`
- R8 `(1000,2000)`
- R9 `(2000,2000)`

Legacy targeted player search keeps the previous multi-origin behaviour when no region selector is supplied.

## Safe protocol telemetry
For each Collector region V6.7 exposes aggregate counters only:

`requests`, `packets`, `decodeErrors`, `blobs`, `protoValid`, `playerCities`, `detailParsed`, `uidPresent`, `namePresent`, `playersDecoded`, `queryMatches`, `readTimeouts`, plus the canonical origin coordinates and number accepted by Collector.

No raw packet, token, session JSON, credential, device identifier, payload transcript or raw stderr is exposed to the Radar UI.

## Decoder consistency fix
The production V3 patch established protobuf field 3 as the nested player detail for player-city tiles. The older V4 diagnostic observer still inspected field 10. V6.7 aligns diagnostics with the production decoder and reports it as `detail3_present`.

## Read-only boundary
V6.7 uses the existing `world.get.block` read-only map request and existing profile read path. It adds no game mutation command.

## Expected next live observation
A federated scan should now provide one diagnostic row per real origin and no longer show the generic player-card error for `@federated:<server>`.

The first live run will determine whether map responses contain:

1. no packets;
2. packets but no protobuf blobs;
3. valid protobuf map objects but no player-city kind 6 objects;
4. player-city objects that fail nested detail decoding;
5. valid player cities with UID/pseudo, which should now be enumerated and ingested.
