# WfGg Simulator — In-game terminology validation checklist

## Goal

Close every `pending` Last War label with the exact current client wording in **FR / EN / IT / ES**. A screenshot or directly copied client string wins over public/community terminology.

For every capture, record:

- game language;
- game version if visible;
- screen/path used to reach the label;
- exact capitalization, punctuation, hyphenation and Roman numeral;
- date of capture.

Do not correct spelling or typography from the game. The simulator must reproduce the client label exactly.

## A. Core troop / hero terminology

For each locale capture a hero details/list screen showing:

- Tank type label;
- Aircraft type label;
- Missile type label;
- Attack role;
- Defense role;
- Support role;
- HP / Attack / Defense stat labels.

Priority conflict to resolve: exact Missile wording in each locale.

## B. Hero research tree

For each locale capture the `Hero` research section containing all simulator-relevant nodes:

### Tank
- Tank Mastery I / II semantic nodes
- Cannon Enhancement I / II semantic nodes
- Armor Hardening I / II semantic nodes
- Track Fortification I / II semantic nodes

### Aircraft
- Aircraft Mastery I / II semantic nodes
- Airborne Weapon I / II semantic nodes
- Reinforced Body I / II semantic nodes
- Wingman Tactics I / II semantic nodes

### Missile
- Missile Mastery I / II semantic nodes
- Precision Targeting I / II semantic nodes
- Metal Barricade I / II semantic nodes
- Missile Expansion I / II semantic nodes

Required evidence: tree heading plus enough of each node card to read its complete name and current level.

## C. Advanced type Mastery trees

For **Tank Mastery**, **Aircraft Mastery** and **Missile Mastery**, in each locale capture both tiers I and II and the exact names for:

- Synergy - HP
- Synergy - Attack
- Synergy - Defense
- Synergy - Damage
- March Size
- HP
- Attack
- Defense
- Damage
- Ultimate Defense

Special check: English research mirrors currently use `Missile Mastery` as tree title but `Missile Vehicle ...` in node names. Do not normalize this until the client confirms it.

Also capture the displayed numerical bonus for any node whose per-level curve is still not independently encoded.

## D. Squad research 1–4

For each active Squad tree, capture the exact tree heading and the following combat-relevant nodes:

- Terminator
- Assault Training
- Formation Training
- Survival Training
- Physical Suppression
- Energy Barrage
- Fierce Assault
- Final Stand
- Vigilant Formation
- Counter Defense
- Hold the Line
- Solid Defense

Capture Squad 1, 2 and 3 in every locale. Capture Squad 4 when the account has access to it.

Verify whether the current client uses Roman numerals I / II / III / IV in every language or another localized convention.

## E. Gear inventory

Capture the Equipment/Gear inventory screen in every locale and resolve the exact names of the four slots:

- offensive weapon slot currently represented semantically as `gun`;
- chip slot;
- armor slot;
- radar slot.

Also capture the exact UI words for:

- rarity;
- level;
- stars;
- promotion/upgrade state;
- equipped/assigned status.

Priority conflict: `Cannon`, `Railgun`, `Turret` and their localized variants must not be conflated unless the client proves they are the same UI category.

## F. Exclusive Weapon

For a hero with an Exclusive Weapon available, capture:

- exact feature label;
- level label;
- breakpoint descriptions at levels 10 / 20 / 30 if visible;
- exact same-type specialist wording;
- any activation/deployment condition.

Do this in all four locales where possible.

## G. Wall of Honor

Capture:

- exact feature title;
- level wording;
- type-wide bonus description;
- ATK/DEF/HP labels as displayed there.

This is required because Wall of Honor is a differential Tank/Aircraft/Missile input.

## H. Drone Skill Chips

Capture:

- exact Drone Skill Chip feature name;
- Tank / Aircraft / Missile chip labels;
- rarity/star wording;
- preset/loadout terminology;
- any rule shown for allocation to squads.

## I. Squad / march terminology

Resolve exact current client strings for:

- Squad / Team / Formation / Escouade semantic concept;
- Squad 1 / 2 / 3 / 4 headings;
- March Size;
- Command if displayed as a hero stat;
- Tank Center / Aircraft Center / Missile Center building names.

## J. Season 6

For each locale capture exact names for:

- Bear Totem;
- Eagle Totem;
- Jaguar Totem;
- Tactics Cards feature title;
- Dimensional Crit;
- Frontal Suppression;
- Aftermath Burst;
- Awakening feature and Kimberly / DVA / Tesla awakening labels where visible.

Capture the displayed per-level Totem bonus wording as well as the name.

## K. Boss objectives

Capture exact event/UI wording in each locale for:

- Wanted Boss;
- Wanted Boss 39 and its boss name;
- Wanted Boss 64 and its boss name;
- Wanted Boss 87 and its boss name;
- the +50% troop-type damage rule;
- Crystal Event;
- Crystal Boss;
- Crystal Boss phase names (Weapon / Radar / Chip / Armor / Core semantic phases);
- 5-same-type +30% rule;
- rotating Defense Hero +20% rule.

Because events can rotate or disappear, event captures should include the date.

## L. Acceptance rule

A locale can be marked **terminology-complete** only when:

1. every visible Last War-specific label needed by the simulator has an `in-game-verified` value;
2. all official-source conflicts are resolved against the current client;
3. no final screen falls back to a guessed translation;
4. calculation semantic IDs remain identical across all four locales.

Until then, development may continue with semantic IDs and research-only labels in internal/debug views, but the locale is not final.
