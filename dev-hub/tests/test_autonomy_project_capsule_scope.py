from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]; BIN=ROOT/"dev-hub/bin"; CFG=ROOT/"dev-hub/config"
sys.path.insert(0,str(BIN))
def mod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
gate=mod("umg",BIN/"universal-materialization-gate.py")
ctrl=mod("crc",BIN/"capsule-runtime-controller.py")
pc=mod("pc",BIN/"project-control.py")
policy=json.loads((CFG/"canonical-component-registry.v1.json").read_text())
def manifest(project="A",scope="PROJECT",ttl=60):
 return {"branch_id":f"{project}:web:primary","project_id":project,"scope":scope,"ttl_seconds":ttl,
  "governance_class":"RUNTIME_INFRASTRUCTURE","owner_foundry":"branch-foundry","materialization_gate_required":True,"automatic_external_spend_eur":0}
ok=gate.check_only(manifest(),policy,{})
assert ok["status"]=="PASS" and ok["component_id"]=="runtime:A:web:primary",ok
for bad,code in [(manifest(project=""),"PROJECT_CAPSULE_PROJECT_ID_REQUIRED"),(manifest(scope="PLATFORM"),"PROJECT_CAPSULE_SCOPE_MUST_BE_PROJECT"),(manifest(ttl=0),"PROJECT_CAPSULE_TTL_REQUIRED")]:
 try: gate.check_only(bad,policy,{})
 except ValueError as e: assert code in str(e),(code,e)
 else: raise AssertionError(code)
with tempfile.TemporaryDirectory(prefix="project-capsules-") as td:
 root=Path(td);dyn=root/"dynamic.json"
 rec=gate.register(manifest("A"),policy,dyn,{})
 gate.transition(dyn,rec["component_id"],"ACTIVE")
 x=json.loads(dyn.read_text()); assert len(x["registrations"])==1 and x["registrations"][0]["project_id"]=="A" and x["registrations"][0]["scope"]=="PROJECT"
 gate.transition(dyn,rec["component_id"],"RETIRED")
 x=json.loads(dyn.read_text()); assert x["registrations"]==[] and x["history"][-1]["project_id"]=="A"
 # Two project runtime registries: teardown A must never touch B.
 for project in ("A","B"):
  pr=root/project;pr.mkdir();(pr/"registry.json").write_text(json.dumps({"schema":"chacha.dev/runtime-capsule-registry/v1","project_id":project,"capsules":[{"project_id":project,"unit":"u-"+project,"workspace":str(pr),"materialization_component_id":"runtime:"+project+":web:primary"}]}))
 calls=[];ctrl.run=lambda *a,**k: SimpleNamespace(returncode=0,stdout="",stderr="");ctrl.active=lambda u:False;ctrl.gate_call=lambda a,m,o,manifest=None,component_id=None:(calls.append(component_id) or {"status":"PASS"})
 args=SimpleNamespace(runtime_root=root,project_id="A",materialization_gate=BIN/"universal-materialization-gate.py",materialization_policy=CFG/"canonical-component-registry.v1.json",dynamic_registry=dyn)
 out=ctrl.teardown(args);assert [r["project_id"] for r in out["results"]]==["A"],out;assert calls==["runtime:A:web:primary"],calls;assert (root/"B"/"registry.json").is_file()
 assert out["teardown_complete"] is True and out["runtime_root_removed"] is True,out
 assert not (root/"A").exists()
# Delivery boundary: TTL is only a fallback; RELEASE->OPERATE requires immediate project-scoped teardown.
seen=[]
pc.teardown_project_ephemeral_capsules=lambda project,policy,repo_root:(seen.append(project) or {"status":"PASS","project_id":project})
assert pc.project_delivery_capsule_teardown_gate("BUILD","VERIFY","A",{},ROOT)["status"]=="NOT_REQUIRED"
assert pc.project_delivery_capsule_teardown_gate("RELEASE","OPERATE","A",{},ROOT)["status"]=="PASS" and seen==["A"]
pc.teardown_project_ephemeral_capsules=lambda project,policy,repo_root:{"status":"BLOCKED","project_id":project}
blocked=pc.project_delivery_capsule_teardown_gate("RELEASE","OPERATE","A",{},ROOT)
assert blocked["status"]=="BLOCKED" and blocked["reason"]=="PROJECT_EPHEMERAL_CAPSULE_TEARDOWN_REQUIRED_BEFORE_OPERATE"
pcsrc=(BIN/"project-control.py").read_text()
assert "capsule_teardown=project_delivery_capsule_teardown_gate(current,target,project,policy,repo_root)" in pcsrc
print("CHACHA_DEV_PROJECT_CAPSULE_SCOPE=PASS")
print("CHACHA_DEV_PROJECT_CAPSULE_CROSS_PROJECT_TEARDOWN_BLOCK=PASS")
print("CHACHA_DEV_PROJECT_CAPSULE_RETIRED_INSTANCE_NOT_ACTIVE=PASS")
