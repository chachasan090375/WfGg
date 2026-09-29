#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SOURCE_SCHEMA = "chacha.dev/provider-zero-cost-attestation/v1"
TARGET_SCHEMA = "chacha.dev/conversation-provider-zero-cost-attestation/v1"
RECEIPT_SCHEMA = "chacha.dev/provider-economics-bridge-receipt/v1"
SOURCE_PROVIDER = "antigravity"
DEFAULT_TARGET_PROVIDER = "agy-gemini-conversation"
ALLOWED_COST_CLASSES = {"free", "owned", "included", "local", "quota"}


def parse_iso(value: Any) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def canonical_digest(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def derive(source: dict[str, Any], target_provider_id: str = DEFAULT_TARGET_PROVIDER,
           now: dt.datetime | None = None) -> dict[str, Any]:
    current = now or dt.datetime.now(dt.timezone.utc)
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": "BLOCKED",
        "reason": None,
        "source_provider_id": source.get("provider_id") if isinstance(source, dict) else None,
        "target_provider_id": target_provider_id,
        "source_digest": canonical_digest(source) if isinstance(source, dict) else None,
        "target_attestation": None,
        "automatic_external_spend_eur": 0,
    }
    if not isinstance(source, dict):
        receipt["reason"] = "SOURCE_ATTESTATION_NOT_OBJECT"
        return receipt
    if source.get("schema") != SOURCE_SCHEMA or source.get("provider_id") != SOURCE_PROVIDER:
        receipt["reason"] = "SOURCE_ATTESTATION_IDENTITY_INVALID"
        return receipt
    try:
        spend = float(source.get("automatic_external_spend_eur"))
    except Exception:
        spend = -1.0
    if spend != 0:
        receipt["reason"] = "SOURCE_ATTESTATION_NONZERO_SPEND"
        return receipt
    cost_class = str(source.get("cost_class") or "").lower()
    if cost_class not in ALLOWED_COST_CLASSES:
        receipt["reason"] = "SOURCE_COST_CLASS_NOT_ZERO_COST_ELIGIBLE"
        return receipt
    valid_until = parse_iso(source.get("valid_until"))
    if valid_until is None or valid_until <= current:
        receipt["status"] = "STALE"
        receipt["reason"] = "SOURCE_ATTESTATION_STALE"
        receipt["last_known_reset_at"] = source.get("quota_reset_time") or source.get("resume_at")
        receipt["source_observed_at"] = source.get("observed_at")
        receipt["source_valid_until"] = source.get("valid_until")
        return receipt
    quota_available = source.get("quota_available")
    if cost_class == "quota" and not isinstance(quota_available, bool):
        receipt["reason"] = "SOURCE_QUOTA_AVAILABILITY_UNKNOWN"
        return receipt
    target = {
        "schema": TARGET_SCHEMA,
        "provider_id": target_provider_id,
        "status": "PASS",
        "cost_class": cost_class,
        "quota_available": quota_available if cost_class == "quota" else True,
        "valid_until": source.get("valid_until"),
        "reset_at": source.get("quota_reset_time") or source.get("resume_at"),
        "automatic_external_spend_eur": 0,
        "source_provider_id": SOURCE_PROVIDER,
        "source_attestation_schema": SOURCE_SCHEMA,
        "source_observed_at": source.get("observed_at"),
        "source_status": source.get("status"),
        "source_reason_codes": list(source.get("reason_codes") or []),
        "source_digest": receipt["source_digest"],
    }
    receipt.update({
        "status": "PASS",
        "reason": "DERIVED_FROM_FRESH_LOCAL_ZERO_COST_EVIDENCE",
        "provider_available": target["quota_available"] is True,
        "target_attestation": target,
    })
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--target-provider", default=DEFAULT_TARGET_PROVIDER)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        source = json.loads(args.source.read_text(encoding="utf-8"))
    except Exception as exc:
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "BLOCKED",
            "reason": "SOURCE_ATTESTATION_UNREADABLE",
            "error": type(exc).__name__,
            "automatic_external_spend_eur": 0,
        }
    else:
        receipt = derive(source, args.target_provider)
    raw = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8")
    sys.stdout.write(raw)
    return 0 if receipt.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
