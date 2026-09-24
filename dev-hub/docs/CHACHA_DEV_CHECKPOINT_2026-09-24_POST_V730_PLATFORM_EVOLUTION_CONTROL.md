# ChaCha DEV checkpoint — Post V7.3 Platform Evolution Control

Date: 2026-09-24
Branch: `dev-hub-post-v730-universal-evolution-coverage-sync`
Qualified code head before checkpoint commit: `9653fd91718e91b76ac5088d18f57be0dfcec94c`

## Frozen V7.3 candidate

Do not rewrite or replay V7.0, V7.1 or V7.2.

V7.3 Direct Operator + Android Widget remains frozen at:

`06190655a7b013806aa2e0e890447535a3e0e4c9`

Its six exact-SHA gates were acquired as SUCCESS. V7.3 is not yet ACQUIRED in production because the real VPS PILOT previously rolled back on Cloudflare D1 write quota exhaustion. Production runtime remains V7.2:

`d35fb8640145edac392627eebbcc1599e1f2e713`

The post-V7.3 work in this branch must not mutate the frozen V7.3 candidate.

## Production/runtime invariants preserved

- V7.2 remains active.
- Direct Operator service remains inactive until the V7.3 real PILOT succeeds.
- Radar Funnel 443 -> 127.0.0.1:8788 must remain untouched.
- Exactly 3 physical platform releases retained.
- Guardian heartbeat runtime timer was protected from D1 pressure by changing the restored cadence from 60s to 300s.
- No automatic external spend: EUR 0.
- No platform component self-mutation or self-promotion.

## Universal evolution governance

Guardian coverage is now a source of universal evolution governance.

Current expected Guardian component count: 48.

Universal evolution:
- maps Guardian-covered components into the canonical evolution index;
- fails closed on an unknown Guardian component kind;
- derives one evolution owner per component;
- does not duplicate central intelligence in lightweight agents;
- does not allow self-mutation or self-promotion.

Evolution source catalog drift is fingerprinted for:
- Guardian coverage manifest;
- Technology Core Watch;
- provider adapters;
- MCP provider catalog;
- project embedded assurance.

A material source change creates a platform reassessment request.

## Platform reassessment chain

Implemented chain:

`source drift -> Bus Health -> platform reassessment queue -> evolution owner -> Foundry dispatch -> native Foundry SHADOW -> evidence gate -> PILOT readiness -> real harness contract -> comparative PILOT runner -> Architecture Council review -> protected human approval request -> promotion gate -> controlled apply contract -> deny-by-default apply planner -> canonical Project Control central handoff -> guarded source integration executor`

Key invariants:
- unknown evolution owner: BLOCK;
- owner mismatch: BLOCK;
- Technology Watch stale without refresh: BLOCK;
- incumbent remains control group;
- SHADOW is idempotent;
- already completed SHADOW dispatch does not re-call Technology Watch;
- candidate presence alone never authorizes PILOT;
- exact candidate and incumbent artifacts/revisions required;
- real qualified harness required;
- synthetic harness cannot support a production decision;
- PILOT uses same harness and isolated systemd capsules;
- Emergency Stop respected;
- Guardian PRE/POST evidence required;
- Sentinel exact candidate SHA required;
- PILOT cannot make the final architecture decision.

## Platform comparative PILOT runner

Component:

`dev-hub/bin/platform-component-pilot-runner.py`

The runner:
- is covered by Guardian;
- is watched by Technology Core Watch;
- may run comparative PILOTs only;
- may not deploy production;
- may not promote a component;
- may not expand permissions;
- requires complete pre-PILOT checks;
- requires exact artifacts and exact revisions;
- requires an exact-SHA qualification workflow name;
- requires a Sentinel exact-SHA receipt;
- keeps production entrypoint unchanged;
- persists Guardian PRE/POST receipt digests;
- hands its result to Architecture Council;
- finishes as HOLD incumbent unless later protected promotion approval is recorded.

## Architecture Council platform component review

Component:

`dev-hub/bin/architecture-council-platform-component-review.py`

Policy:

`platform_component_candidate_review` in
`dev-hub/config/architecture-decision-council.v1.json`

