# CHACHA DEV CHECKPOINT — V6.43 ACQUIRED IN REAL VPS RUNTIME

Date: 2026-09-24
Status: ACQUIRED IN REAL VPS RUNTIME
Branch: `dev-hub-v643-multi-project-trust-graduation`
Acquired revision: `634c76248b611cacde37ddbc3c60bd2861d0afe6`

## Acquired baseline — do not replay

V6.35 Central Specialist Authorities: ACQUIRED.
V6.36 Seven-Agent Final Compromise: ACQUIRED.
V6.37 Automatic Seven-Agent Finalization: ACQUIRED.
V6.38 Full Autonomous Project Golden Path: ACQUIRED.
V6.39 Controlled Production Handoff: ACQUIRED / OPERATE.
V6.40 Capability Foundry Auto-Closure: ACQUIRED.
V6.41 Capability Build Loop: ACQUIRED.
V6.42 Durable Capability Adoption & Cross-Project Reuse: ACQUIRED.
V6.43 Multi-Project Trust Graduation: ACQUIRED IN REAL VPS RUNTIME.

Do not replay V6.35-V6.43 in later increments unless explicitly auditing or rolling back.

## Real VPS terminal proof

`CHACHA_DEV_V643_INSTALL=PASS`

Active runtime after installation:
- version: `6.43.0`
- revision: `634c76248b611cacde37ddbc3c60bd2861d0afe6`
- release: `/opt/chacha-dev/platform/releases/20260924T065946Z-634c76248b611cacde37ddbc3c60bd2861d0afe6`
- evidence: `/opt/chacha-dev/evidence/v643-multi-project-trust-graduation-20260924T065946Z.json`

## Real guarantees acquired

- V6.42 real baseline verified before activation.
- Project Control / Verification Broker proof required for trust observations.
- Trust counts DISTINCT project IDs, not raw event count.
- Same-project replay does not inflate trust.
- Three distinct verified successful projects graduate a capability to TRUSTED.
- Critical incident immediately QUARANTINES the capability.
- Negative trust removes the capability from active reuse before gap detection.
- Verified recovery requires fresh evidence.
- Recovery returns to PROVISIONAL, never directly to TRUSTED.
- TRUSTED is advisory and never grants production, network or secret permissions.
- Technology Watch revalidation remains mandatory.
- Guardian and Sentinel authority remain preserved.
- Architecture Council remains final authority.
- Synthetic PILOT trust does not pollute canonical trust state.
- Automatic external spend remains 0 EUR.
- Guardian coverage and post-activation checks passed.

## Next observed gap

V6.43 trust is event-driven but not time-aware.

A capability can remain TRUSTED indefinitely if no negative event arrives. The current policy records `last_seen_at` and requires Technology Watch revalidation, but there is no trust freshness / expiry state, no explicit stale-trust reason, and no automatic downgrade when trust evidence becomes too old.

The next increment should therefore add a bounded, explainable freshness layer without granting new authority or permissions.

Proposed next increment:

**V6.44 — Trust Freshness & Continuous Revalidation**

Required invariants:
- freshness is derived only from verified evidence;
- stale trust never escalates privileges;
- Technology Watch revalidation remains mandatory;
- stale TRUSTED must not silently remain equivalent to fresh TRUSTED;
- negative evidence keeps precedence over freshness;
- Guardian / Sentinel / Architecture Council remain superior authorities;
- existing V6.43 project-distinct counting remains unchanged;
- automatic external spend remains 0 EUR.

