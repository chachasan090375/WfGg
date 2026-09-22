# WfGg Last War Messenger V6.24 — DRY-RUN ONLY

This source tree is deliberately **not part of the Radar runtime**.

It models the protocol contract proven by offline decompilation of Last War 1.0.351:

- command: `mail.send`
- transport: SFS
- private player-to-player type: `MAIL_SELF_SEND = 21`
- constructor: `MailSendMessage(name, title, contents, allianceId, targetUid, sendLocalTime, type, serverId)`
- same-server official call: `name, title, content, "", uid, curTime, 21`
- UI limits: title 50 bytes via Lua `string.len`, contents 2000 bytes

## Safety boundary

V6.24 here has **no network code** and cannot send anything to Last War.
It only builds a dry-run representation of the request.

Private cross-server mail remains blocked because the official 1.0.351 client contains no proven `MAIL_SELF_SEND` call supplying `serverId`. The observed `serverId` uses are government/president mail paths.

A later write-capable Last War Messenger must be a separate service from the Radar Connector and requires its own explicit enablement/PILOT. Radar itself remains Last War READ-ONLY.
