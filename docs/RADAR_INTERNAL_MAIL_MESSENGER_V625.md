# Radar V6.25 — Internal Mail Messenger Guarded

## Purpose

V6.25 turns the V6.24 protocol discovery into a **safe application contract** for future automatic player-to-player internal mail.

It does **not** send mail.

Radar production remains unchanged and Last War remains strictly READ-ONLY.

## Proven Last War contract

Static decompilation of Last War 1.0.351 proved:

- command: `mail.send`
- player-to-player type: `MAIL_SELF_SEND = 21`
- constructor: `MailSendMessage:OnCreate(name, title, contents, allianceId, targetUid, sendLocalTime, type, serverId)`
- 1:1 official call shape:
  `MailSend(name, title, content, "", uid, curTime, 21)`
- wire types:
  - `name`: UtfString
  - `title`: UtfString
  - `contents`: UtfString
  - `allianceId`: UtfString
  - `targetUid`: UtfString
  - `sendLocalTime`: Long
  - `type`: Int
  - `serverId`: Int, optional
- official UI limits: title 50 bytes, contents 2000 bytes
- official UI refuses empty title or empty contents
- response handler treats a present `errorCode` as an error and otherwise refreshes Mail state.

Other proven mail types are intentionally excluded from this candidate:

- `MAIL_ALLIANCE_ALL = 20`
- `MAIL_PRESIDENT_SEND = 45`
- `MAIL_PRESIDENT_SEND_EIGHT = 201`

## Guarded architecture

```
Radar READ-ONLY
      |
      | future prepared intent only
      v
V6.25 Messenger Contract / Outbox
      |
      +-- DISABLED (default) -> BLOCKED
      |
      +-- DRY_RUN            -> DRY_RUN_READY
      |
      X  no ENABLED mode in V6.25
```

The V6.25 module deliberately contains:

- no TCP/HTTP client;
- no import of Last War networking/session packages;
- no `SendExtension`;
- no `net.Dial`;
- no write-capable game transport;
- no token storage;
- no production deployment path.

## Anti-duplicate model

Every prepared message requires a `campaignKey` and a `targetUid`.

The idempotency key is:

`SHA-256(campaignKey + NUL + targetUid)`

Therefore the same campaign cannot accidentally prepare the same recipient twice when a persistent Outbox is added in a later version.

## Next gated step

V6.26 may add a persistent SQLite Outbox and a **separate** Last War Messenger transport.

A real `mail.send` PILOT must remain separately approved. The Radar Connector itself must not gain game-write commands.
