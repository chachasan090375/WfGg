# CHACHA DEV CHECKPOINT — V6.43 MULTI-PROJECT TRUST GRADUATION

Date: 2026-09-24
Status: QUALIFIED / SENTINEL PASS / NOT YET ACQUIRED IN REAL VPS RUNTIME
Branch: `dev-hub-v643-multi-project-trust-graduation`
Qualified code HEAD: `92a228ce7b5f4346e6a90d045c202e68b1fba385`

## Acquired baseline — do not replay

V6.35 Central Specialist Authorities: ACQUIRED IN REAL RUNTIME.
V6.36 Seven-Agent Final Compromise: ACQUIRED IN REAL RUNTIME.
V6.37 Automatic Seven-Agent Finalization: ACQUIRED IN REAL RUNTIME.
V6.38 Full Autonomous Project Golden Path: ACQUIRED IN REAL RUNTIME.
V6.39 Controlled Production Handoff: ACQUIRED / OPERATE.
V6.40 Capability Foundry Auto-Closure: ACQUIRED IN REAL RUNTIME.
V6.41 Capability Build Loop: ACQUIRED IN REAL RUNTIME.
V6.42 Durable Capability Adoption & Cross-Project Reuse: ACQUIRED IN REAL VPS RUNTIME.

V6.42 acquired checkpoint:
`dev-hub/docs/CHACHA_DEV_CHECKPOINT_2026-09-24_V642.md`

V6.42 real terminal marker:
`CHACHA_DEV_V642_INSTALL=PASS`

## V6.43 goal

Add multi-project trust graduation for durable capabilities:
- count verified outcomes by DISTINCT project, not raw event count;
- prevent trust inflation from replay/idempotent reuse of the same project;
- graduate capability confidence CANDIDATE -> PROVISIONAL -> TRUSTED;
- apply negative evidence immediately;
- quarantine severe failures/incidents;
- require fresh verified recovery evidence before reuse resumes;
- keep trust advisory only;
- never escalate production, secret or network permissions from trust;
- preserve Technology Watch, Guardian, Sentinel and Architecture Council authority;
- automatic external spend remains 0 EUR.

## V6.43 implementation currently present

### 1. Trust policy
`dev-hub/config/capability-trust-graduation.v1.json`

Main rules:
- 1 distinct verified success project -> PROVISIONAL.
- 3 distinct verified success projects -> TRUSTED.
- same project replay does not increase trust.
- verified failure -> DEGRADED.
- high incident -> DEGRADED.
- critical incident -> QUARANTINED.
- verified recovery -> RECOVERY_CANDIDATE.
- after recovery, 2 fresh distinct verified success projects are required.
- recovery returns only to PROVISIONAL, never directly to TRUSTED.
- TRUSTED is advisory, not an authority or permission grant.

### 2. Verified capability outcome observer
`dev-hub/bin/capability-trust-observer.py`

It:
- accepts capability project outcomes only when backed by committed Project Control / Verification Broker evidence;
- verifies Project Control receipt, evidence ledger, verified task result, claims digest and matching ledger artifact;
- rejects self-declared VERIFIED outcomes without Project Control proof;
- binds observations to exact durable capability lineage:
  - component kind = capability
  - component_id = capability id
  - version = durable adoption_id
- emits through the canonical learning fabric using source_kind `learning-module`;
- requires Technology Watch revalidation;
- automatic external spend = 0 EUR.

### 3. Component Confidence extension
`dev-hub/bin/component-confidence-engine.py`
`dev-hub/config/component-confidence.v1.json`

V6.25 remains the confidence engine.
For `component_kind=capability`, V6.43 changes the aggregation to DISTINCT project IDs.
Historical component behavior remains backward compatible.

The capability snapshot now exposes:
- distinct_project_count;
- project_distinct_counting=true;
- fresh_success_projects_after_recovery;
- replay does not inflate trust.

### 4. Durable reuse trust filter
`dev-hub/bin/durable-capability-registry.py`

The V6.42 durable merge can now consume:
- `--trust-snapshot`
- `--trust-policy`

