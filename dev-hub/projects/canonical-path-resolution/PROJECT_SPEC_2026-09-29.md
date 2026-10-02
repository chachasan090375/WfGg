# ChaCha DEV — Canonical Path Resolution & Multi-Agent Recovery

Date: 2026-09-29
Status: CANDIDATE / NOT ACTIVE
Baseline production: c788348a9d80bbf1eaa4a9e54ff0cf4fd7bc86d3

## Purpose

Eliminate path drift, repeated path rediscovery and blind retry loops across ChaCha DEV by making component locations canonically declared, resolvable and continuously reconciled, while escalating genuine non-progress to a capability-driven multi-agent resolution cell.

## Core principles

1. The Canonical Component Registry remains the single component authority. This project MUST NOT create a competing registry.
2. Canonical Path Resolver resolves declared component locations from canonical manifests/contracts; agents and orchestrators MUST NOT rediscover known paths by repository exploration as a normal execution strategy.
3. Path Drift Reconciler compares declared paths with runtime truth: manifest, release/current link, systemd, filesystem, policy, runtime state and evidence roots.
4. Non-progress is detected from evidence, not from an arbitrary retry counter alone. Signals include identical repeated error, unchanged state, no new evidence, already-explored cycle, or confidence not increasing.
5. A bounded hard retry ceiling may exist only as a safety guard; it is not the recovery algorithm.
6. When non-progress is detected, the current loop stops and all evidence/state is preserved before recovery planning.
7. Logicien coordinates causal analysis but MUST NOT operate as the sole fallback.
8. Recovery participants are selected from declared capabilities. Technology Watch, Dark Intelligence, Sentinelle, Bastion, Ergonom(e), Visual, Translation, Foundries and other structural agents may participate when relevant.
9. Technology Watch may use public internet, technical documentation and GitHub repositories as evidence sources. GitHub is never an automatic fallback simply because execution failed.
10. Dark Intelligence is used only when its isolated specialized sources are relevant and policy allows it.
11. Architecture Council arbitrates competing recovery strategies when required by confidence/risk/policy.
12. Run Controller may resume only with a materially different strategy or new evidence; replaying the same failed strategy without new evidence is forbidden.
13. Guardian and Sentinelle remain mandatory gates where their contracts apply. No bypass is introduced.
14. STOP remains authoritative and fail-closed.
15. Automatic external spend remains EUR 0 by default.
16. Remote MCP V0.2 SHA 301def3ab83015d454e75fc41c2de1b8a41e0b0d is out of scope and MUST NOT be modified by this project.

## Canonical path contract

Every managed component must be able to declare, when applicable:

- source_root
- release_root
- current_link
- runtime_root
- state_root
- evidence_root
- systemd_unit
- endpoints and ports
- writable_roots
- persistent_root
- owner
- lifecycle state

The resolver must support semantic lookups such as component + key rather than requiring callers to reconstruct paths.

## Resolution states

- RESOLVED: canonical value exists and runtime verification agrees.
- RESOLVED_UNVERIFIED: canonical value exists but runtime verification has not yet run.
- DRIFT: canonical and runtime truth disagree.
- UNRESOLVED: required canonical value is absent.
- AMBIGUOUS: multiple authoritative-looking values conflict.
- BLOCKED_POLICY: resolution or verification is forbidden by policy.

UNRESOLVED, AMBIGUOUS and unsafe DRIFT MUST stop blind exploration and enter governed recovery.

## Multi-agent recovery flow

1. Detect non-progress or resolution anomaly.
2. Freeze the failed strategy; persist evidence and attempted hypotheses.
3. Logicien performs causal decomposition and identifies missing capabilities/evidence.
4. Capability Registry selects relevant agents dynamically.
5. Selected agents investigate in parallel where safe.
6. Logicien assembles hypotheses, contradictions and falsification results.
7. Architecture Council arbitrates when more than one viable strategy remains or risk requires it.
8. Guardian validates governance constraints; Sentinelle validates technical acceptability when applicable.
9. Run Controller receives one revised strategy with explicit changed assumptions/evidence.
10. Resume once. If no measurable progress results, return to recovery with the new evidence; do not replay the identical strategy.

## Anti-loop invariants

- Same action + same inputs + same state + no new evidence => MUST NOT be re-executed automatically.
- Repository search is evidence acquisition, not a retry policy.
- Historical paths may be consulted by recovery agents, never silently promoted to canonical truth.
- Every recovery iteration records hypothesis_id, evidence_delta, strategy_delta and outcome.
- A recovery cycle with empty evidence_delta and empty strategy_delta terminates BLOCKED_NON_PROGRESS.

## Drift reconciliation

For each managed component compare:

canonical manifest -> component registry -> release/current link -> service manager -> filesystem -> runtime policy -> runtime state/evidence paths.

Classify existing components:

- COMPLIANT
- UPDATABLE
- SUPERSEDED
- ORPHAN
- INCOMPATIBLE

Safe non-destructive reconciliation may be proposed automatically under policy. Destructive or ambiguous repair requires the normal governance boundary.

## Acceptance criteria

1. A component path is resolved through one canonical API/contract without repository-wide discovery.
2. A known path disagreement is detected as DRIFT with both declared and observed values preserved.
3. An unknown required path yields UNRESOLVED and does not trigger blind repeated GitHub searches.
4. Repeating an identical failed action without new evidence is prevented.
5. Non-progress invokes capability-driven multi-agent recovery; Logicien is coordinator, not sole solver.
6. Technology Watch can contribute public technical/GitHub evidence when relevant without becoming a mandatory fallback.
7. Dark Intelligence is optional, policy-gated and isolated.
8. Architecture Council can arbitrate conflicting viable strategies.
9. Guardian/Sentinelle/STOP invariants remain intact.
10. Existing components can be audited and classified COMPLIANT/UPDATABLE/SUPERSEDED/ORPHAN/INCOMPATIBLE.
11. No automatic external spend is introduced.
12. Remote MCP V0.2 frozen candidate remains byte-for-byte untouched by this project.
13. Qualification includes a deterministic loop fixture proving termination on zero progress and resumption only after strategy/evidence change.

## Promotion rule

Materialization of files or passing unit tests does not make this project ACTIVE. Production activation requires qualification, Guardian/Sentinelle gates where applicable, an isolated pilot, post-activation verification and explicit promotion under the normal ChaCha DEV lifecycle.