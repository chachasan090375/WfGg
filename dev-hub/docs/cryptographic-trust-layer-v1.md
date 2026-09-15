# ChaCha DEV HUB — Cryptographic Trust Layer V1

## Purpose

The audit journal already provides a SHA-256 hash chain. V1 adds authenticated digital checkpoints so that rewriting the journal and recomputing every hash is detectable against externally anchored signatures.

## Ownership

The **security-reviewer** is the policy owner for cryptographic trust. It reviews signature policy, key lifecycle, rotation, revocation and trust-anchor rules. The security reviewer does **not** receive private-key material.

The **platform-cloud-engineer** operates only an approved signing backend and the anchor transports. It cannot activate, rotate or revoke a key on its own.

The **recovery-engineer** validates signed checkpoints and external anchors during restore drills.

The **ChaCha Dev Architect** orchestrates the workflow and records decisions/evidence, but must never possess, print or persist private signing material.

A real human owner must explicitly approve key activation, rotation, revocation and exceptional trust-policy changes.

## Cryptographic model

1. Every audit event remains chained with SHA-256.
2. At mandatory security boundaries a checkpoint captures the journal sequence, journal-head digest and current state-projection digest.
3. The checkpoint is digitally signed with Ed25519.
4. The public-key fingerprint is SHA-256 over the DER-encoded SubjectPublicKeyInfo.
5. The signed checkpoint is externally anchored outside the VPS.
6. Release boundaries require at least two independent anchors, initially NAS + GitHub.

The signed object never contains a private key or private-key path.

## Mandatory checkpoint triggers

- release boundary
- retirement boundary
- key activation
- key rotation
- key revocation
- restore validation
- explicit manual security checkpoint
- routine interval defined by policy

## Key rotation chain

Rotation uses cross-signing. The old key signs a handover containing the new public-key fingerprint, and the new key signs acceptance containing the old public-key fingerprint. The rotation is also recorded in the append-only control-plane journal.

This creates a continuous signature history even when the active signing key changes.

## External anchoring

Routine checkpoints require at least one independent anchor. Release checkpoints require two. The preferred initial anchors are:

- NAS: independent private storage
- GitHub: independent repository/control plane

An anchor stores only public trust material: checkpoint id, journal head, checkpoint digest, public-key fingerprint, Ed25519 signature, key id and timestamp.

## Enforcement

PREVIEW -> RELEASE now requires a verified signed release checkpoint and trust-anchor quorum in addition to the existing release evidence and human production approval.

RELEASE -> OPERATE requires a post-release signed checkpoint and post-release anchor quorum.

OPERATE -> RETIRE requires a signed retirement checkpoint and retirement anchor quorum.

## Current implementation status

The policy, schemas and signing/verification engine are committed on `dev-hub-v5.0`.

The `openssl-ed25519` provider and `crypto-trust-adapter` are intentionally not enabled yet. The provider is in ASSESS and the adapter is DESIGNED. Runtime enablement requires adapter contract tests, provider-health validation, explicit key-lifecycle setup and human approval. No private signing key has been generated or stored by this change.
