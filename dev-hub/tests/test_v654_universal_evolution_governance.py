#!/usr/bin/env python3
from __future__ import annotations
import json,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/"dev-hub/bin";CFG=ROOT/"dev-hub/config";sys.path.insert(0,str(BIN))
import agent_benchmark_adapter_runner as runner
import agent_benchmark_evidence_promoter as promoter
import agent_fleet_observatory as afo
import agent_evolution_controller as aec
import agent_evolution_profile as aep
import agent_observation_bus_health as aobh
import component_evolution_governance as ceg
import importlib.util,subprocess

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

afp=load_module("v654_agent_foundry_planner",BIN/"agent-foundry-planner.py")

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
routing=load(CFG/"agent-routing.v1.json");seven=load(CFG/"seven-agent-final-compromise.v1.json")
project=load(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
fleet_policy=load(CFG/"agent-fleet-observatory.v1.json");evo=load(CFG/"agent-evolution.v1.json")
adapter_cfg=load(CFG/"agent-benchmark-adapters.v1.json");profile_policy=load(CFG/"agent-evolution-profile.v1.json")
universal_policy=load(CFG/"universal-evolution-governance.v1.json");lightweight_policy=load(CFG/"lightweight-agent-runtime-profile.v1.json")
inv=aec.build_inventory(routing,seven,[project]);assert inv["agent_count"]==35
runner.tw.snapshot_status=lambda root:{"state":"FRESH","fresh":True,"snapshot_digest":"v654-test"}

fourth=["acceptance-engineer","contract-integrator","integration-architect","ergonomist"]
with tempfile.TemporaryDirectory(prefix="v654-profile-") as td:
    rt=Path(td)
    # Fourth wave real adapters.
    for aid in fourth:
        raw=runner.run(aid,ROOT,"rev-v654",adapter_cfg)
        assert raw["truth_scope"]=="BENCHMARK_ONLY" and raw["production_truth_eligible"] is False,(aid,raw)
        assert raw["verification"]=="BENCHMARK_VERIFIED",(aid,raw)
        path=rt/"agent-evolution/benchmark-evidence"/aid/"rev-v654.json"
        pr=promoter.promote(raw,"rev-v654",adapter_cfg,path);assert pr["promoted"] is True,(aid,pr)
    report=afo.build_report(ROOT,rt,fleet_policy,evo,routing,seven,[project])
    for aid in fourth:
        row=next(x for x in report["agents"] if x["agent_id"]==aid)
        assert row["scorecard"]["measurement_coverage_pct"]>=80.0,(aid,row["scorecard"])
        assert row["scorecard"]["production_measurement_coverage_pct"]==0.0,(aid,row["scorecard"])
        assert row["plan"]["evidence_maturity"]["candidate_evidence_mature"] is False,(aid,row["plan"])
        assert row["plan"]["candidate"]["owner"] is None,(aid,row["plan"])
    # Universal lightweight profiles cover every inventory member without inventing a score.
    idx=aep.build_index(report,routing,seven,[project],adapter_cfg,evo,profile_policy)
    assert idx["profile_count"]==35,idx["profile_count"]
    assert idx["profile_is_performance_score"] is False
    assert all(p["profile_is_performance_score"] is False for p in idx["profiles"])
    assert all(p["evolution"]["active_self_mutation"] is False and p["evolution"]["self_promotion"] is False for p in idx["profiles"])
    byid={p["identity"]["agent_id"]:p for p in idx["profiles"]}
    assert byid["curator"]["measurement"]["strategy"]=="PROFILE_ONLY",byid["curator"]
    assert byid["intendant"]["measurement"]["strategy"]=="PROFILE_ONLY",byid["intendant"]
    radar=byid["technology-radar-agent"]
    assert radar["identity"]["scope"]=="PROJECT" and radar["evolution"]["scope"]=="PROJECT_LOCAL",radar
    assert radar["evolution"]["platform_global_promotion_forbidden"] is True,radar
    assert byid["technology-watch-agent"]["measurement"]["next_action"]=="RUN_EXECUTABLE_BENCHMARK",byid["technology-watch-agent"]
    outroot=rt/"agent-evolution/profiles";aep.write_profiles(outroot,idx)
    assert (outroot/"index.json").is_file()

    # Universal component governance: one owner, class-specific controls, no fake agent scorecards.
    cg=ceg.build_index(idx,load(CFG/"technology-core-watch.v1.json"),load(CFG/"provider-adapters.v1.json"),
                       load(CFG/"mcp-provider-catalog.v1.json"),load(CFG/"project-embedded-assurance.v1.json"),universal_policy)
    assert cg["component_count"]>70,cg["component_count"]
    assert cg["single_evolution_owner_per_component"] is True,cg
    assert cg["no_parallel_governance_engines"] is True,cg
    assert cg["lightweight_agents_do_not_duplicate_central_intelligence"] is True,cg
    cby={x["component_id"]:x for x in cg["components"]}
    assert cby["core:central-orchestrator"]["governance_class"]=="CORE_PLATFORM_COMPONENT",cby["core:central-orchestrator"]
    assert cby["core:central-orchestrator"]["evolution_owner"]=="branch-foundry",cby["core:central-orchestrator"]
    assert cby["adapter:playwright-mcp-adapter"]["governance_class"]=="CONNECTOR_ADAPTER",cby["adapter:playwright-mcp-adapter"]
    assert cby["adapter:playwright-mcp-adapter"]["agent_scorecard"] is False,cby["adapter:playwright-mcp-adapter"]
    assert cby["integration:playwright-mcp"]["sources"]==["mcp-provider-catalog","provider-adapters"],cby["integration:playwright-mcp"]
    assert cg["passive_artifact_governance"]["inherit_owner"] is True,cg["passive_artifact_governance"]
    assert cg["passive_artifact_governance"]["independent_agent_forbidden"] is True,cg["passive_artifact_governance"]
    embedded_rows=[x for x in cg["components"] if x["component_id"].startswith("embedded-probe:")]
    assert len(embedded_rows)==5,embedded_rows
    assert all(x["governance_class"]=="LIGHTWEIGHT_EMBEDDED_AGENT" for x in embedded_rows),embedded_rows

    # Agent Foundry automatically gives every newly created agent the evolution contract.
    pkg={"id":"v654-light","domain":"custom-domain","kind":"primary",
         "capabilities":["custom-a","custom-b","custom-c","custom-d","custom-e"],"roles":[],"toolchain":[]}
    foundry=afp.decide_package(pkg,routing,load(CFG/"agent-foundry.v1.json"),"v654")
    assert foundry["decision"]=="CREATE_EPHEMERAL_AGENT",foundry
    manifest=foundry["manifest"]
    assert manifest["evolution_profile"]["governance_class"]=="LIGHTWEIGHT_PROJECT_AGENT",manifest
    assert manifest["evolution_profile"]["active_self_mutation"] is False and manifest["evolution_profile"]["self_promotion"] is False,manifest
    light=manifest["lightweight_runtime_profile"]
    assert light["governance_class"]=="LIGHTWEIGHT_PROJECT_AGENT",light
    assert set(light["centralized_controls"])==set(lightweight_policy["centralized_controls"]),light
    assert "technology-watch-engine" in light["local_forbidden_controls"],light

    # Embedded application probes inherit the lightweight contract; heavy intelligence remains central.
    dummy_runtime=rt/"dummy-runtime.py";dummy_relay=rt/"dummy-relay.py";dummy_client=rt/"dummy-client.mjs"
    dummy_runtime.write_text("#!/usr/bin/env python3\n",encoding="utf-8");dummy_relay.write_text("#!/usr/bin/env python3\n",encoding="utf-8");dummy_client.write_text("// v654\n",encoding="utf-8")
    bundle=rt/"embedded"
    subprocess.run([sys.executable,str(BIN/"project-embedded-assurance.py"),
      "--project-id","v654-project","--policy",str(CFG/"project-embedded-assurance.v1.json"),
      "--runtime-script",str(dummy_runtime),"--relay-script",str(dummy_relay),"--client-runtime",str(dummy_client),
      "--output-dir",str(bundle)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    em=load(bundle/"embedded-assurance.json");lp=em["lightweight_agent_runtime_profile"]
    assert lp["governance_class"]=="LIGHTWEIGHT_EMBEDDED_AGENT",lp
    assert lp["technology_watch_local"] is False and lp["logician_local"] is False and lp["foundry_local"] is False,lp
    assert all(x["runtime_profile"]=="LIGHTWEIGHT_EMBEDDED_AGENT" and x["central_governance"] is True for x in em["local_probes"].values()),em["local_probes"]
    # Bus health fingerprints the profile policy and must request reassessment if that policy later changes.
    minrepo=rt/"repo";shutil.copytree(ROOT/"dev-hub/config",minrepo/"dev-hub/config")
    (minrepo/"dev-hub/projects/wfgg-radar").mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json",minrepo/"dev-hub/projects/wfgg-radar/project-agent-registry.v1.json")
    buspolicy=load(CFG/"agent-observation-bus.v1.json");state=rt/"bus-state.json";health=rt/"bus-health.json"
    first=aobh.assess(minrepo,rt/"bus-runtime",buspolicy,state,health,False)
    assert first["status"]=="PASS",first
    pp=minrepo/"dev-hub/config/agent-evolution-profile.v1.json";pv=load(pp);pv["version"]="1.0.1-test";pp.write_text(json.dumps(pv)+"\n")
    second=aobh.assess(minrepo,rt/"bus-runtime",buspolicy,state,health,False)
    assert second["status"]=="REASSESS_REQUIRED",second
    assert "AGENT_EVOLUTION_PROFILE_POLICY_CHANGED" in (load(Path(second["reassessment"]["path"]))["trigger_reasons"]),second
    up=minrepo/"dev-hub/config/universal-evolution-governance.v1.json";uv=load(up);uv["version"]="1.0.1-test";up.write_text(json.dumps(uv)+"\n")
    third=aobh.assess(minrepo,rt/"bus-runtime",buspolicy,state,health,False)
    assert "UNIVERSAL_EVOLUTION_GOVERNANCE_POLICY_CHANGED" in (load(Path(third["reassessment"]["path"]))["trigger_reasons"]),third
    lp=minrepo/"dev-hub/config/lightweight-agent-runtime-profile.v1.json";lv=load(lp);lv["version"]="1.0.1-test";lp.write_text(json.dumps(lv)+"\n")
    fourth_health=aobh.assess(minrepo,rt/"bus-runtime",buspolicy,state,health,False)
    assert "LIGHTWEIGHT_AGENT_RUNTIME_PROFILE_CHANGED" in (load(Path(fourth_health["reassessment"]["path"]))["trigger_reasons"]),fourth_health

print("CHACHA_DEV_V654_UNIVERSAL_PROFILE_35=PASS")
print("CHACHA_DEV_V654_PROFILE_IS_PERFORMANCE_SCORE=NO")
print("CHACHA_DEV_V654_PROJECT_RADAR_SCOPE=PROJECT_LOCAL")
print("CHACHA_DEV_V654_CURATOR_INTENDANT_PROFILE_ONLY=PASS")
print("CHACHA_DEV_V654_ACCEPTANCE_ENGINEER_ADAPTER=PASS")
print("CHACHA_DEV_V654_CONTRACT_INTEGRATOR_ADAPTER=PASS")
print("CHACHA_DEV_V654_INTEGRATION_ARCHITECT_ADAPTER=PASS")
print("CHACHA_DEV_V654_ERGONOMIST_ADAPTER=PASS")
print("CHACHA_DEV_V654_FOURTH_WAVE_CANDIDATE_MATERIALIZATION=BLOCKED")
print("CHACHA_DEV_V654_BUS_PROFILE_POLICY_REASSESSMENT=PASS")
print("CHACHA_DEV_V654_AUTOMATIC_EXTERNAL_SPEND_EUR=0")

print("CHACHA_DEV_V654_UNIVERSAL_COMPONENT_GOVERNANCE=PASS")
print("CHACHA_DEV_V654_SINGLE_EVOLUTION_OWNER=PASS")
print("CHACHA_DEV_V654_CONNECTOR_AGENT_SCORECARD=NO")
print("CHACHA_DEV_V654_PASSIVE_ARTIFACT_INHERITS_OWNER=PASS")
print("CHACHA_DEV_V654_FUTURE_AGENT_INHERITANCE=PASS")
print("CHACHA_DEV_V654_LIGHTWEIGHT_EMBEDDED_PROFILE=PASS")
print("CHACHA_DEV_V654_LOCAL_TECH_WATCH_LOGICIAN_FOUNDRY_DUPLICATION=NO")
