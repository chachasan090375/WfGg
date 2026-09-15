#!/usr/bin/env python3
"""ChaCha DEV HUB Control Plane State Store V1.1.

Maintains one current project projection plus an append-only, SHA-256 hash-chained
JSONL audit journal. The journal is authoritative history; the projection is the
fast current-state view. Mutations are serialized per project and may include
optimistic version/head preconditions. No secrets should be stored here.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_SCHEMA = "chacha.dev/control-plane-state/v1"
EVENT_SCHEMA = "chacha.dev/audit-event/v1"
POLICY_SCHEMA = "chacha.dev/control-plane-state-policy/v1"
SECTIONS = [
    "identity", "lifecycle", "architecture", "capabilities", "providers",
    "execution", "evidence", "approvals", "risks", "decisions", "recovery", "operations"
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


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


def fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        fsync_dir(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())
    fsync_dir(path.parent)


@contextmanager
def mutation_lock(root: Path, project: str):
    project_root = root / project
    project_root.mkdir(parents=True, exist_ok=True)
    lock_path = project_root / ".control-plane-mutation.lock"
    with lock_path.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def merge_patch(target: Any, patch: Any) -> Any:
    """RFC-7396-style merge patch."""
    if not isinstance(patch, dict):
        return deepcopy(patch)
    if not isinstance(target, dict):
        target = {}
    out = deepcopy(target)
    for key, value in patch.items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = merge_patch(out.get(key), value)
    return out


def empty_state(project: str) -> dict[str, Any]:
    state = {section: {} for section in SECTIONS}
    state["identity"] = {"slug": project}
    state["lifecycle"] = {"stage": "IDEA"}
    return state


def paths(root: Path, project: str, policy: dict[str, Any]) -> tuple[Path, Path, Path, Path]:
    storage = policy.get("storage") or {}
    project_root = root / project
    return (
        project_root / str(storage.get("project_state_filename", "state.json")),
        project_root / str(storage.get("journal_filename", "audit.jsonl")),
        project_root / str(storage.get("snapshot_directory", "snapshots")),
        project_root / str(storage.get("checkpoint_directory", "checkpoints")),
    )


def make_event(project: str, sequence: int, event_type: str, actor: str, previous: str | None,
               payload: dict[str, Any], references: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    event = {
        "schema": EVENT_SCHEMA,
        "project": project,
        "sequence": sequence,
        "event_id": "evt-" + uuid.uuid4().hex,
        "event_type": event_type,
        "actor": actor,
        "observed_at": now_iso(),
        "previous_event_digest": previous,
        "payload": payload,
        "references": references or [],
    }
    event["event_digest"] = digest(event)
    return event


def read_events(journal: Path) -> list[dict[str, Any]]:
    if not journal.exists():
        return []
    events: list[dict[str, Any]] = []
    with journal.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"JOURNAL_JSON_INVALID=line:{lineno}:{exc.msg}")
            if not isinstance(item, dict):
                raise SystemExit(f"JOURNAL_EVENT_NOT_OBJECT=line:{lineno}")
            events.append(item)
    return events


def verify_events(events: list[dict[str, Any]], project: str) -> list[str]:
    errors: list[str] = []
    previous: str | None = None
    expected_sequence = 1
    for event in events:
        seq = event.get("sequence")
        if event.get("schema") != EVENT_SCHEMA:
            errors.append(f"SCHEMA:{seq}")
        if event.get("project") != project:
            errors.append(f"PROJECT:{seq}")
        if seq != expected_sequence:
            errors.append(f"SEQUENCE:expected={expected_sequence}:actual={seq}")
        if event.get("previous_event_digest") != previous:
            errors.append(f"CHAIN:{seq}")
        declared = event.get("event_digest")
        unsigned = dict(event)
        unsigned.pop("event_digest", None)
        actual = digest(unsigned)
        if declared != actual:
            errors.append(f"DIGEST:{seq}")
        previous = declared
        expected_sequence += 1
    return errors


def rebuild(project: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    current: dict[str, Any] | None = None
    created_at = now_iso()
    for event in events:
        payload = event.get("payload") or {}
        if event.get("event_type") == "PROJECT_INITIALIZED":
            current = deepcopy(payload.get("state") or empty_state(project))
            created_at = event.get("observed_at") or created_at
        elif "state_patch" in payload:
            if current is None:
                raise SystemExit("REBUILD_MISSING_INITIAL_EVENT")
            current = merge_patch(current, payload["state_patch"])
    if current is None:
        raise SystemExit("REBUILD_EMPTY_JOURNAL")
    last = events[-1]
    return {
        "schema": STATE_SCHEMA,
        "project": project,
        "version": len(events),
        "created_at": created_at,
        "updated_at": last.get("observed_at") or now_iso(),
        "last_event_sequence": last.get("sequence", 0),
        "last_event_digest": last.get("event_digest"),
        "state": current,
    }


def init_project(root: Path, project: str, policy: dict[str, Any], actor: str, initial: dict[str, Any] | None) -> None:
    with mutation_lock(root, project):
        state_path, journal, snapshots, checkpoints = paths(root, project, policy)
        if state_path.exists() or journal.exists():
            raise SystemExit(f"PROJECT_STATE_ALREADY_EXISTS={project}")
        snapshots.mkdir(parents=True, exist_ok=True)
        checkpoints.mkdir(parents=True, exist_ok=True)
        state = empty_state(project)
        if initial:
            state = merge_patch(state, initial)
        event = make_event(project, 1, "PROJECT_INITIALIZED", actor, None, {"state": state})
        append_jsonl(journal, event)
        projection = {
            "schema": STATE_SCHEMA,
            "project": project,
            "version": 1,
            "created_at": event["observed_at"],
            "updated_at": event["observed_at"],
            "last_event_sequence": 1,
            "last_event_digest": event["event_digest"],
            "state": state,
        }
        atomic_json(state_path, projection)
    print(f"CONTROL_PLANE_INIT=OK:{project}")
    print(f"STATE={state_path}")
    print(f"JOURNAL={journal}")


def record_event(root: Path, project: str, policy: dict[str, Any], event_type: str, actor: str,
                 payload: dict[str, Any], patch: dict[str, Any] | None, refs: list[dict[str, Any]] | None,
                 expected_version: int | None = None, expected_head: str | None = None) -> None:
    allowed = set(policy.get("event_types") or [])
    if event_type not in allowed:
        raise SystemExit(f"EVENT_TYPE_NOT_ALLOWED={event_type}")
    with mutation_lock(root, project):
        state_path, journal, _snapshots, _checkpoints = paths(root, project, policy)
        projection = load_json(state_path)
        if projection.get("schema") != STATE_SCHEMA or projection.get("project") != project:
            raise SystemExit("STATE_IDENTITY_INVALID")
        events = read_events(journal)
        errors = verify_events(events, project)
        if errors:
            raise SystemExit("JOURNAL_INVALID=" + ",".join(errors))
        if projection.get("last_event_sequence") != len(events):
            raise SystemExit("PROJECTION_JOURNAL_SEQUENCE_MISMATCH")
        if events and projection.get("last_event_digest") != events[-1].get("event_digest"):
            raise SystemExit("PROJECTION_JOURNAL_DIGEST_MISMATCH")
        if expected_version is not None and int(projection.get("version", 0)) != expected_version:
            raise SystemExit(f"EXPECTED_VERSION_MISMATCH=expected:{expected_version}:actual:{projection.get('version')}")
        if expected_head is not None and str(projection.get("last_event_digest") or "") != expected_head:
            raise SystemExit(f"EXPECTED_HEAD_MISMATCH=expected:{expected_head}:actual:{projection.get('last_event_digest')}")

        event_payload = deepcopy(payload)
        next_state = deepcopy(projection["state"])
        if patch is not None:
            event_payload["state_patch"] = patch
            next_state = merge_patch(next_state, patch)
        sequence = len(events) + 1
        event = make_event(project, sequence, event_type, actor, projection.get("last_event_digest"), event_payload, refs)
        append_jsonl(journal, event)

        updated = deepcopy(projection)
        updated["version"] = int(projection.get("version", 0)) + 1
        updated["updated_at"] = event["observed_at"]
        updated["last_event_sequence"] = sequence
        updated["last_event_digest"] = event["event_digest"]
        updated["state"] = next_state
        atomic_json(state_path, updated)

    print(f"EVENT_RECORDED={event_type}")
    print(f"EVENT_SEQUENCE={sequence}")
    print(f"EVENT_DIGEST={event['event_digest']}")
    print(f"PROJECTION_VERSION={updated['version']}")


def snapshot(root: Path, project: str, policy: dict[str, Any], actor: str, checkpoint: bool) -> None:
    state_path, _journal, snapshots, checkpoints = paths(root, project, policy)
    projection = load_json(state_path)
    target_dir = checkpoints if checkpoint else snapshots
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"{stamp}-v{projection.get('version')}.json"
    atomic_json(target, projection)
    d = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    event_type = "CHECKPOINT_CREATED" if checkpoint else "SNAPSHOT_CREATED"
    record_event(
        root, project, policy, event_type, actor,
        {"snapshot": str(target), "snapshot_digest": d, "projection_version": projection.get("version")},
        None,
        [{"kind": "file", "value": str(target), "digest": d}],
        expected_version=int(projection.get("version", 0)),
        expected_head=str(projection.get("last_event_digest") or ""),
    )
    print(f"{'CHECKPOINT' if checkpoint else 'SNAPSHOT'}={target}")


def verify_project(root: Path, project: str, policy: dict[str, Any]) -> None:
    state_path, journal, _snapshots, _checkpoints = paths(root, project, policy)
    projection = load_json(state_path)
    events = read_events(journal)
    errors = verify_events(events, project)
    rebuilt = rebuild(project, events) if not errors else None
    if projection.get("schema") != STATE_SCHEMA:
        errors.append("PROJECTION_SCHEMA")
    if projection.get("project") != project:
        errors.append("PROJECTION_PROJECT")
    if rebuilt and projection.get("state") != rebuilt.get("state"):
        errors.append("PROJECTION_STATE_DIVERGED")
    if rebuilt and projection.get("last_event_digest") != rebuilt.get("last_event_digest"):
        errors.append("PROJECTION_HEAD_DIVERGED")
    if rebuilt and int(projection.get("version", -1)) != int(rebuilt.get("version", -2)):
        errors.append("PROJECTION_VERSION_DIVERGED")
    print(f"PROJECT={project}")
    print(f"EVENTS={len(events)}")
    print(f"VERSION={projection.get('version')}")
    print(f"JOURNAL_CHAIN={'OK' if not errors else 'FAIL'}")
    if errors:
        print("ERRORS=" + ",".join(sorted(set(errors))))
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--root", type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--project", required=True)
    p_init.add_argument("--actor", default="chacha-dev-architect")
    p_init.add_argument("--initial", type=Path)

    p_show = sub.add_parser("show")
    p_show.add_argument("--project", required=True)

    p_record = sub.add_parser("record")
    p_record.add_argument("--project", required=True)
    p_record.add_argument("--event-type", required=True)
    p_record.add_argument("--actor", required=True)
    p_record.add_argument("--payload", type=Path)
    p_record.add_argument("--patch", type=Path)
    p_record.add_argument("--references", type=Path)
    p_record.add_argument("--expected-version", type=int)
    p_record.add_argument("--expected-head")

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--project", required=True)

    p_rebuild = sub.add_parser("rebuild")
    p_rebuild.add_argument("--project", required=True)

    p_snap = sub.add_parser("snapshot")
    p_snap.add_argument("--project", required=True)
    p_snap.add_argument("--actor", default="chacha-dev-architect")

    p_check = sub.add_parser("checkpoint")
    p_check.add_argument("--project", required=True)
    p_check.add_argument("--actor", default="chacha-dev-architect")

    args = parser.parse_args()
    policy = load_json(args.policy)
    if policy.get("schema") != POLICY_SCHEMA:
        raise SystemExit(f"POLICY_SCHEMA_INVALID={policy.get('schema')}")
    configured_root = Path(str((policy.get("storage") or {}).get("runtime_root", "/opt/chacha-dev/runtime/state")))
    root = args.root or configured_root

    if args.cmd == "init":
        init_project(root, args.project, policy, args.actor, load_json(args.initial) if args.initial else None)
    elif args.cmd == "show":
        state_path, _j, _s, _c = paths(root, args.project, policy)
        print(json.dumps(load_json(state_path), indent=2, ensure_ascii=False))
    elif args.cmd == "record":
        payload = load_json(args.payload) if args.payload else {}
        patch = load_json(args.patch) if args.patch else None
        refs_raw = load_json(args.references) if args.references else None
        refs = refs_raw.get("references", []) if refs_raw else None
        record_event(
            root, args.project, policy, args.event_type, args.actor, payload, patch, refs,
            expected_version=args.expected_version, expected_head=args.expected_head,
        )
    elif args.cmd == "verify":
        verify_project(root, args.project, policy)
    elif args.cmd == "rebuild":
        with mutation_lock(root, args.project):
            state_path, journal, _s, _c = paths(root, args.project, policy)
            events = read_events(journal)
            errors = verify_events(events, args.project)
            if errors:
                raise SystemExit("JOURNAL_INVALID=" + ",".join(errors))
            atomic_json(state_path, rebuild(args.project, events))
        print(f"PROJECTION_REBUILT=OK:{state_path}")
    elif args.cmd == "snapshot":
        snapshot(root, args.project, policy, args.actor, False)
    elif args.cmd == "checkpoint":
        snapshot(root, args.project, policy, args.actor, True)


if __name__ == "__main__":
    main()
