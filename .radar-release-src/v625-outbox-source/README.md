# WfGg Internal Mail Outbox V6.25 — DRY-RUN

V6.25 adds the **pre-send queue and anti-duplicate layer** for Last War internal private mail.

It inherits the V6.24 protocol findings:

- command: `mail.send`
- transport: SFS
- private type: `MAIL_SELF_SEND = 21`
- title limit: 50 bytes (Lua `string.len`)
- contents limit: 2000 bytes
- known same-server private request:
  `name, title, contents, "", targetUid, sendLocalTime, 21`

## What V6.25 does

A message can be prepared with:

- a `campaignKey` defining the anti-duplicate scope;
- a `trigger` describing why Radar prepared it;
- target player name and UID;
- title and contents;
- sender/target server metadata;
- a server-time value used only for the dry-run wire preview.

The durable outbox is a separate JSON file, written atomically with mode `0600`.

Idempotency is:

`campaignKey + targetUid`

This means a player can receive at most one prepared message for a given campaign. Re-preparing the exact same message is a no-op. Reusing the same campaign/player pair with different content is rejected as `OUTBOX_IDEMPOTENCY_CONFLICT`.

`sendLocalTime` is deliberately excluded from message identity so a retry performed later does not become a second message.

## Safety boundary

V6.25 has no network package, no Last War socket, no token handling and no send transition.

The only state currently produced is:

`PREPARED_DRY_RUN`

There is intentionally no `SENT` state and no code capable of executing `mail.send`.

Private cross-server mail remains blocked until an official/private-mail call using or proving cross-server routing is identified.

Radar itself remains strictly Last War READ-ONLY. A future write-capable Messenger will be a separate service and will require explicit authorization before any functional Last War PILOT.
