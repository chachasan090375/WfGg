# Radar V6.24 — Internal Mail Protocol Discovery

## Goal

Prepare a future Radar feature that can send a Last War internal mail to another player, while preserving the current Radar invariant:

- Last War remains **strictly READ-ONLY** in Radar.
- No `mail.send` request is emitted by V6.24 discovery.
- No Last War scan is launched by the discovery workflow.
- No token is persisted by this discovery work.

## Static findings already proven

From the exact public `ljagiello/lastwar-client` reference currently pinned by Radar:

`ee5f64de160a8051c2f9f98189b75038dd225a0a`

the documentation proves:

- internal game mail has a dedicated command: `mail.send`;
- it is carried by the main SFS game socket;
- the command supports 1:1 mail or alliance-wide mail;
- real-time chat text is a different subsystem on a dedicated WebSocket.

This means the requested feature is **mail**, not the real-time chat WebSocket.

## Still unresolved

The exact request schema for `mail.send` is not published in the checked-in source of the pinned upstream repository.

Until an authoritative source is found, V6.24 MUST NOT guess:

- recipient field name/type;
- subject/title field name/type;
- message/body field name/type;
- 1:1 versus alliance-wide selector;
- length limits;
- response command;
- server error codes;
- rate limits / cooldowns.

An authoritative schema can come from either:

1. the decompiled Lua request constructor for the `mail.send` message class; or
2. a redacted capture of a mail sent manually from the official client.

The first option is preferred because it is static and non-mutating.

## Architecture boundary for later implementation

Future design:

```
Radar (READ-ONLY)
    |
    v
WfGg Outbox
    |
    v
Last War Messenger (separate write-capable component)
    |
    v
mail.send
```

The Last War Messenger MUST remain a separate component from the Radar Connector. Enabling it will require a separate explicit production decision after protocol qualification and a controlled PILOT.

## V6.24 qualification rule

V6.24 discovery is PASS when all of the following are true:

- `mail.send` is proven from the pinned upstream reference;
- transport is identified as SFS;
- scope is identified as 1:1/alliance-wide;
- the workflow performs static analysis only;
- generated/current Radar runtime contains no `mail.send` execution path;
- `LASTWAR_MUTATION=NO`;
- `GAME_SCAN_EXECUTED=NO`.

Schema discovery may remain `UNRESOLVED` without failing this first static milestone. It simply prevents implementation of an emitter.