Reuse behavior:
- CANDIDATE / PROVISIONAL / TRUSTED remain eligible for reuse;
- DEGRADED / QUARANTINED / RECOVERY_CANDIDATE are removed from the active capability registry before capability-gap detection;
- blocked entries remain in durable/forensic state;
- TRUSTED does not grant any new permissions;
- Technology Watch revalidation remains required.

### 5. Central orchestrator integration
`dev-hub/bin/autonomous-project-orchestrator.py`

Current orchestrator version: V6.43.

Before capability-gap detection it:
- loads durable capability registry;
- looks for canonical confidence snapshot:
  `/opt/chacha-dev/runtime/knowledge/component-confidence.json`;
- applies V6.43 trust policy if the snapshot is present;
- merges only trust-eligible durable capabilities;
- then performs capability-gap detection / Foundry resolution.

Trust therefore constrains reuse BEFORE the project chooses an existing durable capability.

## V6.43 qualification proof

Qualified code HEAD:
`92a228ce7b5f4346e6a90d045c202e68b1fba385`

GitHub Actions:
- ChaCha DEV V6.43 multi-project trust graduation qualification
  - run: `35965234630`
  - conclusion: SUCCESS
- ChaCha DEV Sentinel technical assurance
  - run: `35965234736`
  - conclusion: SUCCESS

The V6.43 E2E test proves:
- Project Control verified observation;
- exact capability lineage;
- distinct-project counting;
- same-project replay does not inflate trust;
- 3 distinct successful projects -> TRUSTED;
- critical incident -> QUARANTINED;
- negative trust removes capability from active reuse;
- verified recovery requires fresh evidence;
- recovery returns to PROVISIONAL, not TRUSTED;
- trust does not escalate permissions;
- Technology Watch remains required;
- Architecture Council remains final authority;
- automatic external spend = 0 EUR.

Regression coverage on the same qualification:
- V6.42 durable capability adoption regression: PASS.
- V6.25 component confidence regression: PASS.

Historical stale version assertions were made version-compatible; no functional V6.25 invariant was weakened.

## Important current status

V6.43 IS NOT ACQUIRED IN REAL VPS RUNTIME YET.

There is currently no V6.43 real VPS installer/PILOT script in the branch.

Do NOT declare V6.43 acquired from CI alone.

## Exact next step

Create the real V6.43 VPS PILOT/installer from the qualified baseline.

The real PILOT must prove on ChaChaVPS, without replaying V6.35-V6.42:

1. V6.42 real baseline is present.
2. V6.43 release activates safely.
3. A synthetic durable capability is bound to an exact adoption_id.
4. Project 1 verified success -> PROVISIONAL.
5. Replay of Project 1 -> still one distinct success project.
6. Project 2 verified success -> still PROVISIONAL.
7. Project 3 verified success -> TRUSTED.
8. TRUSTED capability is reusable and receives NO new production/network/secret permissions.
9. Critical incident on a distinct project -> QUARANTINED.
10. QUARANTINED capability disappears from the active reuse registry before gap detection.
11. Verified recovery alone -> RECOVERY_CANDIDATE and still blocked.
12. Two fresh distinct verified projects after recovery -> PROVISIONAL only.
13. Technology Watch, Guardian, Sentinel and Architecture Council authority remain preserved.
14. Automatic external spend remains 0 EUR.
15. Synthetic test capability is cleaned up or rolled back so no unwanted active registry pollution remains.

The PILOT must use real Project Control / Verification Broker proof for project outcomes; no self-declared VERIFIED shortcuts.

Only consider V6.43 ACQUIRED after the real VPS terminal marker:
`CHACHA_DEV_V643_INSTALL=PASS`

## Resume instruction

Resume V6.43 from this checkpoint.
Do not replay V6.35-V6.42.
Do not redo already-successful V6.43 CI qualification or Sentinel unless code/runtime-relevant files change.
Start directly by creating and qualifying the real VPS V6.43 PILOT/installer, then run it on ChaChaVPS.
