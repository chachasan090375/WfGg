# ChaCha DEV HUB — Task Graph & Evidence V1

Status: DESIGN + REFERENCE IMPLEMENTATION

## Purpose

This layer connects the lifecycle state machine to specialist agents and real evidence.

It answers two questions:

1. What concrete work must be done before a lifecycle transition can occur?
2. What independently verified evidence proves that the work succeeded?

The system deliberately separates **production of work** from **verification of work**.

## Flow

`Lifecycle transition -> Task Graph -> Specialist execution -> Task Result -> Independent verification -> Evidence Ledger -> Lifecycle check`

Example for `VERIFY -> PREVIEW`:

- produce `test-result`
- produce `security-scan`
- produce `ci-result`
- produce `preview-candidate`
- evaluate blocking gates:
  - identity-security
  - testing
  - build-dependencies
  - ci-cd-release
- write verified evidence into the ledger
- ask the Lifecycle Engine whether promotion is allowed

## Task Graph

The Task Graph is deterministic and generated from:

- `lifecycle.v1.json`
- `quality-gates.v1.json`
- `evidence-catalog.v1.json`
- `orchestration-policy.v1.json`

Each task declares:

- owner specialist role
- required abstract capabilities
- required permission
- dependencies
- expected outputs
- verification mode
- whether it blocks the transition

The graph generator checks that:

- the transition exists;
- referenced quality gates exist;
- dependencies are acyclic;
- every task permission is legal in the **current** lifecycle stage.

The last rule is important: permissions of the target stage are granted only after a successful lifecycle promotion.

## Evidence Catalog

`evidence-catalog.v1.json` maps lifecycle artifact names to roles, capabilities and verification rules.

Examples:

- `test-result` -> Testing role -> `unit-test-js` -> machine verification
- `security-scan` -> Security role -> `security-scan-js` -> machine verification
- `rollback-plan` -> Release role -> documentation capability -> independent review
- `production-release` -> explicit human approval

This avoids hard-coding tools such as Vitest or Playwright into lifecycle rules. The Capability Registry resolves the provider later.

## Task Results

A Task Result is not automatically accepted as evidence.

A successful result contains:

- task identity
- producer
- timestamp
- raw evidence references and digests
- requested outputs
- verification status, method and verifier

An agent cannot create an `OK` lifecycle artifact merely by claiming success.

## No self-certification

For non-approval tasks:

`producer != verifier`

Examples:

- implementation agent produces a change; independent review verifies it;
- test agent requests execution; test runner output is verified by the orchestration/evidence layer;
- security specialist requests a scan; scanner output is independently recorded.

Human approvals are different: the human approver is the authoritative actor for the decision itself.

## Evidence Ledger

Only the Evidence Collector writes normalized evidence into the lifecycle ledger.

The collector validates:

- project matches graph;
- task exists in graph;
- output was declared by that task;
- success has evidence;
- required verification mode is respected;
- self-certification is rejected;
- `NOT_APPLICABLE` has an explicit reason;
- approval is verified by a human.

Every accepted result receives a SHA-256 digest and an append-only history entry.

The lifecycle engine consumes the normalized ledger structure:

- `artifacts`
- `gates`
- `approvals`
- `risk_acceptances`

## Trust model

The V1 trust model is intentionally conservative:

- producer claims are untrusted;
- machine output is evidence, not automatically interpretation;
- gate evaluation is separate from artifact production;
- human approval is mandatory for production release and other high-impact actions;
- missing or unverifiable evidence becomes `UNVERIFIED`, never `OK`;
- production mutation remains outside this layer.

## Parallelism

Read-only and evidence-gathering tasks may run in parallel.

Repository/workspace writes remain constrained by the orchestration policy (`max_parallel_write_agents_per_project = 1`). A future Execution Scheduler will turn the DAG into runnable waves while enforcing locks, provider health and Storage Governor preflight.

## Reference commands

Generate a graph:

```bash
python3 dev-hub/bin/task-graph-engine.py \
  --project wfgg \
  --transition VERIFY->PREVIEW \
  --lifecycle dev-hub/config/lifecycle.v1.json \
  --quality dev-hub/config/quality-gates.v1.json \
  --catalog dev-hub/config/evidence-catalog.v1.json \
  --orchestration dev-hub/config/orchestration-policy.v1.json \
  --output /tmp/wfgg.verify-preview.tasks.json
```

Initialize an evidence ledger:

```bash
python3 dev-hub/bin/evidence-collector.py init \
  --project wfgg \
  --ledger /tmp/wfgg.evidence.json
```

Ingest one independently verified task result:

```bash
python3 dev-hub/bin/evidence-collector.py ingest \
  --graph /tmp/wfgg.verify-preview.tasks.json \
  --result /tmp/task-result.json \
  --ledger /tmp/wfgg.evidence.json
```

Then the existing Lifecycle Engine performs the transition check against that ledger.

## Next layer

The next implementation layer is the **Execution Scheduler**:

- resolve task capabilities to healthy providers;
- assign specialist agents;
- group safe read tasks into parallel waves;
- serialize writes with project locks;
- run Storage Governor preflight for heavy tasks;
- dispatch tasks;
- collect raw results;
- send them through independent verification;
- feed the Evidence Collector;
- call the Lifecycle Engine;
- stop automatically on blocking failures.
