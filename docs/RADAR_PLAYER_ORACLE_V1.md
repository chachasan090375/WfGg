# WfGg Radar — Player Oracle V1

Date: 2026-09-12
Branch: `radar-player-oracle-v1`
Frozen broad-scan reference: `radar-broadscan-v4-frozen-2026-09-12`
Frozen base commit: `0fca0a63b03c9c1d7efb136ccf0c559bd0cec0d2`

## Goal

Make individual player searches fast and precise without losing the existing Broad Scan capability.

The default targeted path becomes:

`pseudo -> Collector index -> stable game UID -> get.user.info.multi(allServers=true) -> normalized profile -> targeted location lookup if needed -> Broad Scan only as fallback`

The existing Collector V4 / map sweep remains available for discovery, background indexing and wide searches.

## Non-negotiable rules

1. `game_uid` is the canonical identity key.
2. Never overwrite an observed value with an AI guess.
3. Every decoded field keeps provenance, timestamp and confidence/status.
4. Raw unknown fields are retained in the schema inventory instead of discarded.
5. READONLY only. No gameplay mutation command is introduced.
6. Production `radar-production-v1` is not modified while Oracle V1 is under validation.
7. If targeted lookup cannot resolve a player, fall back to the frozen Broad Scan path.

## Layers

### 1. Resolver

Input can be pseudo or UID.

- Query Collector first.
- If a known row contains `game_uid`, use it immediately.
- If the UID is unknown, invoke Broad Scan discovery and then retry targeted lookup.

### 2. Direct Profile Decoder

Use the already validated Last War READONLY command `get.user.info.multi` with the target UID and `allServers=true`.

Known normalized fields currently include:

- game UID
- pseudo
- current/source server when present
- alliance id/tag
- HQ level
- power

The decoder must evolve toward a complete field inventory rather than a fixed small struct.

### 3. Schema Registry

Each observed scalar is represented as:

```json
{
  "path": "profile.currentServer",
  "value": "1004",
  "wireType": "string",
  "source": "get.user.info.multi",
  "status": "OBSERVED",
  "observedAt": "...",
  "decoderVersion": "player-oracle-v1"
}
```

Unknown fields are stored with their exact path and type. They are not promoted into canonical meaning until verified.

### 4. AI Analyst

The AI layer may:

- cluster unknown fields by behavior,
- compare multiple observations,
- propose candidate meanings,
- detect likely server/position/timestamp identifiers,
- recommend the next safe READONLY experiment,
- detect protocol/schema changes after Last War updates.

The AI layer may not:

- invent a value,
- silently rename a field as proven,
- issue a gameplay mutation,
- erase contradictory evidence.

Hypotheses use status `INFERRED` until a deterministic rule is validated. Deterministic observations remain `OBSERVED`/`PROVEN`.

### 5. Location Resolver

Order of operations:

1. inspect the direct profile response for explicit location fields,
2. inspect current/cross/source server fields,
3. use a targeted UID -> world point command if identified,
4. use `world.get.block` only as the final fallback.

Source server and observed current server/location must be stored separately so a temporary cross-server teleport is not confused with an account transfer.

### 6. Orchestrator

Targeted search policy:

1. resolve UID from Collector,
2. direct profile refresh,
3. merge sparse profile data without deleting last known X/Y,
4. attempt targeted location refresh,
5. if unresolved, launch Broad Scan fallback,
6. return one merged player card with per-field provenance and freshness.

## Phase 1 implementation

The first code change is intentionally small and reversible:

- before starting a nine-region map cycle, try `Collector -> UID -> ProfileScanner`;
- if the profile refresh succeeds, complete the search immediately;
- if it fails or the UID is unknown, continue through the current Broad Scan unchanged.

This gives an immediate speed improvement for already indexed players while preserving the validated V4 scanner as a safety net.

## Phase 2

Capture the complete `get.user.info.multi` response schema for a known UID and expose a redacted field inventory. Add the extensible decoder registry and provenance model.

## Phase 3

Identify and validate the most direct UID -> current location/server mechanism. Only after validation should the Radar UI display live cross-server location separately from home server.
