# WfGg Radar — Server Explorer V5 validation

Date: 2026-09-12

## Result

Server Explorer V5 is validated against the control neighborhood 989–995.

Observed through `SERVER_EXPLORER_SENTINEL`:

- 989: ACCESSIBLE
- 990: ACCESSIBLE
- 991: ACCESSIBLE
- 992: ACCESSIBLE
- 993: ACCESSIBLE
- 994: ACCESSIBLE
- 995: ACCESSIBLE
- tested=7
- accessible=7

Protocol Sentinel confirmed for every tested server:

- `nativeStage=MAP_RETURN`
- `runError=false`
- `postLoginPacket=true`
- `postLoginDecodeOK=true`
- `postLoginDecodeFail=false`
- `initOK=true`
- `mapPacket=true`

Typical end-to-end probe latency after the V5 redirect/init fixes is about 1.1–1.2 seconds per server in the current one-process-per-server implementation.

`players=0` in these tests is not a server-emptiness result: V5 probe mode deliberately checks only a small central map window to prove a valid READONLY `world.get.block` round-trip.

## Validated architecture

The following chain is now proven end-to-end:

1. authenticated Last War login
2. `serverInfo` redirect handling when present
3. INIT reception and SFS decoding
4. explicit foreign `serverId` in READONLY `world.get.block`
5. valid map response on neighboring servers
6. result returned to Radar/Server Explorer

This proves that an authenticated session can read map data for a target `serverId` without moving the account to that server.

## Frozen fallback

Keep V5 as the diagnostic/fallback implementation. Broad Scan V4 remains preserved and must not be replaced by the next optimization.

## Next milestone — Server Explorer V6

V6 should stop relying on manual `@servers:` ranges and become an orchestrated discovery/collection engine.

Priorities:

1. **Single-session multi-server probing** — authenticate/INIT once, then reuse the live connection for many target `serverId` values instead of spawning one native process/login per server.
2. **Automatic server discovery** — bounded adaptive exploration, with explicit safety caps and resumable progress, rather than manual ranges.
3. **Collector ingestion** — when a server is confirmed accessible, allow full map collection modes to feed Collector.
4. **Global identity index** — continuously populate the pseudo ↔ UID aliases/index across discovered servers; preserve pseudo collisions as multiple candidates rather than overwriting.
5. **Ambiguous-pseudo UX** — Radar should return a candidate list (server, alliance, HQ/power when available, profile thumbnail when available) so the user can choose the intended UID.
6. **Sentinel orchestration** — retain stage-only diagnostics and per-server counters without logging tokens, credentials, raw profile payloads, or player-sensitive data.
7. **Fallback** — if V6 single-session mode fails, retain V5 one-process-per-server probing and Broad Scan V4 unchanged.

## Invariant

Do not treat `playersObserved=0` as `server unavailable`. Availability is determined by a valid map protocol round-trip (`mapPacket=true` / successful probe), not by whether the sampled map window happens to contain a player.