Council independently checks:
- pilot contract/result identity;
- candidate/incumbent exact revisions and artifacts;
- same benchmark contract;
- isolated capsules;
- unchanged production entrypoint;
- Guardian PRE/POST;
- Sentinel exact-SHA receipt and exact-SHA workflow success;
- qualification workflow exact-SHA success;
- fresh Technology Watch;
- Logician falsification;
- permission non-escalation;
- rollback readiness;
- measurable gain;
- no material regression;
- zero automatic external spend.

A PASS produces only:

`TECHNICALLY_ADMISSIBLE_AWAIT_EXPLICIT_HUMAN_PROMOTION_APPROVAL`

Council may not auto-promote.

## Real Project Control platform boundary

The real VPS Project Control plane for `chacha-dev-platform` was initialized using the qualified canonical bootstrap operation.

Canonical paths:
- state: `/opt/chacha-dev/runtime/state/chacha-dev-platform/state.json`
- journal: `/opt/chacha-dev/runtime/state/chacha-dev-platform/audit.jsonl`
- ledger: `/opt/chacha-dev/runtime/evidence/chacha-dev-platform/ledger.json`

Observed immediately after bootstrap:
- state created: yes;
- ledger created: yes;
- audit event recorded: yes;
- replay idempotent: yes;
- journal events: 2;
- projection version: 2;
- journal chain: OK;
- approvals: empty.

The qualified post-V7.3 Project Control code reports the platform profile as READY:
- `control_profile=platform`;
- `lifecycle_managed=false`;
- no pending transactions;
- protected human approval boundary=true.

Application lifecycle operations are forbidden for the platform profile:
- plan-transition;
- schedule;
- advance.

V7.2's older status code may still display ordinary IDEA lifecycle blockers, but its protected `record-approval` implementation correctly rejects system actors. A live proof using actor `central-orchestrator` returned `HUMAN_APPROVAL_ACTOR_REQUIRED` and did not alter the ledger.

## Canonical Project Control bootstrap

Added operation:

`bootstrap-control-plane`

It:
- uses `control-plane-store.py init`;
- uses `evidence-collector.py init`;
- is idempotent;
- is forward-only;
- blocks inconsistent partial state;
- never silently deletes or rewrites audit history;
- records the ledger bootstrap as an `EVIDENCE_RECORDED` audit event;
- performs final integrity verification;
- supports `project` and governance-only `platform` profiles.

The local JSON API can invoke bootstrap, but still cannot synthesize `record-approval`.

## Protected human approval request

A technically admissible Council review creates:

`chacha.dev/protected-human-approval-request/v1`

The request binds:
- project `chacha-dev-platform`;
- exact component;
- candidate and incumbent revisions;
- stable approval id;
- exact technical review digest;
- exact evidence string;
- actor requirement `real-human`.

Agent/API approval synthesis is forbidden.

Actual approval must be recorded through the protected Project Control `record-approval` operation.

## Platform component promotion gate

Component:

`dev-hub/bin/platform-component-promotion-gate.py`

It is Guardian-covered and Technology Watch-covered, with read/plan permissions only.

Behavior:
- no recorded approval -> `AWAITING_HUMAN_APPROVAL`;
- forged/system approval -> `BLOCKED`;
- evidence mismatch -> `BLOCKED`;
- Project Control pending transaction -> `BLOCKED`;
- exact real-human approval in both ledger and projection -> `PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY`.

Even after a valid human approval:
- automatic apply = false;
- direct runtime mutation = false;
- production activation = false;
- production deployment = false;
- merge to production branch = false.

The resulting controlled apply contract is limited to:

`SOURCE_RELEASE_CANDIDATE_INTEGRATION`

and requires:
- Central Orchestrator apply;
- candidate-owner apply adapter;
- exact revision;
- rollback;
- post-apply exact-SHA qualification;
- Sentinel;
- Guardian post-apply assurance.

## Latest qualified evidence before checkpoint commit

Qualified code SHA:
`9653fd91718e91b76ac5088d18f57be0dfcec94c`

GitHub Actions:
- ChaCha DEV Branch Foundry source integrator qualification
  - run: `36056467439`
  - conclusion: SUCCESS
- ChaCha DEV universal evolution coverage sync qualification
  - run: `36056467136`
  - conclusion: SUCCESS
- ChaCha DEV Sentinel technical assurance
  - run: `36056467090`
  - conclusion: SUCCESS

