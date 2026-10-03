#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, time
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "chacha.dev/local-cognitive-runtime-lifecycle-policy/v1"
STAGE_SCHEMA = "chacha.dev/local-cognitive-stage-manifest/v1"
DUAL_SCHEMA = "chacha.dev/external-dual-assurance-verdict/v1"
LEDGER_SCHEMA = "chacha.dev/evidence-ledger/v1"
RECEIPT_SCHEMA = "chacha.dev/local-cognitive-runtime-activation/v1"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_NOT_OBJECT:" + str(path))
    return value


def save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def policy(path: Path) -> dict[str, Any]:
    value = load(path)
    if value.get("schema") != POLICY_SCHEMA:
        raise ValueError("POLICY_SCHEMA_INVALID")
    return value


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def verify_stage(cfg: dict[str, Any], slot: Path) -> dict[str, Any]:
    releases = Path(cfg["releases_root"]).resolve()
    slot = slot.resolve()
    if not inside(slot, releases) or slot.parent != releases:
        raise ValueError("SLOT_OUTSIDE_RELEASES_ROOT")
    manifest_path = slot / "meta/stage-manifest.json"
    manifest = load(manifest_path)
    if manifest.get("schema") != STAGE_SCHEMA:
        raise ValueError("STAGE_MANIFEST_SCHEMA_INVALID")
    if manifest.get("state") != "STAGED_IMMUTABLE_NOT_ACTIVE":
        raise ValueError("STAGE_STATE_INVALID")
    runtime = manifest.get("runtime") or {}
    if runtime.get("build_is_dev") is not False or runtime.get("rpc_built") is not False:
        raise ValueError("RUNTIME_BUILD_GUARDRAIL_FAILED")
    if str(runtime.get("version") or "").startswith("b"):
        raise ValueError("DEVELOPMENT_BUILD_FORBIDDEN")
    if Path(str(manifest.get("slot_path") or "")).resolve() != slot:
        raise ValueError("SLOT_PATH_MISMATCH")
    files = manifest.get("files") or []
    if not files:
        raise ValueError("STAGE_FILE_LEDGER_REQUIRED")
    for row in files:
        rel = Path(str(row.get("path") or ""))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("STAGE_FILE_PATH_INVALID:" + str(rel))
        item = slot / rel
        if row.get("type") == "file":
            if not item.is_file() or digest(item) != row.get("digest"):
                raise ValueError("STAGE_FILE_DIGEST_MISMATCH:" + str(rel))
        elif row.get("type") == "symlink":
            if not item.is_symlink() or not inside(item.resolve(), slot):
                raise ValueError("STAGE_SYMLINK_ESCAPE:" + str(rel))
        else:
            raise ValueError("STAGE_FILE_TYPE_INVALID:" + str(rel))
    server = slot / "bin/llama-server"
    model = slot / "model/Qwen3.5-0.8B-Q4_0.gguf"
    if not server.is_file() or not os.access(server, os.X_OK):
        raise ValueError("STAGE_SERVER_MISSING")
    if not model.is_file() or digest(model) != (manifest.get("model") or {}).get("digest"):
        raise ValueError("STAGE_MODEL_DIGEST_MISMATCH")
    return {"slot": str(slot), "manifest": str(manifest_path),
            "manifest_digest": digest(manifest_path), "runtime": runtime,
            "model_digest": digest(model), "server_digest": digest(server)}


def atomic_switch(current: Path, target: Path, token: str) -> None:
    current = current.absolute(); target = target.resolve()
    current.parent.mkdir(parents=True, exist_ok=True)
    tmp = current.with_name(current.name + ".switch-" + token)
    tmp.unlink(missing_ok=True)
    os.symlink(str(target), str(tmp), target_is_directory=True)
    os.replace(tmp, current)
    fsync_dir(current.parent)


