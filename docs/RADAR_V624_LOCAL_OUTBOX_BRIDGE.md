# Radar V6.24 — Local Outbox Bridge

## Purpose

Allow Radar / ChaCha DEV to prepare internal Last War mail drafts without giving the Radar Connector any Last War write capability.

## Boundary

```
Radar UI
  -> ChaCha DEV / Run Controller
     -> wfgg-messenger-outbox (local process)
        -> dedicated append-only outbox ledger
```

There is **no Last War network hop** in this bridge.

The Messenger process has no `net` / `net/http` dependency and V6.24 exposes only local outbox operations.

## Commands

The process requires an explicit ledger path through `-ledger` or `WFGG_MESSENGER_OUTBOX_LEDGER`.

- `create` — read one JSON draft from stdin and create or reuse an active duplicate.
- `queue <id>` — DRAFT -> QUEUED.
- `cancel <id>` — DRAFT/QUEUED -> CANCELLED.
- `show <id>`
- `history <id>`
- `list`

The output is JSON.

## Draft contract

```json
{
  "targetName": "PLAYER_NAME",
  "targetUid": "PLAYER_UID",
  "title": "TITLE",
  "contents": "MESSAGE",
  "sendLocalTime": 1700000000,
  "senderServer": 8120,
  "targetServer": 8120
}
```

Before entering the outbox, the draft is validated against the offline-proven Last War 1.0.351 contract:

- private player mail = `mail.send`, `MAIL_SELF_SEND = 21`
- title <= 50 bytes
- contents <= 2000 bytes
- target UID and player name required
- cross-server private mail rejected while unproven

## Anti-duplicate

An idempotency hash is derived from recipient UID/name, title, contents and server pair. If the same active DRAFT or QUEUED item already exists, `create` returns that record with `reused=true` instead of adding a second item.

A CANCELLED item is terminal and no longer blocks a fresh draft.

## Persistence and history

The outbox is an append-only JSONL ledger. Every state change appends a complete new revision. Replaying the ledger reconstructs both current state and history.

The ledger is deliberately separate from Collector and Autopilot storage.

## Safety invariant

V6.24 cannot transition to SENT or FAILED because it has no sender. Those states belong to a future write-capable Messenger service and will not be introduced into Radar itself.

Last War mode for Radar remains **READ_ONLY**.
