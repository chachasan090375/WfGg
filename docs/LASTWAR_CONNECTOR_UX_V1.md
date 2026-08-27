# WfGg Last War Connector — UX contract v1

Status: design/development branch only (`connector-readonly-v1`).

## Non-negotiable product rule

The end user never needs a terminal, Termux, shell command, token, API key, JSON file, packet capture command or manual configuration file.

The CLI under `connector/` is developer/diagnostic tooling only and must never be presented as the normal user journey.

## Target user journey

### Normal path

1. User signs in to WfGg normally.
2. In Profile / Simulator, user taps **Relier mon compte Last War**.
3. WfGg starts a short-lived pairing transaction silently.
4. WfGg tries the browser-first Last War authentication/identity path.
5. If the browser path can establish the required read-only game session, import starts immediately.
6. User sees **Synchronisation en cours** and then **Compte synchronisé**.
7. WfGg updates the simulator from the normalized read-only snapshot.

No token or pairing code is displayed in the normal path.

### Helper path (only if browser-only access is technically impossible)

1. User taps **Relier mon compte Last War**.
2. WfGg detects platform and checks whether `WfGg Connect` is available.
3. If installed, a deep link launches it and pairing is automatic.
4. If not installed, WfGg presents one platform-appropriate button such as **Installer WfGg Connect**.
5. After installation, the helper opens automatically from the browser deep link and returns the user to WfGg when linked.
6. Subsequent synchronizations are one-tap or automatic and require no reconfiguration unless the Last War session expires.

The helper has a graphical UI. No command line is exposed.

## Platform policy

- Web browser: preferred path on every platform.
- Windows: browser-first; graphical WfGg Connect fallback if required.
- macOS: browser-first; graphical WfGg Connect fallback if required.
- Android: browser-first; graphical WfGg Connect app fallback if required.
- iOS/iPadOS: browser-first is mandatory for the initial release unless a compliant native distribution path is available. Do not tell users to sideload or use a terminal.

## User-facing states

Only these concepts should be visible:

- `Non relié`
- `Connexion à Last War…`
- `Autorisation…`
- `Synchronisation…`
- `Compte synchronisé`
- `Dernière mise à jour : <date>`
- `Mettre à jour`
- `Dissocier mon compte`
- `La session Last War a expiré — Se reconnecter`

Technical terms such as access token, refresh token, bearer token, pairing token, device ID, fingerprint, SFS2X, TCP, session config and D1 must not appear in user-facing copy.

## Security contract

- WfGg cloud never stores a Last War password or email verification code.
- Long-lived Last War session material, if technically required, stays on the user's device/helper.
- WfGg server receives only normalized data required by the simulator.
- Cloud API explicitly rejects credential-like fields in snapshots.
- WfGg pairing is one-time and short-lived.
- Device authorization is revocable from the user's WfGg profile.
- Synchronization access tokens are short-lived and automatically renewed by the helper.
- Read-only Last War command allowlist only. No game action/write command is part of this connector.

## Data scope v1

The connector should request only data useful to WfGg, progressively:

1. Account identity: game UID, server, player name.
2. Heroes: ownership, native ID, level, rarity/variant, grade/stars.
3. Hero progression: skills, exclusive weapon, Awakening, Wall of Honor where available.
4. Equipment: assignment, slot, rarity, level, stars/promotion.
5. Research values used by the simulator.
6. Drone / component values used by the simulator.
7. Other simulator-relevant layers only after native protocol confirmation.

Do not fetch mailbox, chat, contacts, purchases, private messages or unrelated account content.

## Performance target

- Existing linked user: one tap to refresh.
- No repeated authentication while the local Last War session remains valid.
- Differential sync where protocol support permits it.
- Snapshot payload is normalized and compact; no raw protocol dump is stored in D1.

## Current technical truth

The official Last War website embeds its own account sign-in (`accounts.lastwar.com`), which makes a browser-first experience plausible. However, current public interoperability research for reconnecting an established game account still uses session material captured from the real game client. Therefore WfGg must not claim browser-only full profile import until the account-site session can be proven to yield or exchange for the game-session credentials required for read-only state queries.
