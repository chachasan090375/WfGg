# ChaCha DEV — Checkpoint V7.0 ACQUIRED

Date: 2026-09-24

## Acquisition

- Version: **V7.0 — Consolidated Platform Baseline**
- Canonical branch: `dev-hub-v700-consolidated-platform-baseline`
- Acquired runtime revision: `b061f1405fc758ff22be241c5c791a3ecb58c9ec`
- Runtime version: `7.0.0`
- Active release: `/opt/chacha-dev/platform/releases/20260924T153443Z-b061f1405fc758ff22be241c5c791a3ecb58c9ec`
- Runtime evidence: `/opt/chacha-dev/evidence/v700-consolidated-platform-baseline-20260924T153443Z.json`
- Previous acquired rollback baseline: V6.63 `a3803180a64f1ea95d94466b7b10529a7a4af92f`
- Secondary verified rollback: V6.60 `f78cb1972112d32b1ac3ae582009bc96385be58c`
- Replay rule: **do not replay the incremental V6 chain except explicit audit/rollback**.

The commit containing this checkpoint is documentary only and is not the acquired runtime revision.

## Consolidation result

V7 replaces the physical V6 release mille-feuille with one canonical compiled runtime baseline.

Before V7:
- physical releases: **85**
- release tree size: approximately **884 MiB**
- current runtime release included historical tests/docs/installers.

After V7:
- physical releases: **3**
- V7 active + V6.63 rollback + V6.60 rollback
- release tree size: approximately **40 MiB**
- freed during Intendant consolidation: **859.5 MiB**
- V7 compiled active release size: approximately **10.47 MiB**
- historical tests deployed in active runtime: **NO**
- historical docs deployed in active runtime: **NO**
- old V6 installer scripts deployed in active runtime: **NO**
- Git history preserved: **YES**
- automatic remote branch deletion: **NO**

## Consolidation ownership and governance

- consolidation owner: **Intendant**
- default consolidation mode: **DRY_RUN**
- destructive apply requires:
  - Guardian PASS
  - Sentinel exact-revision PASS
  - V7 exact-revision qualification PASS
  - Architecture Council consolidation approval
  - healthy V7 runtime
  - verified rollback releases
  - explicit operator purge approval
- active release may never be retired by Intendant.
- Architecture Council remains final authority.
- active self-mutation: **NO**
- self-promotion: **NO**
- permission expansion: **NO**
- automatic external spend: **€0**

## V7 qualification

Exact acquired SHA `b061f1405fc758ff22be241c5c791a3ecb58c9ec`:

- V7 consolidated platform baseline qualification: **PASS**
- Sentinel technical assurance: **PASS**
- compiled runtime builder: **PASS**
- Intendant DRY_RUN: **PASS**
- Architecture Council consolidation gate: **PASS**
- real physical purge: **PASS**
- post-purge runtime health: **PASS**
- Guardian all hooks active: **YES**
- Technology Watch: **FRESH**
- Observation Bus hash chain: **PASS**

Critical historical invariants requalified under V7:
- V6.60 independent accuracy attestation: **PASS**
- V6.61 real-world evidence / isolated candidate: **PASS**
- V6.63 Radar attribution and runtime surfaces: **PASS**
- V6.64 project-bound evidence / Acceptance Council gate invariants: **PASS**

## Runtime fleet state

- agent_count: **35**
- MIXED_EVIDENCE: **24**
- BENCHMARK_HEAVY: **11**
- MEASURE_FIRST: **0**
- Guardian all hooks active: **true**

## Radar boundary preserved

`technology-radar-agent` remains:
- scope: **PROJECT_ONLY**
- central brain role: **false**
- Technology Watch platform role: **false**
- production permission: **false**
- SRE/Release execution credit without explicit actor binding: **forbidden**

Technology Watch remains the global platform technology-watch authority.

## Aborted V6.64 revision quarantine

The aborted concurrent V6.64 revision:

`a059ac0392c42961229106ee3d3d9c1871d608f6`

remains present in the append-only Observation Bus for audit history. V7 adds a trusted abort tombstone so its partial observations are excluded from Fleet metrics without rewriting historical Bus records.

## Acceptance candidate

The Acceptance Engineer candidate remains:
- isolated: **YES**
- incumbent control group: **YES**
- production activation: **NO**
- promotion: **NO**
- explicit human promotion approval required: **YES**

## Canonical V7 rule

From V7 forward:

**1 platform version → 1 canonical branch → 1 acquired runtime SHA → 1 active release → 1 checkpoint**

Physical runtime retention is capped at **3 releases** unless an explicit audited exception is approved.

## Resume baseline

Resume future ChaCha DEV work from:

- branch: `dev-hub-v700-consolidated-platform-baseline`
- runtime SHA: `b061f1405fc758ff22be241c5c791a3ecb58c9ec`
- platform version: `7.0.0`

Do not restart the V6 incremental chain. New work should evolve from V7 using consolidated versioning and Intendant retirement governance.
