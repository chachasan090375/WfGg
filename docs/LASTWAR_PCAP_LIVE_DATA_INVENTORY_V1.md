# WfGg — Last War live PCAP data inventory v1

Status: **laboratory only** (`portal-auth-lastwar-lab-v1`).

This note records what was confirmed from a real Android Last War login capture on 2026-08-28. It deliberately contains **no access token, device identifier, anti-fraud fingerprint, e-mail address, player UID, player name, alliance identifier, or other account credential/PII value**.

## Capture quality

The capture contained:

- the native Android package `com.fun.lastwar.gp`;
- a full SFS2X game login request;
- a successful game login response;
- the authoritative `init` bootstrap push;
- the normal burst of automatic post-login read requests/responses.

The captured native client identified itself as app version `1.0.359`, build/version code `1864`.

The game socket was plain SFS2X TCP on the account's zone-specific port. The login request carried all fields required by the existing upstream cross-server/session-config path: zone, gameUid, deviceId, shumeiBoxId, access token and platform identity.

## Authoritative `init` payload

The captured `init` object contained **246 top-level fields**. Important WfGg-relevant domains confirmed present include:

### Player/profile

`playerInfo` contains a detailed power breakdown and progression data, including fields such as:

- hero power
- army power
- building power
- science power
- squad equipment power
- battle-card power
- dominator power
- decoration power
- max/overall power-related fields
- stamina/PVE progression
- army kills and battle counters

`user` contains profile/account metadata including server, level, registration/open-server metadata, alliance ID, career data, profile picture/version data, country/locale-related fields and account-binding state. Sensitive fields that can also appear in this object must not be persisted wholesale by WfGg.

### Heroes

`userHero` contained **31 hero records** in this capture.

Each hero record exposes fields including:

- `heroId`
- stable hero instance `uuid`
- level (`lev`)
- rank (`rankLv`)
- awakening level (`awakenLv`)
- skin ID
- skill data
- weapon information
- effect/state information

This is sufficient to build a roster model once numeric hero IDs are joined to the game's static hero catalog.

### Formations / squads

The bootstrap contained:

- **3** `army_formation` records;
- **12** `formation_template` records;
- scout/defence/battlefield formation containers.

Formation records map slot/index positions to hero instance UUIDs and include squad index, slot count, formation state and chip-equipment-group information. This creates a direct join from current squads to `userHero`.

### Hero equipment and weapons

The capture contained:

- **180** hero-equipment records under `heroEquips.list`;
- **6** general `equipList` records;
- at least **1** weapon record under `weaponArr`.

Hero-equipment records expose equipment config ID, equipment UID, level, promotion and owning hero UID. Weapon records expose level, power, experience, chip level/experience, skills and properties.

This is directly relevant to a future WfGg squad/hero-strength module.

### Science / research

`science_new` contained **243** research records in this capture. Each entry includes a science/item ID and its current level.

Static ID mapping can turn this into named technology progress without scraping the UI.

### Buildings / city

`building_new` contained **190** building instances.

Building objects expose stable UUID/type ID, level and positional/production metadata. Static building-ID mapping can turn these into named city-building levels.

### Inventory / resources

The bootstrap contained:

- **507** `items` records;
- **24** `resource_items` records;
- a structured `resource` object with several named resource/currency counters.

These are technically available but should be treated as optional/private data and not copied into WfGg unless a module has a clear need for them.

### Alliance

The bootstrap exposes the current alliance identifier, while automatic post-login responses expose richer alliance/profile data. In this capture, later read responses confirmed fields for:

- alliance full name;
- alliance abbreviation/tag;
- the player's alliance rank;
- alliance officer/official structures;
- alliance territory/city/stronghold information;
- alliance help/task/train data.

The account's own `get.new.user.info` response contains `allianceRank` alongside server, level, power breakdown and profile data.

### Season / cross-server / events

The normal post-login burst included read responses for season, cross-server, city-war, alliance-territory, arena, event and world-state commands. This demonstrates that WfGg can potentially build additional read-only modules beyond the initial profile/squad use case without relying on screen scraping.

## Security boundary for WfGg

Do **not** persist the raw `init` object or raw PCAP in GitHub, Cloudflare D1 or the browser.

Recommended model:

1. a backend/broker owns the live Last War session credential;
2. raw credential fields (`at`, `deviceId`, `shumeiBoxId`, loginKey, e-mail/code) stay outside browser-visible payloads;
3. the backend selects and normalizes only module-specific fields;
4. D1 stores only the minimum stable identity/profile/module data required by WfGg;
5. technical Last War infrastructure fields and unrelated private account data are discarded.

## Immediate architectural conclusion

The manual `UID + server` declaration form is no longer the right long-term identity mechanism.

A successful Last War account-link flow can provide a verified player identity and then hydrate modules from server-returned data. The first high-value normalized models should be:

- `lastwar_player_profile`
- `lastwar_heroes`
- `lastwar_formations`
- `lastwar_hero_equipment`
- `lastwar_science`
- `lastwar_buildings`
- `lastwar_alliance_membership`

The next live validation step is to use the captured real session identity locally (0600 file only) and confirm that the read-only client can reconnect and receive `init` without another e-mail verification round-trip. `scripts/lastwar-phase3-session-from-pcap.sh` performs exactly that local-only test.
