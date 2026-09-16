# Provider Selection Engine V1

## Purpose

The DEV HUB already has an orchestrator (`chacha-dev-architect`), role routing, a capability registry, an execution scheduler, a Run Controller and an independent Verification Broker. V1 adds the missing decision layer between capability resolution and scheduling: a provider-selection engine that ranks eligible providers for one task.

It does **not** execute providers and it does **not** replace the Scheduler or Run Controller.

## Decision chain

1. `chacha-dev-architect` classifies the request and resolves the required role/capability.
2. Provider Selection Engine hard-filters candidates using policy, lifecycle permissions, adapter runtime status and health.
3. Eligible candidates are ranked using verified evidence and operational signals.
4. Execution Scheduler applies dependency, concurrency, retry and failover policy.
5. Run Controller performs explicit dispatch only.
6. Verification Broker independently verifies the produced result.

## Why scoring is needed

Static fallbacks are not enough once several AI development providers exist. The best provider may differ by task type, project, current health, latency, cost and observed verified quality. The engine must learn from verified evidence rather than provider self-reports.

The initial score is 100 points:
- task/capability fit: 30
- verified historical quality: 25
- health: 15
- risk fit: 10
- latency fit: 8
- cost fit: 7
- cross-provider diversity: 5

These are policy weights, not permanent vendor rankings. Technology Radar and observed evidence can justify later policy revisions.

## Evidence and confidence

Historical quality uses only independently verified runs. Unverified producer outputs cannot increase the provider score. Ranking confidence remains NONE/LOW/MEDIUM until enough verified runs exist; the policy currently requires at least 5 verified runs for a confident comparison and tracks at most 50 verified runs over a 90-day window.

When evidence is insufficient the engine must say so rather than pretending that one provider is objectively better.

## Claude and other development agents

Claude is simply another provider behind the capability contract. It receives no special preference. While its adapter is only `CONTRACT_OK`, it is not runtime-eligible. When it reaches `PILOT` or `ENABLED`, verified task evidence can begin contributing to its ranking.

The same applies to Antigravity, Skywork and future providers. New providers can be added without redesigning the orchestration chain.

## Safety boundary

The engine is PLAN_ONLY:
- cannot dispatch;
- cannot promote adapters;
- cannot mutate production;
- cannot bypass human approval;
- cannot use the same provider as producer and independent verifier for the same task.

The Scheduler remains authoritative for retry/failover and the Run Controller remains authoritative for dispatch.
