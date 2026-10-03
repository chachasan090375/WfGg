#!/usr/bin/env python3
import json,sys,tempfile,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))
import canonical_component_registry as ccr
import agent_fleet_observatory as afo
import component_registry_reconciler as reconciler

def load(p): return json.loads(Path(p).read_text())
reg_policy=load(ROOT/"dev-hub/config/canonical-component-registry.v1.json")
canonical=ccr.build_registry(ROOT,reg_policy)
assert canonical["component_count"]>=190,canonical["component_count"]
expected_fleet_ids={str(x.get("name")) for x in canonical.get("components") or [] if x.get("fleet_required") is True}
assert canonical["fleet_projection_count"]==len(expected_fleet_ids),canonical["fleet_projection_count"]
with tempfile.TemporaryDirectory() as td:
    runtime=Path(td)/"runtime"; runtime.mkdir()
    # Fleet projection itself must be canonical even when no historical runtime evidence exists.
    report=afo.build_report(ROOT,runtime,
      load(ROOT/"dev-hub/config/agent-fleet-observatory.v1.json"),
      load(ROOT/"dev-hub/config/agent-evolution.v1.json"),
      load(ROOT/"dev-hub/config/agent-routing.v1.json"),
      load(ROOT/"dev-hub/config/seven-agent-final-compromise.v1.json"),
      [load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")],canonical)
    ids={x.get("agent_id") for x in report.get("agents") or []}
    assert ids==expected_fleet_ids,(len(ids),len(expected_fleet_ids),sorted(ids^expected_fleet_ids))
    assert "conversation-reasoner" in ids,ids
    assert "human-behavior-center" in ids,ids
    # A compliant 3-release platform must reconcile without fleet drift or release overage.
    platform=Path(td)/"platform"; releases=platform/"releases"; releases.mkdir(parents=True)
    active=None
    for n in range(3):
        d=releases/(f"r{n}");d.mkdir();(d/".revision").write_text(str(n)*40)
        if n==0: active=d
    (platform/"current").symlink_to(active)
    recon=reconciler.reconcile(ROOT,canonical,reg_policy,report,platform)
    codes=[x.get("code") for x in recon.get("issues") or []]
    assert "FLEET_MISSING" not in codes,codes
    assert "RELEASE_OVERAGE" not in codes,codes
# Daily cycle must use the same canonical object for both Fleet builds.
src=(ROOT/"dev-hub/bin/agent_evolution_daily_cycle.py").read_text()
assert 'canonical=ccr.build_registry(root,canonical_policy)' in src
assert src.count('afo.build_report(root,runtime,fp,ep,routing,seven,[project],canonical)')==2
print("CHACHA_DEV_AUTONOMY_CANONICAL_FLEET_PROJECTION=PASS")
