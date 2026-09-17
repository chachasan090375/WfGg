# Radar V6.9 — Native Profile Protocol

## Objective

V6.9 isolates the remaining Radar failure to the profile layer. The V6.7 map sweep is preserved unchanged. Profile enrichment no longer converts UID batches into the pseudo query `@profile:...` and no longer sends those values through the map/player search path.

## Native path

The connector still accepts profile batches through the existing `protocol.ProfileScanner` interface. `ScanProfiles` now calls a dedicated native helper mode:

`--scan-profiles UID1,UID2,...`

The native helper reuses only the previously captured read-only `get.user.info.multi` template. It refreshes the request id, forces `allServers=true`, replaces the captured `uids` value while preserving its wire representation, sends the request, and accepts only responses associated with `get.user.info.multi`.

## Progressive qualification

The runtime target after static qualification is deliberately progressive:

1. one known valid UID;
2. two UIDs;
3. five UIDs;
4. ten UIDs;
5. twenty-five UIDs;
6. fifty UIDs.

A larger batch is not considered validated until the preceding size resolves correctly. V6.8 adaptive isolation and its hard attempt budget remain in place as a safety net.

## Safe diagnostics

The native helper reports only aggregate profile diagnostics: requested count, packet count, decode-error count, matching-command count, resolved-profile count, and whether the `uids` field was actually replaced. Tokens, session material, raw packets and UID values are never placed in diagnostics or logs.

If no `get.user.info.multi` response is observed, the bridge returns `LASTWAR_PLAYER_PROFILE_RESPONSE_NOT_OBSERVED`. If the captured template does not expose a replaceable `uids` field, it returns `LASTWAR_PLAYER_PROFILE_UIDS_FIELD_NOT_FOUND`. These codes allow Collector to distinguish a transport/template fault from a legitimate partial profile response.

## Preservation boundary

V6.9 does not modify `world.get.block`, the nine-region sweep, V6.7 protocol discovery, V6.8 map-evidence preservation, D1 ingestion, authentication, Worker routes or the live UI. The qualification branch is `radar-v69-native-profiles`; no release binary is published and `radar-production-v1` remains untouched until an explicit production authorization.
