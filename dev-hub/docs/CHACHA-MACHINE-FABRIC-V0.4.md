# ChaCha Machine Fabric V0.4

## Purpose

ChaCha Machine Fabric is a general-purpose governed machine communication
and orchestration layer.

It is NOT specific to ChaCha DEV.

ChaCha DEV, WfGg, backups, development tooling, personal files, NAS
operations and future projects may all consume the same infrastructure.

## Architectural invariants

1. ChaCha Remote Operator remains the canonical ChatGPT FIRST_ROUTE.
2. Tailscale is the private machine-to-machine transport.
3. No new public ingress is required.
4. No general arbitrary shell capability is exposed.
5. Operations are expressed as named capabilities.
6. Guardian remains authoritative for governed mutations.
7. Sentinelle remains part of technical qualification before promotion.
8. STOP remains available.
9. Data should move directly node-to-node where practical.
10. The VPS coordinates transfers but should not relay large payloads
    unnecessarily.
11. Operating-system differences belong in adapters.
12. Upper layers consume capabilities rather than system-specific commands.

## Nodes

- ChaChaVPS: controller, router, governance, runtime
- ChaChaMac: workstation, development, build, interactive operations
- ChaChaNAS: storage, backup, archive, persistent data
- ChaChaTel: mobile and emergency-access node

## Control plane

ChatGPT
→ ChaCha Remote Operator MCP
→ ChaCha Machine Fabric Router
→ Guardian / policy
→ target node agent

## Data plane

ChaChaMac ↔ ChaChaNAS
ChaChaMac ↔ ChaChaVPS
ChaChaTel ↔ ChaChaVPS
ChaChaTel ↔ ChaChaNAS

Direct transport should use the private Tailscale mesh.

## V0.4 scope

V0.4 provides:

- multi-node inventory
- named capability contracts
- fail-closed route resolution
- no execution
- no production activation
- no CCR registration yet
- no UMG materialization yet

## Next gates

V0.5:
inspect and integrate the real Canonical Component Registry and
Universal Materialization Gate contracts.

V0.6:
materialize ChaChaMac node agent.

V0.7:
materialize ChaChaNAS node agent.

V0.8:
materialize ChaChaTel node agent.

V0.9:
governed direct node-to-node transfer contracts.

V1.0:
general Machine Fabric production qualification.
