# WfGg Simulator — Terminology Policy

## Rule

The simulator must not invent or freely translate Last War labels.

For every UI term in FR / EN / IT / ES, keep a provenance and one of these states:

- `in-game-verified`: exact wording captured from the game client in that language. This is authoritative.
- `official-public`: wording published by Last War / FUNFLY on an official site or official Help Center. May still require in-game confirmation when different official pages use different variants.
- `platform-localized`: wording from the official Last War listing/editorial material on Google Play / App Store. Useful evidence, but not authoritative over the in-game client.
- `pending`: no exact official wording accepted yet. Do not display a guessed translation in production.

## Priority

1. Current in-game client string in the selected language.
2. Current official Last War website / Help Center.
3. Official app-store localization associated with Last War.
4. Anything else is research-only and cannot become a production label without confirmation.

## Conflict rule

If official sources disagree, do not choose the most natural translation. Keep all observed variants in `official-terminology.v1.json`, mark the final game label as pending, and resolve it with an in-game capture/string.

Known examples already showing why this matters:

- FR: official website uses `Véhicule Missile`, while the official Help Center also uses `Missiles` in formation wording.
- ES: official website uses `Misiles`, while Google Play localized editorial material uses `Vehículo de misiles`.
- FR gear: official Help Center mentions `Tourelles` / `Puces`, while Google Play localized editorial material describes `Canons` / `Puces` / `Armure` / `Radar`.

## Implementation requirement

All simulator UI labels must be read from the terminology dictionary by stable semantic IDs. Calculation code must never depend on a translated display string.
