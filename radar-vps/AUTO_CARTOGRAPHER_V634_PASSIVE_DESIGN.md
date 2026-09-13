# WfGg Radar — Auto-Cartographer V6.3.4 PASSIVE

## Why V6.3.4 exists

V6.3.3 scheduled `/v1/cartographer/tick` calls reused the Last War gameplay credential to perform map probes outside the user's active mobile session. During real in-game teleport tests this correlated with game instability (teleport failures / unresponsive buttons). The Cloudflare scheduler was therefore disabled in production before V6.3.4 work started.

## Non-negotiable safety contract

V6.3.4 is **PASSIVE_ONLY**:

- no scheduled/background Last War protocol call;
- no Last War credential retained by Cartographer;
- no autonomous login/re-login;
- no `/v1/cartographer/tick` active-probe route;
- no goroutine/ticker that touches the game protocol;
- no brute-force server traversal.

The only game traffic allowed is traffic that an existing user-initiated Radar/Collector operation already performs for its own purpose.

## Passive observation

A normal Collector search already reads the nine map regions. V6.3.4 observes those returned `[]protocol.Player` rows in memory and records, without additional game calls:

- dominant server per region;
- distinct server count;
- unique UID count;
- a deterministic 9-region world fingerprint;
- first/last seen timestamps and visit count.

State file:

`/opt/wfgg-radar/state/auto-cartographer-v634-passive.json`

Signed status endpoint (tokenless with respect to Last War):

`GET /v1/cartographer/status`

It reports explicit safety flags:

- `mode=PASSIVE_ONLY`
- `activeProbes=false`
- `holdsGameToken=false`
- `backgroundGameCalls=false`

## Sensor boundary

A VPS that performs zero Last War requests cannot know that the mobile game teleported until some legitimate observation reaches it. V6.3.4 intentionally does not hide this limitation.

For true hands-off detection immediately after a mobile teleport, a future sensor must observe the already-existing mobile session (or another proven server-side signal) without creating a competing Last War session. That sensor is a separate phase and must preserve the V6.3.4 safety contract.
