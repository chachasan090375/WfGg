# WfGg — Last War normalized module model v1

Status: **laboratory only** (`portal-auth-lastwar-lab-v1`). No production migration is applied by this document.

## Evidence baseline

The privacy-safe Phase 6 export from a real Last War `init` bootstrap confirms the following useful domains are present in one authoritative payload:

- 31 heroes (`userHero`)
- 3 active army formations (`army_formation`)
- 12 formation templates (`formation_template`)
- 180 hero-equipment records (`heroEquips`)
- 6 general equipment records (`equipList`)
- 1 weapon record (`weaponArr`)
- 190 building instances (`building_new`)
- 243 science/research records (`science_new`)
- one `playerInfo` power/progression object

The same export confirms `networkUsed=false`: this model was derived offline from the user's own PCAP.

## Privacy rule

WfGg modules do not need the raw Last War session credential or device identity.

Never persist in module tables:

- access token / refresh token / loginKey
- deviceId / airKey / shumeiBoxId / advertising IDs
- raw Login payload or raw PCAP
- network/database hostnames
- e-mail verification code

For shareable development fixtures, also omit player/alliance names and raw account-specific instance UUIDs.

## Normalized entities

### `lastwar_player_profile`

One row per linked WfGg user.

Suggested fields:

- `wfgg_user_id`
- `hero_power`
- `army_power`
- `building_power`
- `science_power`
- `squad_equip_power`
- `battle_card_power`
- `dominator_power`
- `deco_power`
- `player_max_power`
- `army_kill`
- `pve_level`
- `stamina`
- `captured_at`

### `lastwar_heroes`

One row per hero catalog ID.

Suggested fields:

- `wfgg_user_id`
- `hero_id`
- `level`
- `rank_lv`
- `awaken_lv`
- `skin_id`
- `state`
- `skill_count`
- `has_weapon_info`
- `captured_at`

The public hero catalog can later map `hero_id` to localized name, rarity/type and artwork without storing those labels redundantly in account data.

### `lastwar_formations`

One row per active formation/template.

Suggested fields:

- `wfgg_user_id`
- `formation_kind` (`army` / `template`)
- `formation_index`
- `squad_no`
- `type`
- `slots`
- `state`
- `chip_equip_group`
- `defence_priority`
- `captured_at`

### `lastwar_formation_heroes`

Child rows for formation membership.

- `wfgg_user_id`
- `formation_kind`
- `formation_index`
- `slot_order`
- `hero_id`

Raw Last War hero-instance UUIDs are used only transiently while normalizing the payload, then converted to public `hero_id` values.

### `lastwar_hero_equipment`

- `wfgg_user_id`
- `hero_id`
- `cfg_id`
- `level`
- `promote`
- `captured_at`

Raw equipment UID and raw hero UID are deliberately discarded after the local join.

### `lastwar_general_equipment`

- `wfgg_user_id`
- `cfg_id`
- `slot`
- `power`
- `exp`
- `num`
- `captured_at`

### `lastwar_weapons`

Initial safe subset:

- `wfgg_user_id`
- `level`
- `power`
- `exp`
- `chip_lv`
- `chip_exp`
- `skill`
- `skill_level`
- `captured_at`

### `lastwar_buildings`

Multiple instances of the same building type exist, so type ID alone is not a row key.

Shareable fixtures use an `instance_ordinal` assigned after sorting by building type/level rather than exposing the raw Last War building UUID.

Suggested fields:

- `wfgg_user_id`
- `b_id`
- `instance_ordinal`
- `level`
- `state`
- `prod_status`
- `captured_at`

### `lastwar_science`

- `wfgg_user_id`
- `science_id`
- `level`
- `captured_at`

## Current first-module recommendation

Build the first UI around three sections because the Phase 6 evidence is already sufficient and stable:

1. **Vue générale** — power breakdown + PvE/progression.
2. **Héros & équipes** — hero roster, active formations/templates and hero equipment joins.
3. **Progression base** — building levels + science levels.

Resource balances remain intentionally out of the first model until a concrete WfGg feature needs them.

## Phase 7

`scripts/lastwar-phase7-normalized-module-data.sh` performs the next offline step. It reads the same PCAP and outputs `WFGG_LASTWAR_PHASE7_NORMALIZED_MODULE_DATA.json` with module-ready data while removing raw credentials, names and account-specific instance UUIDs.

The Phase 7 JSON is the intended development fixture for building the first WfGg Last War screens. It is still personal progression data, so it should remain a laboratory fixture and should not be committed to the public repository.
