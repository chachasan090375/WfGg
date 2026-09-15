#!/usr/bin/env python3
"""ChaCha DEV HUB Cryptographic Trust Layer V1.

Creates and verifies signed audit checkpoints. It deliberately does not generate,
activate, rotate or revoke private keys automatically. Private-key material is
passed only as an external path to the approved signing backend and is never
written to Git or the control-plane state.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_SCHEMA = "chacha.dev/control-plane-state/v1"
CHECKPOINT_SCHEMA = "chacha.dev/signed-checkpoint/v1"
TRUST_SCHEMA = "chacha.dev/cryptographic-trust/v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_obj(value: Any) -> str:
    return sha256_bytes(canonical(value))


def unsigned_fields(checkpoint: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "schema", "project", "checkpoint_id", "created_at", "journal_sequence",
        "journal_head_digest", "state_projection_digest", "reason", "key_id", "algorithm"
    ]
    return {key: checkpoint[key] for key in keys}


def openssl(args: list[str], input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["openssl", *args],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
            timeout=30,
        )
    except FileNotFoundError:
        raise SystemExit("OPENSSL_NOT_FOUND")
    except subprocess.TimeoutExpired:
        raise SystemExit("OPENSSL_TIMEOUT")


def public_der(public_key: Path) -> bytes:
    proc = openssl(["pkey", "-pubin", "-in", str(public_key), "-outform", "DER"])
    if proc.returncode != 0:
        raise SystemExit("PUBLIC_KEY_INVALID=" + proc.stderr.decode("utf-8", "replace")[:300])
    return proc.stdout


def public_fingerprint(public_key: Path) -> str:
    return sha256_bytes(public_der(public_key))


def validate_ed25519_public_key(public_key: Path) -> None:
    proc = openssl(["pkey", "-pubin", "-in", str(public_key), "-text", "-noout"])
    text = (proc.stdout + proc.stderr).decode("utf-8", "replace").lower()
    if proc.returncode != 0 or "ed25519" not in text:
        raise SystemExit("PUBLIC_KEY_NOT_ED25519")


def validate_ed25519_private_key(private_key: Path) -> None:
    proc = openssl(["pkey", "-in", str(private_key), "-text", "-noout"])
    text = (proc.stdout + proc.stderr).decode("utf-8", "replace").lower()
    if proc.returncode != 0 or "ed25519" not in text:
        raise SystemExit("PRIVATE_KEY_NOT_ED25519_OR_NOT_READABLE")


def create_checkpoint(state: dict[str, Any], key_id: str, reason: str) -> dict[str, Any]:
    if state.get("schema") != STATE_SCHEMA:
        raise SystemExit(f"STATE_SCHEMA_INVALID={state.get('schema')}")
    sequence = state.get("last_event_sequence")
    head = state.get("last_event_digest")
    if not isinstance(sequence, int) or sequence < 1 or not isinstance(head, str):
        raise SystemExit("STATE_MISSING_JOURNAL_HEAD")
    projection_digest = sha256_obj(state.get("state") or {})
    return {
        "schema": CHECKPOINT_SCHEMA,
        "project": state.get("project"),
        "checkpoint_id": "chk-" + uuid.uuid4().hex,
        "created_at": now_iso(),
        "journal_sequence": sequence,
        "journal_head_digest": head,
        "state_projection_digest": projection_digest,
        "reason": reason,
        "key_id": key_id,
        "algorithm": "Ed25519",
        "public_key_fingerprint": None,
        "signature": None,
        "checkpoint_digest": None,
        "anchors": [],
        "rotation": None,
    }


def sign_checkpoint(checkpoint: dict[str, Any], private_key: Path, public_key: Path) -> dict[str, Any]:
    if checkpoint.get("schema") != CHECKPOINT_SCHEMA:
        raise SystemExit("CHECKPOINT_SCHEMA_INVALID")
    validate_ed25519_private_key(private_key)
    validate_ed25519_public_key(public_key)
    message = canonical(unsigned_fields(checkpoint))
    with tempfile.TemporaryDirectory(prefix="chacha-sign-") as td:
        msg = Path(td) / "message.json"
        sig = Path(td) / "signature.bin"
        msg.write_bytes(message)
        proc = openssl(["pkeyutl", "-sign", "-rawin", "-inkey", str(private_key), "-in", str(msg), "-out", str(sig)])
        if proc.returncode != 0:
            raise SystemExit("SIGNATURE_FAILED=" + proc.stderr.decode("utf-8", "replace")[:300])
        signature = sig.read_bytes()
    out = dict(checkpoint)
    out["public_key_fingerprint"] = public_fingerprint(public_key)
    out["signature"] = base64.b64encode(signature).decode("ascii")
    out["checkpoint_digest"] = sha256_obj({**unsigned_fields(out), "public_key_fingerprint": out["public_key_fingerprint"], "signature": out["signature"]})
    return out


def verify_checkpoint(checkpoint: dict[str, Any], public_key: Path) -> list[str]:
    errors: list[str] = []
    if checkpoint.get("schema") != CHECKPOINT_SCHEMA:
        return ["CHECKPOINT_SCHEMA_INVALID"]
    validate_ed25519_public_key(public_key)
    expected_fp = public_fingerprint(public_key)
    if checkpoint.get("public_key_fingerprint") != expected_fp:
        errors.append("PUBLIC_KEY_FINGERPRINT_MISMATCH")
    try:
        signature = base64.b64decode(str(checkpoint.get("signature") or ""), validate=True)
    except Exception:
        return errors + ["SIGNATURE_BASE64_INVALID"]
    message = canonical(unsigned_fields(checkpoint))
    with tempfile.TemporaryDirectory(prefix="chacha-verify-") as td:
        msg = Path(td) / "message.json"
        sig = Path(td) / "signature.bin"
        msg.write_bytes(message)
        sig.write_bytes(signature)
        proc = openssl(["pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(public_key), "-sigfile", str(sig), "-in", str(msg)])
        if proc.returncode != 0:
            errors.append("SIGNATURE_INVALID")
    expected_digest = sha256_obj({**unsigned_fields(checkpoint), "public_key_fingerprint": checkpoint.get("public_key_fingerprint"), "signature": checkpoint.get("signature")})
    if checkpoint.get("checkpoint_digest") != expected_digest:
        errors.append("CHECKPOINT_DIGEST_MISMATCH")
    return errors


def anchor_manifest(checkpoint: dict[str, Any]) -> dict[str, Any]:
    required = ["signature", "checkpoint_digest", "public_key_fingerprint"]
    if any(not checkpoint.get(x) for x in required):
        raise SystemExit("CHECKPOINT_NOT_SIGNED")
    return {
        "schema": "chacha.dev/trust-anchor/v1",
        "project": checkpoint["project"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "journal_sequence": checkpoint["journal_sequence"],
        "journal_head_digest": checkpoint["journal_head_digest"],
        "checkpoint_digest": checkpoint["checkpoint_digest"],
        "key_id": checkpoint["key_id"],
        "public_key_fingerprint": checkpoint["public_key_fingerprint"],
        "signature": checkpoint["signature"],
        "created_at": checkpoint["created_at"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True, type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fp = sub.add_parser("fingerprint")
    p_fp.add_argument("--public-key", required=True, type=Path)

    p_create = sub.add_parser("create-checkpoint")
    p_create.add_argument("--state", required=True, type=Path)
    p_create.add_argument("--key-id", required=True)
    p_create.add_argument("--reason", required=True)
    p_create.add_argument("--output", required=True, type=Path)

    p_sign = sub.add_parser("sign")
    p_sign.add_argument("--checkpoint", required=True, type=Path)
    p_sign.add_argument("--private-key", required=True, type=Path)
    p_sign.add_argument("--public-key", required=True, type=Path)
    p_sign.add_argument("--output", required=True, type=Path)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--checkpoint", required=True, type=Path)
    p_verify.add_argument("--public-key", required=True, type=Path)

    p_anchor = sub.add_parser("anchor-manifest")
    p_anchor.add_argument("--checkpoint", required=True, type=Path)
    p_anchor.add_argument("--output", required=True, type=Path)

    args = parser.parse_args()
    policy = load(args.policy)
    if policy.get("schema") != TRUST_SCHEMA:
        raise SystemExit(f"TRUST_POLICY_SCHEMA_INVALID={policy.get('schema')}")

    if args.cmd == "fingerprint":
        validate_ed25519_public_key(args.public_key)
        print(f"PUBLIC_KEY_FINGERPRINT={public_fingerprint(args.public_key)}")
        return
    if args.cmd == "create-checkpoint":
        checkpoint = create_checkpoint(load(args.state), args.key_id, args.reason)
        save(args.output, checkpoint)
        print(f"CHECKPOINT_CREATED={args.output}")
        return
    if args.cmd == "sign":
        signed = sign_checkpoint(load(args.checkpoint), args.private_key, args.public_key)
        save(args.output, signed)
        print(f"CHECKPOINT_SIGNED={args.output}")
        print(f"KEY_ID={signed['key_id']}")
        print(f"PUBLIC_KEY_FINGERPRINT={signed['public_key_fingerprint']}")
        return
    if args.cmd == "verify":
        errors = verify_checkpoint(load(args.checkpoint), args.public_key)
        print("SIGNATURE_VERIFY=" + ("OK" if not errors else "FAIL"))
        if errors:
            print("ERRORS=" + ",".join(errors))
            raise SystemExit(2)
        return
    if args.cmd == "anchor-manifest":
        manifest = anchor_manifest(load(args.checkpoint))
        save(args.output, manifest)
        print(f"ANCHOR_MANIFEST_CREATED={args.output}")
        return


if __name__ == "__main__":
    main()
