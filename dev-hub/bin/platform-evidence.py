#!/usr/bin/env python3
"""ChaCha DEV HUB Platform Evidence Collector V1.

Normalizes independent provider probe results into Provider Health Snapshot V1
and Storage Governor output into Storage Preflight V1.

This program does not execute provider probes or arbitrary commands. Probe
execution stays in provider-specific adapters; this layer validates freshness,
identity and status before readiness consumes the evidence.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/platform-evidence/v1"
PROBE_CATALOG_SCHEMA = "chacha.dev/provider-health-probes/v1"
PROBE_RESULT_SCHEMA = "chacha.dev/provider-probe-result/v1"
HEALTH_SCHEMA = "chacha.dev/provider-health-snapshot/v1"
STORAGE_SCHEMA = "chacha.dev/storage-preflight/v1"


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FILE_NOT_FOUND={path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON_INVALID={path}:{exc.lineno}:{exc.colno}:{exc.msg}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON_ROOT_NOT_OBJECT={path}")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve(repo_root: Path, configured: str) -> Path:
    p = Path(configured)
    return p if p.is_absolute() else repo_root / p


def parse_time(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"TIMESTAMP_INVALID:{value}")
    if dt.tzinfo is None:
        raise ValueError(f"TIMESTAMP_TIMEZONE_REQUIRED:{value}")
    return dt.astimezone(timezone.utc)


def validate_probe_result(value: dict[str, Any], allowed_states: set[str]) -> list[str]:
    errors: list[str] = []
    if value.get("schema") != PROBE_RESULT_SCHEMA:
        errors.append(f"SCHEMA:{value.get('schema')}")
    for field in ("provider", "state", "source", "checked_at"):
        if not isinstance(value.get(field), str) or not str(value.get(field)).strip():
            errors.append(f"FIELD:{field}")
    if value.get("state") not in allowed_states:
        errors.append(f"STATE:{value.get('state')}")
    try:
        parse_time(str(value.get("checked_at") or ""))
    except ValueError as exc:
        errors.append(str(exc))
    latency = value.get("latency_ms")
    if latency is not None and (not isinstance(latency, (int, float)) or latency < 0):
        errors.append("LATENCY")
    details = value.get("details")
    if details is not None and not isinstance(details, dict):
        errors.append("DETAILS")
    return errors


def result_files(explicit: list[Path], directory: Path | None) -> list[Path]:
    files: list[Path] = list(explicit)
    if directory:
        if not directory.exists():
            raise SystemExit(f"RESULT_DIR_NOT_FOUND={directory}")
        files.extend(sorted(p for p in directory.glob("*.json") if p.is_file()))
    # Preserve first occurrence order while removing duplicate paths.
    out: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def collect_health(repo_root: Path, policy: dict[str, Any], project: str | None,
                   explicit: list[Path], directory: Path | None, output: Path,
                   allow_extra_provider: bool) -> dict[str, Any]:
    health_cfg = policy.get("health") or {}
    refs = policy.get("repository_paths") or {}
    catalog_path = resolve(repo_root, str(refs.get("provider_health_probes")))
    catalog = load_json(catalog_path)
    if catalog.get("schema") != PROBE_CATALOG_SCHEMA:
        raise SystemExit(f"PROBE_CATALOG_SCHEMA_INVALID={catalog.get('schema')}")
    catalog_providers = set((catalog.get("providers") or {}).keys())
    allowed_states = set(str(x) for x in health_cfg.get("states") or [])
    freshness = int(health_cfg.get("default_freshness_seconds") or 300)
    future_skew = int(health_cfg.get("maximum_future_skew_seconds") or 60)
    reject_extra = bool(health_cfg.get("reject_extra_provider", True)) and not allow_extra_provider
    preserve_original = bool(health_cfg.get("preserve_original_state_in_details", True))

    latest: dict[str, tuple[datetime, dict[str, Any], Path]] = {}
    invalid: list[str] = []
    extra: list[str] = []
    for path in result_files(explicit, directory):
        value = load_json(path)
        errors = validate_probe_result(value, allowed_states)
        if errors:
            invalid.append(f"{path}:{'|'.join(errors)}")
            continue
        provider = str(value["provider"])
        if provider not in catalog_providers:
            extra.append(provider)
            if reject_extra:
                continue
        checked = parse_time(str(value["checked_at"]))
        current = latest.get(provider)
        if current is None or checked > current[0]:
            latest[provider] = (checked, value, path)

    if invalid:
        raise SystemExit("PROBE_RESULTS_INVALID=" + ";".join(invalid))
    if extra and reject_extra:
        raise SystemExit("EXTRA_PROVIDERS_REJECTED=" + ",".join(sorted(set(extra))))

    observed_dt = now()
    providers: dict[str, Any] = {}
    all_providers = sorted(catalog_providers | ({p for p in latest} if allow_extra_provider else set()))
    counters = {"HEALTHY": 0, "DEGRADED": 0, "UNAVAILABLE": 0, "UNKNOWN": 0}
    for provider in all_providers:
        found = latest.get(provider)
        if found is None:
            item = {
                "state": str(health_cfg.get("missing_state") or "UNKNOWN"),
                "source": "platform-evidence",
                "checked_at": observed_dt.isoformat(),
                "latency_ms": None,
                "reason": "probe-result-missing",
                "details": {"project": project, "freshness_seconds": freshness},
            }
        else:
            checked, source_value, source_path = found
            age = (observed_dt - checked).total_seconds()
            state = str(source_value["state"])
            reason = str(source_value.get("reason") or "")
            details = dict(source_value.get("details") or {})
            details.update({
                "project": project,
                "probe_result": str(source_path),
                "age_seconds": max(0, round(age, 3)),
                "freshness_seconds": freshness,
            })
            if age < -future_skew:
                if preserve_original:
                    details["original_state"] = state
                state = str(health_cfg.get("future_dated_state") or "UNKNOWN")
                reason = f"probe-result-future-dated:{abs(round(age, 3))}s"
            elif age > freshness:
                if preserve_original:
                    details["original_state"] = state
                state = str(health_cfg.get("stale_state") or "UNKNOWN")
                reason = f"probe-result-stale:{round(age, 3)}s>{freshness}s"
            item = {
                "state": state,
                "source": str(source_value["source"]),
                "checked_at": checked.isoformat(),
                "latency_ms": source_value.get("latency_ms"),
                "reason": reason,
                "details": details,
            }
        providers[provider] = item
        counters[item["state"]] = counters.get(item["state"], 0) + 1

    snapshot = {
        "schema": HEALTH_SCHEMA,
        "observed_at": observed_dt.isoformat(),
        "providers": providers,
    }
    save_json(output, snapshot)
    print(f"PROVIDER_HEALTH_SNAPSHOT={output}")
    print(f"PROVIDERS={len(providers)}")
    for state in ("HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN"):
        print(f"{state}={counters.get(state, 0)}")
    return snapshot


def parse_kv(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Za-z0-9_.-]+", key):
            out[key] = value.strip()
    return out


def flatten_json(value: Any, out: dict[str, Any] | None = None) -> dict[str, Any]:
    out = out or {}
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, dict):
                flatten_json(child, out)
            elif isinstance(child, (str, int, float, bool)) or child is None:
                out[str(key)] = child
    return out


def number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_storage(policy: dict[str, Any], project: str | None, input_path: Path,
                      input_format: str, source: str, output: Path) -> dict[str, Any]:
    cfg = policy.get("storage") or {}
    text = input_path.read_text(encoding="utf-8")
    raw: dict[str, Any]
    detected = input_format
    if input_format == "auto":
        stripped = text.lstrip()
        detected = "json" if stripped.startswith("{") else "key-value"
    if detected == "json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"STORAGE_JSON_INVALID={exc.lineno}:{exc.colno}:{exc.msg}")
        if not isinstance(parsed, dict):
            raise SystemExit("STORAGE_JSON_ROOT_NOT_OBJECT")
        if parsed.get("schema") == STORAGE_SCHEMA:
            save_json(output, parsed)
            print(f"STORAGE_PREFLIGHT={output}")
            print(f"STATUS={parsed.get('status')}")
            return parsed
        raw = flatten_json(parsed)
    elif detected == "key-value":
        raw = parse_kv(text)
    else:
        raise SystemExit(f"STORAGE_FORMAT_UNSUPPORTED={detected}")

    aliases = {str(k).upper(): str(v) for k, v in (cfg.get("numeric_fields") or {}).items()}
    text_fields = {str(k).upper(): str(v) for k, v in (cfg.get("text_fields") or {}).items()}
    by_upper = {str(k).upper(): v for k, v in raw.items()}
    normalized: dict[str, Any] = {}
    for source_key, target in aliases.items():
        normalized[target] = number(by_upper.get(source_key))
    for source_key, target in text_fields.items():
        value = by_upper.get(source_key)
        normalized[target] = str(value) if value is not None else None

    raw_status = str(normalized.get("status") or by_upper.get("STATUS") or "UNKNOWN").upper()
    status_map = {str(k).upper(): str(v).upper() for k, v in (cfg.get("status_map") or {}).items()}
    status = status_map.get(raw_status, str(cfg.get("unknown_status") or "UNKNOWN").upper())
    pressure = normalized.get("pressure")
    reasons: list[str] = []
    current_free = normalized.get("current_free_mb")
    required_free = normalized.get("required_free_mb")
    if isinstance(current_free, (int, float)) and isinstance(required_free, (int, float)) and current_free < required_free:
        reasons.append("INSUFFICIENT_FREE_SPACE")
    if status == "WARN":
        reasons.append("STORAGE_PRESSURE_WARNING")
    if status == "BLOCKED" and not reasons:
        reasons.append("STORAGE_PREFLIGHT_BLOCKED")
    if status == "UNKNOWN":
        reasons.append("STORAGE_PREFLIGHT_STATUS_UNKNOWN")

    artifact = {
        "schema": STORAGE_SCHEMA,
        "project": project,
        "observed_at": now_iso(),
        "status": status,
        "source": source,
        "need_mb": normalized.get("need_mb"),
        "reserve_mb": normalized.get("reserve_mb"),
        "required_free_mb": required_free,
        "current_free_mb": current_free,
        "current_used_percent": normalized.get("current_used_percent"),
        "pressure": pressure,
        "reasons": reasons,
        "details": {
            "input": str(input_path),
            "input_format": detected,
            "raw_status": raw_status,
        },
    }
    save_json(output, artifact)
    print(f"STORAGE_PREFLIGHT={output}")
    print(f"STATUS={status}")
    if current_free is not None:
        print(f"CURRENT_FREE_MB={current_free:g}")
    if required_free is not None:
        print(f"REQUIRED_FREE_MB={required_free:g}")
    for reason in reasons:
        print(f"REASON={reason}")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaCha DEV HUB platform evidence normalizer")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path, default=Path("dev-hub/config/platform-evidence.v1.json"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    health = sub.add_parser("health")
    health.add_argument("--project")
    health.add_argument("--result", action="append", type=Path, default=[])
    health.add_argument("--result-dir", type=Path)
    health.add_argument("--allow-extra-provider", action="store_true")
    health.add_argument("--output", required=True, type=Path)

    storage = sub.add_parser("storage")
    storage.add_argument("--project")
    storage.add_argument("--input", required=True, type=Path)
    storage.add_argument("--format", choices=["auto", "json", "key-value"], default="auto")
    storage.add_argument("--source", default="storage-governor")
    storage.add_argument("--output", required=True, type=Path)

    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else repo_root / args.policy
    policy = load_json(policy_path)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")

    if args.cmd == "health":
        collect_health(repo_root, policy, args.project, args.result, args.result_dir,
                       args.output, args.allow_extra_provider)
    else:
        normalize_storage(policy, args.project, args.input, args.format, args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
