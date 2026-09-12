# WfGg Collector · Identity Index V1

## Goal

Make Collector the canonical identity directory for Player Oracle.

The stable identity is `game_uid`. A pseudo is only an alias: it can change and it can collide with another player's pseudo. Oracle must therefore resolve `pseudo -> UID candidate(s)` once, then use the UID for all direct Last War profile requests.

## Canonical route

1. User enters pseudo, UID, or pseudo + server.
2. Collector Identity Resolver searches `player_identity` and historical `player_aliases`.
3. If one current UID is unambiguous, return it immediately.
4. If several UIDs share the pseudo, use current server / alias history / freshness to disambiguate. Never silently merge two UIDs.
5. Player Oracle requests the Last War profile directly by UID.
6. Dynamic fields (power, alliance, current/cross server, coordinates, etc.) come from the decoded profile. Broad Scan V4 remains discovery + fallback + Decoder Lab ground truth.

## Data model

### player_identity

One canonical row per UID. This is the only identity table Oracle should trust for current identity resolution.

- `game_uid` — primary key, immutable identity.
- `current_pseudo` — latest observed pseudo.
- `pseudo_key` — normalized lookup key.
- `current_server_id` — latest identity-level server hint, not a permanent home server.
- `first_seen`, `last_seen` — evidence timestamps.
- `confidence` — observed / confirmed state.

### player_aliases

Historical support table. Many-to-many by design.

- one UID may have several pseudos over time;
- one pseudo may correspond to several UIDs;
- `is_current` marks the latest alias for each UID.

This prevents a rename from breaking future searches and prevents duplicate pseudos from being incorrectly merged.

### identity_coverage

Tracks which server/world scopes have actually been swept. We must not claim "all Last War players" until every accessible scope has a completed discovery pass.

## Population strategy

Broad Scan V4 becomes the discovery engine for the identity directory:

- every map observation containing UID + pseudo upserts `player_identity`;
- a pseudo change closes the previous current alias and opens/refreshes the new one;
- existing Collector rows are backfilled into the identity directory;
- later multi-server scanning expands coverage server by server;
- profile decoding enriches player data but never changes identity unless UID evidence supports it.

## Resolver rules

Priority:

- exact UID -> immediate;
- exact current pseudo with one UID -> immediate;
- exact current pseudo with multiple UIDs -> disambiguate with server/freshness;
- historical alias -> return candidate list, not an automatic merge;
- no candidate -> Broad Scan discovery fallback.

## Decoder Lab relationship

Identity Index answers **who is this?** Decoder Lab answers **what does Last War tell us about this UID?**

Once UID is resolved, Decoder Lab stores/compares the full safe profile payload, learns deterministic field mappings, and normalizes known fields such as current server, source server, cross-server, power, HQ, alliance, `x/y`, `pointId`, and `worldPos`.

Broad Scan remains frozen as fallback and as ground truth for validating coordinate decoding.

## V1 safety rules

- Never use pseudo as a primary key.
- Never overwrite one UID with another because their pseudos match.
- Never claim complete global coverage without `identity_coverage` evidence.
- Never store Last War access tokens or authentication secrets in identity/decoder tables.
- Keep Broad Scan V4 independently recoverable.
