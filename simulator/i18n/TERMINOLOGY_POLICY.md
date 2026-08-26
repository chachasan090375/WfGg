# WfGg Simulator — Terminology Policy

## Rule

The simulator must not invent, normalize, simplify, or freely translate Last War labels.

For every UI term in FR / EN / IT / ES, keep a provenance and one of these states:

- `in-game-verified`: exact wording captured from the current game client in that language. This is authoritative.
- `official-public`: wording published by Last War / FUNFLY on an official website or official Help Center. It may still require in-game confirmation when different official pages use different variants.
- `platform-localized`: wording from the official Last War listing/editorial material on Google Play / App Store. Useful evidence, but never authoritative over the current game client.
- `game-data-mirror`: exact-looking identifier or label found in a current research/game-data mirror. It is useful to identify the correct node and its structure, but is not accepted as an official localized UI string.
- `research-only`: external/community terminology used only to locate or model a mechanic. It must never become a production display label by itself.
- `pending`: no exact acceptable wording has been established. Do not display a guessed translation in a final production screen.

## Priority

1. Current in-game client string in the selected language.
2. Current official Last War website / Help Center.
3. Official app-store localization associated with Last War.
4. Current game-data mirror, only for semantic/node identification — never for localized translation authority.
5. Community/external research, only as a discovery aid.

## Conflict rule

If official sources disagree, do not choose the most natural translation. Keep all observed variants in the terminology registry, mark the final game label as pending, and resolve it with an in-game capture/string.

Known examples already showing why this matters:

- FR: official website uses `Véhicule Missile`, while other official/public wording also uses `Missile` or `Missiles` depending on context.
- ES: official website uses `Misiles`, while official platform-localized material also uses `Vehículo de misiles`.
- FR gear: official/platform material exposes variants such as `Canons`, `canons magnétiques`, `Tourelle`, `Puces`, `Armure` and `Radar` depending on context.
- EN mastery data currently distinguishes `Missile Mastery` as a tree title while node names use `Missile Vehicle ...`. This is not to be normalized away before in-game verification.

## Research-tree rule

Public research mirrors may establish:

- semantic node identity;
- tree membership;
- Roman suffix / Squad slot relationship;
- max research level;
- dependency topology;
- numerical data when independently validated for the calculation engine.

They may **not** establish an official FR / IT / ES translation. A localized label remains `pending` until supported by a higher-priority source.

## Implementation requirement

All simulator UI labels must be read from terminology dictionaries by stable semantic IDs. Calculation code must never depend on a translated display string.

A screen may be implemented and tested while terms are pending, but it cannot be declared linguistically final for a locale until every visible Last War-specific label on that screen is resolved according to this policy.