VPS source qualification PASS included:
- Branch Foundry source integrator on an isolated temporary bare Git repository;
- namespaced release-candidate ref creation;
- exact ancestry validation;
- idempotent apply;
- exact rollback;
- zero branch mutation;
- zero push/network use;
- sandbox adapter provisioning;
- legacy adapter-provisioning regression;
- canonical Project Control central apply handoff;
- source integration executor;
- controlled apply planner;
- platform promotion gate;
- Project Control bootstrap/platform profile;
- universal evolution coverage 48/48.

## Controlled apply planner

A deny-by-default source-integration planner is now present:

`dev-hub/bin/platform-component-controlled-apply-planner.py`

Registry:

`dev-hub/config/platform-component-apply-adapter-registry.v1.json`

Current registry state:
- schema: `chacha.dev/platform-component-apply-adapter-registry/v1`;
- `default_admission=DENY`;
- registered adapters: none.

The planner is itself:
- covered by Guardian;
- watched by Technology Core Watch;
- governed by a plan-only Guardian role;
- forbidden from production deployment;
- forbidden from component promotion;
- forbidden from runtime mutation;
- forbidden from permission expansion.

Planner behavior:
- invalid/forged promotion gate -> BLOCK;
- permissive or weakened adapter registry -> BLOCK;
- no registered adapter -> `AWAITING_APPLY_ADAPTER`;
- unqualified/wrong-owner/mutating adapter -> BLOCK;
- qualified exact/reversible zero-spend adapter -> only `READY_FOR_CENTRAL_ORCHESTRATOR_APPLY`.

Even when a plan is ready:
- `apply_execution_authorized_by_planner=false`;
- `automatic_apply=false`;
- direct runtime mutation=false;
- production activation=false;
- production deployment=false;
- production merge=false.

Latest qualified planner SHA before this checkpoint update:

`6207af20d869ad116f7d97c2187deff77ce1a83a`

GitHub Actions for that SHA:
- universal evolution coverage sync qualification: run `36053931054` SUCCESS;
- Sentinel technical assurance: run `36053930863` SUCCESS.

VPS source qualification PASS included:
- controlled apply planner;
- default DENY registry;
- invalid registry fail-closed;
- promotion gate;
- universal evolution coverage 47/47.

## Canonical Central Orchestrator apply handoff

Project Control now owns a dedicated operation:

`issue-platform-component-apply-handoff`

It is restricted to the governance-only project:

`chacha-dev-platform`

The operation:
- independently revalidates the human approval in both Evidence Ledger and projection;
- requires Promotion Gate status `PROMOTION_AUTHORIZED_FOR_CONTROLLED_APPLY`;
- requires a ready controlled-apply plan;
- fixes the actor to `central-orchestrator`;
- binds exact component, candidate/incumbent revisions and artifacts;
- binds the candidate-owner adapter;
- binds the exact controlled-apply plan digest;
- requires rollback, Emergency Stop and Guardian PRE/POST;
- emits a deterministic single-use handoff;
- records `PLATFORM_COMPONENT_APPLY_HANDOFF_ISSUED` in the canonical audit journal;
- is idempotent for identical input;
- cannot be synthesized through the agent-facing local JSON API.

The generic `record-control-event` path is forbidden from creating
`PLATFORM_COMPONENT_APPLY_HANDOFF_ISSUED`.

Even after issuance:
- direct runtime mutation=false;
- production activation=false;
- production deployment=false;
- production merge=false;
- automatic apply=false.

## Guarded source integration executor

Component:

`dev-hub/bin/platform-component-source-integration-executor.py`

The executor is:
- Guardian-covered;
- Technology Watch-covered;
- governed as a source-integration-only executor;
- protected by Emergency Stop;
- protected against single-use handoff replay;
- restricted to adapters below `/opt/chacha-dev/adapters/platform-component`;
- shell interpolation forbidden;
- fixed operation protocol only;
- exact component/owner/revision/artifact/adapter binding required.

Execution sequence:
1. validate Project Control Central Orchestrator handoff;
2. atomically consume the single-use handoff;
3. Guardian PRE;
4. candidate-owner adapter `apply`;
5. verify exact source-integration receipt;
6. recheck all post-apply exact-SHA workflows including Sentinel;
7. Guardian POST;
8. return source-release-candidate integration evidence.

If a post-apply exact-SHA gate fails after integration:
- rollback adapter is mandatory;
- rollback receipt must prove restoration;
- result is `BLOCKED_ROLLED_BACK`.

If Guardian POST fails after integration:
- rollback is also mandatory.

