# ChaCha DEV — Checkpoint V7.1 ACQUIRED

Date: 2026-09-24

## Acquisition

- Version: **V7.1 — Intendant Hygiene Cycle**
- Canonical branch: `dev-hub-v710-intendant-hygiene-cycle`
- Acquired runtime revision: `a2ab2403f53d1e57b1c976e97595b44692ce6597`
- Runtime version: `7.1.0`
- Active release: `/opt/chacha-dev/platform/releases/20260924T164217Z-a2ab2403f53d1e57b1c976e97595b44692ce6597`
- Runtime evidence: `/opt/chacha-dev/evidence/v710-intendant-hygiene-cycle-20260924T164217Z.json`
- Immediate rollback: V7.1 `04cb15a998dda8996be2c7cfb6442d4a16d1529d`
- Previous-generation rollback: V7.0 `b061f1405fc758ff22be241c5c791a3ecb58c9ec`

The commit containing this checkpoint is documentary only and is not the acquired runtime revision.

## Acquired behavior

- one Intendant hygiene scheduler
- one systemd timer, calendar-hourly, persistent, randomized
- daily safe-temp hygiene
- weekly release-retirement dry-run
- monthly review-only consolidation
- threshold watch
- hygiene debt score
- dynamic active + two rollback retention
- rollback revisions must differ from the active revision
- rollback selection preserves platform-version diversity when available
- rollback ordering is based on platform generation then acquisition evidence time, never restored-directory age
- Intendant is plan-only
- Central Orchestrator is the only physical hygiene executor
- Guardian realtime PRE/POST gates
- Architecture Council final authority
- global deployment lock serializes V7.1 transactions
- installer rollback only restores systemd units owned by its exact revision
- governed V7.1-to-V7.1 upgrade supported
- remote branch auto-delete: **NO**
- source-code auto-delete: **NO**
- Git history preserved
- automatic external spend: **€0**

## Hygiene cadence

- scheduler poll: hourly
- light hygiene due: every 24 h
- weekly release retirement review: every 168 h
- monthly deep consolidation review: every 720 h
- threshold triggers:
  - filesystem usage >= 75 %
  - physical releases > 3
  - stale/temp candidate storage >= 1 GiB
  - hygiene debt score >= 60

Monthly consolidation remains review-only for source code and remote branches.

## Runtime state after final acquisition

- physical releases: **3**
- distinct physical revisions: **3**
- active: V7.1 `a2ab2403...`
- immediate rollback: V7.1 `04cb15a9...`
- generation rollback: V7.0 `b061f140...`
- Intendant timer: **active + enabled**
- timer scheduling: **calendar-hourly**
- Guardian all hooks active: **true**
- Technology Watch: **FRESH**
- Observation Bus chain: **PASS**
- Observation Bus event count: **103**
- Fleet agents: **35**
- MIXED_EVIDENCE: **24**
- BENCHMARK_HEAVY: **11**
- MEASURE_FIRST: **0**
- Technology Radar scope: **PROJECT**
- Technology Radar production coverage: **20 %**

## Rollback restoration proof

V7.0 was restored from acquired SHA `b061f1405fc758ff22be241c5c791a3ecb58c9ec`.

The reconstructed compiled runtime digest matched the original V7.0 acquisition digest exactly:

`sha256:3ad10730d151c90e972104fdc3b35b602573683697073f3d76723d731e13fc84`

Therefore the retained V7.0 rollback is cryptographically equivalent to the originally acquired compiled runtime.

## Governance invariants

- Intendant direct mutation: **NO**
- physical mutation executor: **central-orchestrator**
- Guardian realtime destructive-operation verdict: **required**
- Architecture Council approval: **required for governed retirement**
- Sentinel exact-revision assurance: **required**
- canonical Observation Bus rewrite: **NO**
- benchmark evidence mutation: **NO**
- self-promotion: **NO**
- permission expansion: **NO**
- Technology Radar central-brain role: **NO**
- Technology Watch platform-global role: **YES**
- automatic external spend: **€0**

## Resume baseline

Resume future ChaCha DEV work from:

- branch: `dev-hub-v710-intendant-hygiene-cycle`
- runtime SHA: `a2ab2403f53d1e57b1c976e97595b44692ce6597`
- platform version: `7.1.0`

Do not replay the transitional V7.1 runtime SHAs. They remain available in Git/evidence history for audit only.

Next planned evolution:

**V7.2 — Human Interface Gateway**
