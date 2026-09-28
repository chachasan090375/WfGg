#!/usr/bin/env python3
import importlib.util,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"dev-hub/bin"))
SPEC=importlib.util.spec_from_file_location("asm",ROOT/"dev-hub/bin/autonomy-self-model.py")
asm=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(asm)
policy=json.loads((ROOT/"dev-hub/config/autonomy-self-model.v1.json").read_text())
assert policy["invariants"]["read_only"] is True
assert policy["invariants"]["no_mutation_authority"] is True
row=asm.issue_view({"code":"FLEET_MISSING","severity":"HIGH","subject":"x"},policy)
assert row["owner"]=="agent-fleet-observatory",row
assert row["recommended_action"]=="BACKFILL_FLEET_FROM_CANONICAL_REGISTRY",row
assert row["mutation_authorized"] is False,row
unknown=asm.issue_view({"code":"NEW_UNKNOWN","severity":"HIGH","subject":"x"},policy)
assert unknown["owner"]=="UNRESOLVED",unknown
assert unknown["recommended_action"]=="HUMAN_CLASSIFICATION_REQUIRED",unknown
print("CHACHA_DEV_AUTONOMY_SELF_MODEL_UNIT=PASS")
