#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
path=ROOT/"dev-hub/bin/branch-blueprint-optimizer.py"
spec=importlib.util.spec_from_file_location("v807_optimizer",path)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
policy=json.loads((ROOT/"dev-hub/config/branch-foundry.v1.json").read_text(encoding="utf-8"))
pre={"implementation_allowed":True,"mode":"multi_domain_change"}

heavy_review={
  "id":"review:cybersecurity","kind":"review","domain":"cybersecurity",
  "capabilities":["security-review","security-scan-js"]
}
out=mod.optimize(heavy_review,pre,policy,{"decision":"REUSE_EXISTING_AGENT"})
assert out["state"]=="READY",out
assert out["chosen"]["id"]=="lean-ephemeral",out["chosen"]
assert out["chosen"]["branch_mode"]=="MATERIALIZE_EPHEMERAL_BRANCH"
assert out["chosen_cost"]["external_spend_eur"]==0

light_review={
  "id":"review:documentation","kind":"review","domain":"documentation",
  "capabilities":["documentation"]
}
out2=mod.optimize(light_review,pre,policy,{"decision":"REUSE_EXISTING_AGENT"})
assert out2["state"]=="READY",out2
assert out2["chosen"]["id"]=="virtual-shared",out2["chosen"]

forced_review={
  "id":"review:qa","kind":"review","domain":"qa","requires_runtime_review":True,
  "capabilities":["test-strategy"]
}
out3=mod.optimize(forced_review,pre,policy,{"decision":"REUSE_EXISTING_AGENT"})
assert out3["state"]=="READY",out3
assert out3["chosen"]["id"]=="lean-ephemeral",out3["chosen"]
assert out3["chosen_cost"]["external_spend_eur"]==0

print("CHACHA_DEV_V807_HEAVY_REVIEW_EPHEMERAL=PASS")
print("CHACHA_DEV_V807_LIGHT_REVIEW_VIRTUAL=PASS")
print("CHACHA_DEV_V807_EXPLICIT_RUNTIME_REVIEW_EPHEMERAL=PASS")
print("CHACHA_DEV_V807_NO_PERMISSION_EXPANSION=PASS")
print("CHACHA_DEV_V807_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