The executor never authorizes:
- runtime mutation;
- production activation;
- production deployment;
- merge to production branch.

Current adapter registry remains empty and DENY-by-default, so no real controlled apply can execute.

## Qualified Branch Foundry source integration adapter

Candidate adapter:

`dev-hub/adapters/platform-component-branch-foundry-source-integrator.py`

Policy:

`dev-hub/config/platform-component-branch-foundry-source-integrator.v1.json`

Qualified behavior:
- candidate owner fixed to `branch-foundry`;
- source-only mode `SOURCE_RELEASE_CANDIDATE_INTEGRATION`;
- bare Git repository required;
- candidate must be an exact 40-character commit SHA;
- incumbent must be an exact 40-character commit SHA;
- candidate must descend from incumbent;
- component id is constrained and cannot escape the trusted ref namespace;
- source integration creates only:
  `refs/chacha-dev/release-candidates/<component>/<candidate-sha>`;
- existing conflicting ref fails closed;
- exact replay is idempotent;
- rollback token is bound to repository/component/candidate/incumbent/ref;
- rollback deletes only the exact namespaced ref while it still points to the candidate;
- no working-tree mutation;
- no checkout;
- no merge;
- no push;
- no fetch/network;
- no runtime mutation;
- no production activation/deployment/merge;
- automatic external spend EUR 0.

Exact-SHA qualification at `9653fd91718e91b76ac5088d18f57be0dfcec94c`:
- dedicated source-integrator qualification: SUCCESS;
- universal evolution qualification: SUCCESS;
- Sentinel technical assurance: SUCCESS.

The adapter policy status is `QUALIFIED`, but:
- `registered_for_live_component=false`;
- the canonical apply adapter registry remains empty and `default_admission=DENY`.

### Real VPS byte provisioning

The qualified adapter bytes were provisioned on the VPS using the canonical adapter provisioner only after the three exact-SHA gates passed.

Installed layout:

`/opt/chacha-dev/adapters/platform-component/branch-foundry-source-integrator/1.0.1/`

Current executable:

`/opt/chacha-dev/adapters/platform-component/branch-foundry-source-integrator/current/branch-foundry-source-integrator`

Verified SHA-256:

`sha256:6326bac2239761810aad426b855b85405bdb28d08fcf83f9f868c34bffb7966f`

Provisioning receipt:

`/opt/chacha-dev/runtime/adapter-provisioning/branch-foundry-source-integrator-1.0.1.json`

Receipt proves:
- source digest = installed digest = current executable digest;
- atomic current symlink;
- fail-closed non-destructive probe PASS;
- no live registration or promotion.

Runtime boundaries observed after provisioning:
- V7.2 remains active;
- exactly 3 physical platform releases remain;
- Direct Operator remains inactive;
- Radar Funnel remains the only Funnel and still targets 127.0.0.1:8788;
- `/opt/chacha-dev/source-integration/WfGg.git` is absent;
- no runtime platform-component apply registry exists;
- therefore the provisioned adapter is dormant and cannot execute a real controlled apply.

## Resume rules

On resume:
1. Verify the real branch HEAD before any write.
2. Verify exact-SHA qualification + Sentinel for that HEAD.
3. Do not modify frozen V7.3 SHA `06190655...`.
4. Do not deploy this post-V7.3 branch directly over V7.2.
5. Do not record any human promotion approval unless a real component candidate has completed SHADOW, real comparative PILOT, Council review, and the user explicitly approves that exact approval request.
6. Do not create a generic unrestricted component mutator.
7. The canonical Project Control Central Orchestrator handoff and guarded source integration executor are qualified; do not bypass either.
8. The Branch Foundry source integrator v1.0.1 is exact-SHA qualified and byte-provisioned on the VPS, but remains unregistered/dormant.
9. Keep the canonical adapter registry DENY-by-default. Do not bind the qualified adapter to any live component until a real component candidate supplies exact component/owner/revision/artifact context.
10. Continue by designing/qualifying the protected component-specific adapter binding/registration gate; it may emit a proposed registry binding but must not register automatically.
11. Do not create the real source-integration repository or execute a controlled apply until a real component candidate has a valid Project Control human approval, Promotion Gate contract, ready apply plan, canonical handoff and registered qualified adapter.
12. Production deployment remains a separate protected handoff after source candidate integration and post-apply qualification.
13. Preserve automatic external spend EUR 0.
