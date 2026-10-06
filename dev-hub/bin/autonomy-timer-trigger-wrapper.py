#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


def load_json(path):
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return None


def snapshot(work):
    out={}

    if not work.exists():
        return out

    for p in work.glob("*/run.json"):
        try:
            st=p.stat()
        except FileNotFoundError:
            continue

        out[str(p)]=(
            st.st_mtime_ns,
            st.st_size
        )

    return out


def atomic_json(path,payload):
    fd,tmp=tempfile.mkstemp(
        prefix=path.name+".",
        suffix=".tmp",
        dir=str(path.parent)
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                payload,
                f,
                indent=2,
                ensure_ascii=False
            )
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp,path)

    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def main():
    ap=argparse.ArgumentParser()

    ap.add_argument(
        "--repo-root",
        type=Path,
        required=True
    )

    ap.add_argument(
        "--runtime-root",
        type=Path,
        required=True
    )

    a=ap.parse_args()

    repo=a.repo_root.resolve()
    runtime=a.runtime_root.resolve()
    work=runtime/"autonomy-core"/"work"

    before=snapshot(work)
    started=time.time_ns()

    runner=(
        repo
        /"dev-hub"
        /"bin"
        /"autonomy-loop-runner.py"
    )

    cp=subprocess.run([
        sys.executable,
        str(runner),
        "--repo-root",
        str(repo),
        "--runtime-root",
        str(runtime)
    ])

    if cp.returncode != 0:
        return cp.returncode

    after=snapshot(work)

    changed=[
        Path(p)
        for p,state in after.items()
        if p not in before
        or before[p] != state
    ]

    if not changed:
        print(
            "TIMER_TRIGGER_PROVENANCE_NO_RUN_CHANGED",
            file=sys.stderr
        )
        return 72

    now=(
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00","Z")
    )

    written=0

    for path in changed:
        payload=load_json(path)

        if not isinstance(payload,dict):
            continue

        payload["trigger"]="timer"

        payload["trigger_provenance"]={
            "schema":
                "chacha.dev/run-trigger-provenance/v1",
            "kind":
                "timer",
            "source":
                "systemd",
            "timer_unit":
                "chacha-dev-autonomy-core.timer",
            "service_unit":
                "chacha-dev-autonomy-core-timer.service",
            "materializer":
                "autonomy-timer-trigger-wrapper",
            "materialized_at":
                now,
            "wrapper_started_epoch_ns":
                started,
            "automatic_external_spend_eur":
                0
        }

        atomic_json(
            path,
            payload
        )

        written+=1

    if written == 0:
        print(
            "TIMER_TRIGGER_PROVENANCE_NO_JSON_WRITTEN",
            file=sys.stderr
        )
        return 73

    print(
        "CHACHA_DEV_TIMER_TRIGGER_PROVENANCE=PASS"
    )
    print(
        "PROVENANCE_RUNS_WRITTEN="
        +str(written)
    )
    print(
        "AUTOMATIC_EXTERNAL_SPEND_EUR=0"
    )

    return 0


if __name__=="__main__":
    raise SystemExit(main())
