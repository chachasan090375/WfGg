#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "dev-hub/bin/sentinel-sandbox-materializer.py"


def run(argv: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(argv, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, check=False)
    if p.returncode != 0:
        raise AssertionError((argv, p.returncode, p.stdout, p.stderr))
    return p.stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


with tempfile.TemporaryDirectory() as td:
    t = Path(td)
    source = t / "source"
    source.mkdir()
    run(["git", "init", "-q"], source)
    run(["git", "config", "user.name", "ChaCha DEV Test"], source)
    run(["git", "config", "user.email", "test@local.invalid"], source)
    write(source / "dev-hub/guardian/worker.js", "export const marker='baseline';\n")
    write(source / "dev-hub/tests/test_demo.py", "print('DEMO_TEST_PASS')\n")
    run(["git", "add", "-A"], source)
    run(["git", "commit", "-q", "-m", "fixture base"], source)
    source_head = run(["git", "rev-parse", "HEAD"], source)

    # Authoritative runtime-only resources intentionally remain untracked.
    write(source / "dev-hub/config/runtime-only.json", '{"required":true}\n')
    write(source / "dev-hub/bin/runtime_helper.py", "VALUE='runtime-only'\n")

    overlay = t / "candidate-worker.js"
    write(overlay, "export const marker='candidate';\n")
    overlay_manifest = t / "overlay.json"
    overlay_manifest.write_text(json.dumps({
        "schema": "chacha.dev/sentinel-sandbox-overlay-manifest/v1",
        "overlays": [{
            "source": str(overlay),
            "target": "dev-hub/guardian/worker.js",
            "sha256": digest(overlay),
        }],
    }), encoding="utf-8")
    sandbox = t / "sandbox"
    receipt = t / "receipt.json"
    out = run([
        "python3", str(TOOL),
        "--source-root", str(source),
        "--sandbox", str(sandbox),
        "--overlay-manifest", str(overlay_manifest),
        "--receipt", str(receipt),
        "--apply",
    ], ROOT)
    assert "CHACHA_DEV_SENTINEL_SANDBOX_MATERIALIZER=PASS" in out
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert data["source_head"] == source_head
    assert data["candidate_delta"] == ["dev-hub/guardian/worker.js"]
    assert data["production_mutation"] is False
    assert data["automatic_external_spend_eur"] == 0
    assert (sandbox / "dev-hub/config/runtime-only.json").is_file()
    assert (sandbox / "dev-hub/bin/runtime_helper.py").is_file()
    assert (sandbox / "dev-hub/guardian/worker.js").read_text() == overlay.read_text()
    assert run(["git", "status", "--porcelain"], sandbox) == ""
    changed = run(["git", "diff", "--name-only", data["bundle_base_head"], data["candidate_head"]], sandbox)
    assert changed.strip() == "dev-hub/guardian/worker.js"
    assert run(["git", "ls-files", "dev-hub/config/runtime-only.json"], sandbox).strip()
    assert run(["git", "ls-files", "dev-hub/bin/runtime_helper.py"], sandbox).strip()
    assert (source / "dev-hub/guardian/worker.js").read_text() == "export const marker='baseline';\n"

probe = json.loads(run(["python3", str(TOOL), "probe"], ROOT))
assert probe["schema"] == "chacha.dev/task-result/v1"
assert probe["status"] == "OK"
assert probe["producer"] == "sentinel-sandbox-materializer"
assert probe["verification"]["status"] == "UNVERIFIED"
assert probe["automatic_external_spend_eur"] == 0

print("CHACHA_DEV_SENTINEL_SANDBOX_MATERIALIZER_TEST=PASS")
print("CHACHA_DEV_SENTINEL_ATOMIC_SOURCE_BUNDLE=PASS")
print("CHACHA_DEV_SENTINEL_CANDIDATE_DELTA_ISOLATION=PASS")
print("CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
