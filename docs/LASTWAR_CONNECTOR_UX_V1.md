# WfGg Last War Connector — UX contract v1

Status: design/development branch only (`connector-readonly-v1`).

## Non-negotiable product rule

The end user never needs a terminal, Termux, shell command, token, API key, JSON file, packet capture command or manual configuration file.

The CLI under `connector/` is developer/diagnostic tooling only and must never be presented as the normal user journey.

## Target user journey

### Preferred path — UID first

1. User signs in to WfGg normally.
2. In Profile / Simulator, user taps **Relier mon compte Last War**.
3. WfGg asks first for the player's **Last War UID**, not for an email address.
4. WfGg attempts a read-only identity resolution for that UID.
5. If Last War exposes the bound contact address through an authorized recovery/verification flow, WfGg displays only a masked form, for example **c***@g***.com**.
6. The user confirms **Envoyer le code**.
7. Last War sends the 6-digit verification code to that address.
8. WfGg asks only for the 6-digit code and immediately discards it after verification.
9. If several Last War characters/roles are returned, WfGg shows a simple character picker with player name/server/UID and the user selects the correct one.
10. User sees **Synchronisation en cours** and then **Compte synchronisé**.
11. WfGg updates the simulator from the normalized read-only snapshot.

No token, login key or pairing code is displayed in the normal path.

### Email fallback — only when UID-to-contact resolution is unavailable

WfGg must not pretend that an UID can reveal a contact address unless Last War actually exposes an authorized endpoint for it.

If UID-to-contact resolution is unavailable, the same flow continues without technical wording:

1. Show the identified UID and player context when available.
2. Explain: **Pour confirmer que ce compte vous appartient, Last War demande l'adresse e-mail associée.**
3. Let the user enter the email address if known.
4. Offer a visible secondary action: **Je ne sais plus quelle adresse e-mail est liée**.
5. That help path gives concise in-game directions to locate/change the linked email from the player's own Last War account, rather than asking for terminal/capture steps.
6. Once the email is entered, Last War sends the code and the flow resumes at the 6-digit verification step.

### Browser-first authentication

WfGg starts a short-lived authorization transaction silently and uses the browser/service path first.

Current interoperability research confirms that a fresh client session can request `account.login.send.verify.code`, accept the email verification code through `account.login.new`, and receive the account session payload containing `gameUid`, `loginKey` and `accountArr`. This means the target experience can be fully web-driven without a terminal on the user's device, provided the WfGg broker can run the compatible Last War protocol service centrally.

The durable Last War `loginKey` and any other reconnect material are implementation secrets. They must never be exposed in the browser UI or JavaScript storage.

### Helper path (only if browser-only access becomes technically impossible)

1. User taps **Relier mon compte Last War**.
2. WfGg detects platform and checks whether `WfGg Connect` is available.
3. If installed, a deep link launches it and pairing is automatic.
4. If not installed, WfGg presents one platform-appropriate button such as **Installer WfGg Connect**.
5. After installation, the helper opens automatically from the browser deep link and returns the user to WfGg when linked.
6. Subsequent synchronizations are one-tap or automatic and require no reconfiguration unless the Last War session expires.

The helper has a graphical UI. No command line is exposed.

## Platform policy

- Web browser: preferred path on every platform.
- Windows: browser-first; graphical WfGg Connect fallback only if required.
- macOS: browser-first; graphical WfGg Connect fallback only if required.
- Android: browser-first; graphical WfGg Connect app fallback only if required.
- iOS/iPadOS: browser-first is mandatory for the initial release unless a compliant native distribution path is available. Do not tell users to sideload or use a terminal.

## User-facing states

Only these concepts should be visible:

- `Non relié`
- `Entrez votre UID Last War`
- `Compte trouvé`
- `Code envoyé à c***@g***.com` when Last War actually provides an authorized masked contact
- `Entrez le code à 6 chiffres`
- `Choisissez votre personnage` when several roles exist
- `Connexion à Last War…`
- `Autorisation…`
- `Synchronisation…`
- `Compte synchronisé`
- `Dernière mise à jour : <date>`
- `Mettre à jour`
- `Dissocier mon compte`
- `La session Last War a expiré — Se reconnecter`

Technical terms such as access token, refresh token, bearer token, pairing token, loginKey, device ID, fingerprint, SFS2X, TCP, session config and D1 must not appear in user-facing copy.

## Privacy rules for account recovery UI

- Never reveal a complete email address obtained from Last War as part of an UID/recovery lookup.
- Prefer masking the local part and domain, e.g. `c***@g***.com`.
- Do not create an endpoint that lets anonymous callers enumerate UID → email associations.
- Any UID-to-contact lookup must require an authenticated WfGg user, rate limiting and abuse controls.
- Responses should be deliberately non-enumerable: avoid differences that reveal whether an arbitrary UID has a linked email when the caller is not already in an authorized linking transaction.
- Verification codes are one-time values and are never persisted or logged.

## Security contract

- WfGg cloud never stores a Last War password or email verification code.
- The verification code is kept only in memory for the active authorization transaction and discarded immediately after use.
- Reconnect material such as a Last War `loginKey`, if retained centrally for automatic refresh, must be encrypted at rest with a dedicated server-side key and must never be returned to the browser.
- Access to decrypted reconnect material is limited to the read-only broker during synchronization.
- WfGg server receives/stores only normalized game data required by the simulator, plus the minimum encrypted reconnect material required to refresh it.
- Cloud API explicitly rejects credential-like fields in normalized snapshots.
- WfGg authorization transactions are one-time and short-lived.
- Device/session authorization is revocable from the user's WfGg profile.
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
- No repeated authentication while the retained Last War reconnect material remains valid.
- Differential sync where protocol support permits it.
- Snapshot payload is normalized and compact; no raw protocol dump is stored in D1.

## Current technical truth

- The official Last War web properties use email-based sign-in/verification.
- The validated game protocol accepts `account.login.send.verify.code` with an email address and then `account.login.new` with the received code.
- A successful verification returns account/session information including `gameUid`, `loginKey` and `accountArr`; the durable `loginKey` can later drive the GSL login path and obtain fresh access-token/session information without asking the user for the email code every time.
- At present there is **no confirmed public proof** that a bare Last War UID can be exchanged for the account's masked email address. Therefore UID-first masked-email recovery is a preferred UX capability under investigation, not a capability WfGg may claim as already working.