def approval_blockers(cfg: dict[str, Any], ledger: dict[str, Any], evidence: str) -> list[str]:
    if ledger.get("schema") != LEDGER_SCHEMA:
        return ["APPROVAL_LEDGER_SCHEMA_INVALID"]
    approval_id = str(cfg.get("approval_id") or "")
    item = (ledger.get("approvals") or {}).get(approval_id)
    if not isinstance(item, dict):
        return ["PROTECTED_APPROVAL_MISSING"]
    blockers = []
    if item.get("status") != "APPROVED": blockers.append("PROTECTED_APPROVAL_NOT_APPROVED")
    actor = str(item.get("actor") or "")
    forbidden = set(cfg.get("forbidden_approval_actors") or [])
    if not actor or actor in forbidden: blockers.append("REAL_HUMAN_APPROVAL_REQUIRED")
    if not item.get("observed_at"): blockers.append("APPROVAL_TIMESTAMP_MISSING")
    if str(item.get("evidence") or "") != evidence: blockers.append("APPROVAL_EVIDENCE_MISMATCH")
    return blockers


def activation_blockers(cfg: dict[str, Any], expected_revision: str,
                        ledger: dict[str, Any], evidence: str,
                        dual: dict[str, Any]) -> list[str]:
    blockers = approval_blockers(cfg, ledger, evidence)
    emergency = load(Path(cfg["emergency_stop_file"]))
    if emergency.get("active") is not False: blockers.append("EMERGENCY_STOP_ACTIVE")
    platform_revision = (Path(cfg["platform_current"]).resolve() / ".revision").read_text().strip()
    if platform_revision != expected_revision: blockers.append("ACTIVE_PLATFORM_REVISION_MISMATCH")
    if dual.get("schema") != DUAL_SCHEMA or dual.get("verdict") != "PASS":
        blockers.append("DUAL_ASSURANCE_PASS_REQUIRED")
    if dual.get("revision") != expected_revision:
        blockers.append("DUAL_ASSURANCE_REVISION_MISMATCH")
    watch = load(Path(cfg["technology_watch_evaluation"]))
    recommendation = str(watch.get("recommendation_class") or "")
    if recommendation not in set(cfg.get("allowed_production_recommendations") or []):
        blockers.append("TECHNOLOGY_WATCH_NOT_PRODUCTION_READY:" + recommendation)
    return blockers


def status(cfg: dict[str, Any]) -> dict[str, Any]:
    current = Path(cfg["current"])
    target = str(current.resolve()) if current.exists() else None
    emergency = load(Path(cfg["emergency_stop_file"]))
    watch = load(Path(cfg["technology_watch_evaluation"]))
    return {"schema":"chacha.dev/local-cognitive-runtime-lifecycle-status/v1",
            "status":"PASS","current_exists":current.exists(), "current_target":target,
            "emergency_stop_active":emergency.get("active"),
            "technology_watch_recommendation":watch.get("recommendation_class"),
            "production_activation_authorized":False,
            "automatic_external_spend_eur":0}


def make_plan(cfg: dict[str, Any], slot: Path, expected_revision: str,
              ledger: dict[str, Any], evidence: str, dual: dict[str, Any]) -> dict[str, Any]:
    stage = verify_stage(cfg, slot)
    blockers = activation_blockers(cfg, expected_revision, ledger, evidence, dual)
    return {"schema":"chacha.dev/local-cognitive-runtime-activation-plan/v1",
            "status":"PASS" if not blockers else "BLOCK",
            "slot":stage["slot"], "stage_manifest_digest":stage["manifest_digest"],
            "expected_platform_revision":expected_revision, "blockers":blockers,
            "would_mutate_current":not blockers, "service_activation_performed":False,
            "automatic_external_spend_eur":0}


