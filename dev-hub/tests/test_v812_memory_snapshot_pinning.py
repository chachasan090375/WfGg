#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
sys.path.insert(0,str(BIN))

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

orch=load_module("v812_orch",BIN/"autonomous-project-orchestrator.py")
council=load_module("v812_council",BIN/"architecture-decision-council.py")

def memory(digest):
    return {
      "schema":"chacha.dev/central-memory-assimilation/v1",
      "snapshot_digest":digest,
      "generated_at":"2026-09-25T15:00:00Z",
      "state_counts":{},
      "trusted_generalizable_count":0,
      "single_observation_never_trusted":True,
      "technology_revalidation_required_before_reuse":True,
      "component_confidence":{"available":True},
      "reuse_catalog":{"branches":[],"architectures":[]}
    }

with tempfile.TemporaryDirectory(prefix="v812-memory-pin-") as td:
    td=Path(td)
    live=td/"live.json"
    pinned=td/"pinned.json"
    live.write_text(json.dumps(memory("digest-A"))+"\n",encoding="utf-8")
    got=orch.pin_memory_snapshot(live,pinned)
    assert got==pinned
    assert json.loads(pinned.read_text())["snapshot_digest"]=="digest-A"

    # Central memory evolves after the run snapshot was pinned.
    live.write_text(json.dumps(memory("digest-B"))+"\n",encoding="utf-8")
    assert json.loads(live.read_text())["snapshot_digest"]=="digest-B"

    # The same run must still evaluate against the immutable pinned generation.
    used=council.central_memory_assimilation(pinned)
    assert used["available"] is True
    assert used["snapshot_digest"]=="digest-A",used

src=(BIN/"autonomous-project-orchestrator.py").read_text(encoding="utf-8")
assert 'central-memory-snapshot-final.json' in src
assert '"--memory-snapshot",memory_snapshot' in src
assert src.count('"--memory-snapshot",memory_snapshot')>=2
csrc=(BIN/"architecture-decision-council.py").read_text(encoding="utf-8")
assert 'ap.add_argument("--memory-snapshot",type=Path)' in csrc
assert 'central_memory_assimilation(a.memory_snapshot)' in csrc

print("CHACHA_DEV_V812_IMMUTABLE_MEMORY_SNAPSHOT=PASS")
print("CHACHA_DEV_V812_LIVE_MEMORY_CAN_ADVANCE=PASS")
print("CHACHA_DEV_V812_COUNCIL_USES_PINNED_GENERATION=PASS")
print("CHACHA_DEV_V812_COMPARATIVE_COUNCIL_PINNED=PASS")
print("CHACHA_DEV_V812_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
