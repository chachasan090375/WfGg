#!/usr/bin/env python3
from __future__ import annotations
import copy,json,os,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
CFG=ROOT/"dev-hub/config"

def save(path:Path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")

def load(path:Path):
    return json.loads(path.read_text(encoding="utf-8"))

def run(cmd,*,env=None):
    p=subprocess.run(cmd,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     env=env,check=False)
    assert p.returncode==0,(p.stdout,p.stderr)
    return p.stdout

with tempfile.TemporaryDirectory(prefix="v644-freshness-") as raw:
    td=Path(raw)
    cap="v644-durable-read"
    aid="adopt-v644-durable-read-0001"
    provider="playwright-mcp"
    adapter="playwright-mcp-adapter"
    durable=td/"durable.json"
    save(durable,{
      "schema":"chacha.dev/durable-capability-adoptions/v1","version":"1.0.0",
      "capabilities":{cap:{
        "class":"execution","providers":[{"id":provider,"status":"ADOPT","health":"runtime-check",
          "cost_class":"included","scope":"platform-durable","fallback":[]}],
        "generated_by":"durable-capability-adoption","promotion_state":"ADOPT",
        "selected_adapter":adapter,"adoption_id":aid,"automatic_external_spend_eur":0
      }},
      "providers":{},"adapters":{},
      "adoptions":{aid:{
        "adoption_id":aid,"status":"ADOPTED","project_id":"project-origin",
        "capability":cap,"provider":provider,"adapter":adapter,
        "provider_origin":"BASE_EXISTING","source_kind":"EXISTING_PROVIDER",
        "production_capable":False,"network_access":False,"credentials_required":False,
        "automatic_external_spend_eur":0
      }},"history":[],"automatic_external_spend_eur":0
    })
    base_caps=td/"base-caps.json";base_providers=td/"base-providers.json"
    save(base_caps,{"schema":"chacha.dev/capability-registry/v1","version":"1.0.0","capabilities":{}})
    save(base_providers,{
      "schema":"chacha.dev/provider-adapters/v1","version":"1.0.0",
      "providers":{provider:{"adapter":adapter}},
      "adapters":{adapter:{"status":"ENABLED"}}
    })
    trust=td/"trust.json"
    save(trust,{"schema":"chacha.dev/component-confidence-snapshot/v1","items":[{
      "component_kind":"capability","component_id":cap,"version":aid,
      "state":"TRUSTED","reuse_advisory_eligible":True
    }]})

    # Build a real Technology Watch snapshot, then prove current revalidation.
    sys.path.insert(0,str(BIN))
    import technology_watch_runtime as tw
    tech=td/"technology-watch.json"
    save(tech,tw.build_snapshot(ROOT,targeted=False))
    env=dict(os.environ);env["CHACHA_TECHNOLOGY_WATCH_SNAPSHOT"]=str(tech)
    fresh=td/"fresh.json"
    out=run([sys.executable,str(BIN/"capability-trust-freshness.py"),
      "--repo-root",str(ROOT),"--registry",str(durable),
      "--policy",str(CFG/"capability-trust-freshness.v1.json"),"--output",str(fresh)],env=env)
    assert "CHACHA_DEV_V644_TRUST_FRESHNESS_PROOF=PASS" in out,out
    proof=load(fresh)
    assert proof["status"]=="PASS" and proof["bindings"]==[{"capability":cap,"adoption_id":aid}],proof
    assert proof["technology_watch"]["revalidation_mode"]=="CURRENT_FRESH_SNAPSHOT",proof

    merged_caps=td/"merged.json";merged_providers=td/"merged-providers.json"
    out=run([sys.executable,str(BIN/"durable-capability-registry.py"),"merge",
      "--base-capability-registry",str(base_caps),"--base-provider-registry",str(base_providers),
      "--registry",str(durable),"--output-capabilities",str(merged_caps),
      "--output-providers",str(merged_providers),"--trust-snapshot",str(trust),
      "--trust-policy",str(CFG/"capability-trust-graduation.v1.json"),
      "--trust-freshness",str(fresh),"--trust-freshness-policy",str(CFG/"capability-trust-freshness.v1.json")])
    active=load(merged_caps)["capabilities"][cap]
    assert active["trust_state"]=="TRUSTED",active
    assert active["trust_freshness_status"]=="FRESH",active
    assert active["trust_freshness_does_not_grant_permissions"] is True,active

    # Missing freshness blocks fast reuse but does not mutate historical trust.
    blocked_caps=td/"blocked.json";blocked_providers=td/"blocked-providers.json"
    out_missing=run([sys.executable,str(BIN/"durable-capability-registry.py"),"merge",
      "--base-capability-registry",str(base_caps),"--base-provider-registry",str(base_providers),
      "--registry",str(durable),"--output-capabilities",str(blocked_caps),
      "--output-providers",str(blocked_providers),"--trust-snapshot",str(trust),
      "--trust-policy",str(CFG/"capability-trust-graduation.v1.json"),
      "--trust-freshness-policy",str(CFG/"capability-trust-freshness.v1.json")])
    assert cap not in load(blocked_caps)["capabilities"],load(blocked_caps)
    assert "CAPABILITY_TRUST_REVALIDATION_REQUIRED" in out_missing,out_missing
    assert load(trust)["items"][0]["state"]=="TRUSTED"

    # Proof is exact to adoption_id; a replay against another adoption cannot unlock reuse.
    wrong=copy.deepcopy(proof);wrong["bindings"][0]["adoption_id"]="different-adoption"
    wrong_path=td/"wrong.json";save(wrong_path,wrong)
    wrong_caps=td/"wrong-caps.json";wrong_providers=td/"wrong-providers.json"
    out_wrong=run([sys.executable,str(BIN/"durable-capability-registry.py"),"merge",
      "--base-capability-registry",str(base_caps),"--base-provider-registry",str(base_providers),
      "--registry",str(durable),"--output-capabilities",str(wrong_caps),
      "--output-providers",str(wrong_providers),"--trust-snapshot",str(trust),
      "--trust-policy",str(CFG/"capability-trust-graduation.v1.json"),
      "--trust-freshness",str(wrong_path),"--trust-freshness-policy",str(CFG/"capability-trust-freshness.v1.json")])
    assert cap not in load(wrong_caps)["capabilities"],load(wrong_caps)
    assert "CAPABILITY_TRUST_REVALIDATION_BINDING_MISSING" in out_wrong,out_wrong

    # Freshness never overrides negative trust.
    negative=copy.deepcopy(load(trust));negative["items"][0]["state"]="QUARANTINED"
    negative_path=td/"negative.json";save(negative_path,negative)
    negative_caps=td/"negative-caps.json";negative_providers=td/"negative-providers.json"
    out_negative=run([sys.executable,str(BIN/"durable-capability-registry.py"),"merge",
      "--base-capability-registry",str(base_caps),"--base-provider-registry",str(base_providers),
      "--registry",str(durable),"--output-capabilities",str(negative_caps),
      "--output-providers",str(negative_providers),"--trust-snapshot",str(negative_path),
      "--trust-policy",str(CFG/"capability-trust-graduation.v1.json"),
      "--trust-freshness",str(fresh),"--trust-freshness-policy",str(CFG/"capability-trust-freshness.v1.json")])
    assert cap not in load(negative_caps)["capabilities"],load(negative_caps)
    assert "CAPABILITY_TRUST_BLOCKED:QUARANTINED" in out_negative,out_negative

    # A stale Technology Watch snapshot triggers a targeted zero-spend refresh and still yields PASS.
    stale=load(tech);stale["generated_at"]="2000-01-01T00:00:00Z";save(tech,stale)
    refreshed=td/"refreshed.json"
    out_refresh=run([sys.executable,str(BIN/"capability-trust-freshness.py"),
      "--repo-root",str(ROOT),"--registry",str(durable),
      "--policy",str(CFG/"capability-trust-freshness.v1.json"),"--output",str(refreshed)],env=env)
    refreshed_v=load(refreshed)
    assert refreshed_v["technology_watch"]["targeted_refresh_performed"] is True,refreshed_v
    assert refreshed_v["technology_watch"]["revalidation_mode"]=="TARGETED_REFRESH",refreshed_v
    assert refreshed_v["automatic_external_spend_eur"]==0,refreshed_v

print("CHACHA_DEV_V644_TECHNOLOGY_WATCH_FRESH_REVALIDATION=PASS")
print("CHACHA_DEV_V644_TARGETED_REFRESH_ON_STALE=PASS")
print("CHACHA_DEV_V644_EXACT_ADOPTION_BINDING=PASS")
print("CHACHA_DEV_V644_STALE_OR_MISSING_FAST_REUSE_BLOCKED=PASS")
print("CHACHA_DEV_V644_NEGATIVE_TRUST_PRECEDENCE=PASS")
print("CHACHA_DEV_V644_TRUST_HISTORY_PRESERVED=PASS")
print("CHACHA_DEV_V644_TRUST_PERMISSION_ESCALATION=NO")
print("CHACHA_DEV_V644_AUTOMATIC_EXTERNAL_SPEND_EUR=0")