def activate(cfg: dict[str, Any], slot: Path, expected_revision: str,
             ledger: dict[str, Any], evidence: str, dual: dict[str, Any], receipt: Path) -> dict[str, Any]:
    plan = make_plan(cfg, slot, expected_revision, ledger, evidence, dual)
    if plan["status"] != "PASS":
        raise ValueError("ACTIVATION_BLOCKED:" + ",".join(plan["blockers"]))
    current = Path(cfg["current"])
    previous = str(current.resolve()) if current.exists() else None
    token = hashlib.sha256((expected_revision + "\n" + plan["stage_manifest_digest"]).encode()).hexdigest()[:16]
    atomic_switch(current, Path(plan["slot"]), token)
    if current.resolve() != Path(plan["slot"]).resolve():
        raise ValueError("CURRENT_SWITCH_VERIFY_FAILED")
    out = {"schema":RECEIPT_SCHEMA,"status":"PASS","phase":"ACTIVATE",
           "expected_platform_revision":expected_revision,"slot":plan["slot"],
           "previous_target":previous,"active_target":str(current.resolve()),
           "stage_manifest_digest":plan["stage_manifest_digest"],
           "approval_id":cfg.get("approval_id"),"approval_evidence":evidence,
           "service_activation_performed":False,"production_service_started":False,
           "automatic_external_spend_eur":0,"created_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    save(receipt, out)
    return out


def rollback(cfg: dict[str, Any], activation_receipt: Path, receipt: Path) -> dict[str, Any]:
    source = load(activation_receipt)
    if source.get("schema") != RECEIPT_SCHEMA or source.get("status") != "PASS" or source.get("phase") != "ACTIVATE":
        raise ValueError("ACTIVATION_RECEIPT_INVALID")
    current = Path(cfg["current"])
    active_target = Path(str(source.get("active_target") or "")).resolve()
    if not current.exists() or current.resolve() != active_target:
        raise ValueError("CURRENT_NOT_ACTIVATED_TARGET")
    previous = source.get("previous_target")
    if previous:
        atomic_switch(current, Path(str(previous)), "rollback-" + str(os.getpid()))
        restored = str(current.resolve())
    else:
        current.unlink()
        fsync_dir(current.parent)
        restored = None
    out = {"schema":RECEIPT_SCHEMA,"status":"PASS","phase":"ROLLBACK",
           "activation_receipt":str(activation_receipt.resolve()),
           "rolled_back_target":str(active_target),"restored_target":restored,
           "service_activation_performed":False,"automatic_external_spend_eur":0,
           "created_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    save(receipt, out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    v = sub.add_parser("verify-stage"); v.add_argument("--slot", type=Path, required=True); v.add_argument("--output", type=Path)
    for name in ("plan", "activate"):
        p = sub.add_parser(name); p.add_argument("--slot", type=Path, required=True)
        p.add_argument("--expected-platform-revision", required=True)
        p.add_argument("--approval-ledger", type=Path, required=True); p.add_argument("--approval-evidence", required=True)
        p.add_argument("--dual-assurance", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    r = sub.add_parser("rollback"); r.add_argument("--activation-receipt", type=Path, required=True); r.add_argument("--output", type=Path, required=True)
    a = ap.parse_args(); cfg = policy(a.policy)
    try:
        if a.cmd == "status": out = status(cfg)
        elif a.cmd == "verify-stage":
            out = {"schema":"chacha.dev/local-cognitive-stage-verification/v1","status":"PASS",
                   **verify_stage(cfg, a.slot),"production_activation_authorized":False,
                   "automatic_external_spend_eur":0}
            if a.output: save(a.output, out)
        elif a.cmd in {"plan", "activate"}:
            ledger = load(a.approval_ledger); dual = load(a.dual_assurance)
            if a.cmd == "plan":
                out = make_plan(cfg, a.slot, a.expected_platform_revision, ledger, a.approval_evidence, dual)
                save(a.output, out)
            else:
                out = activate(cfg, a.slot, a.expected_platform_revision, ledger, a.approval_evidence, dual, a.output)
        else:
            out = rollback(cfg, a.activation_receipt, a.output)
        print(json.dumps(out, ensure_ascii=False, sort_keys=True))
        return 0 if out.get("status") == "PASS" else 20
    except Exception as exc:
        print(json.dumps({"schema":"chacha.dev/local-cognitive-runtime-lifecycle-error/v1",
                          "status":"BLOCK","reason":str(exc),"automatic_external_spend_eur":0},
                         ensure_ascii=False, sort_keys=True))
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
