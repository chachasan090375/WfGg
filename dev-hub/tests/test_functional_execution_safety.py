"""Local failure-path qualification; no remote services or production state."""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

BIN=Path(__file__).resolve().parents[1]/"bin"
sys.path.insert(0,str(BIN))
from guardian_response import response_blockers

def module(file,name):
    spec=importlib.util.spec_from_file_location(name,BIN/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value

rc=module("run-controller.py","functional_rc")
council=module("architecture-decision-council.py","functional_council")
readiness=module("domain-toolchain-readiness.py","functional_readiness")
interface=module("central-interface-controller-core.py","functional_interface")
factory_runner=module("domain-factory-runner.py","functional_factory")

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value))

class GuardianTests(unittest.TestCase):
    def test_response_requires_exit_success_and_safe_flags(self):
        for value,code in [({"verdict":"PASS"},42),({"verdict":"PASS","stop_recommended":True},0),
                           ({"verdict":"WARNING","remediation_required":True},0),
                           ({"verdict":"PASS","stop_recommended":"false"},0),([],0),({},0)]:
            self.assertTrue(response_blockers(value,code),(value,code))
        for value in [{"verdict":"PASS"},{"verdict":"WARNING","stop_recommended":False}]:
            self.assertEqual(response_blockers(value,0),[])

    def test_real_client_nonzero_or_directive_blocks_controller(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);client=root/"client.py";policy=root/"policy.json";write(policy,{})
            envelope={"run_id":"local-run","project":"local-project","task":{"id":"t","permission":"read"},"policy_context":{}}
            cfg={"guardian":{"enabled":True,"runtime_root":str(root),"client":str(client),"policy":str(policy)}}
            with patch.object(rc,"emergency_stop_active",return_value=False),patch.object(rc.grr,"inject_context",side_effect=lambda value,**kw:value):
                for payload,code in [({"verdict":"PASS"},42),({"verdict":"PASS","stop_recommended":True},0),({"verdict":"PASS","remediation_required":True},0)]:
                    client.write_text("import json\nprint(json.dumps("+repr(payload)+"))\nraise SystemExit("+str(code)+")\n")
                    errors,_=rc.guardian_gate(envelope,{},cfg,[],root/"events","t","PRE_ACTION")
                    self.assertTrue(errors)

    def test_enabled_guardian_missing_runtime_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            errors,_=rc.guardian_gate({}, {}, {"guardian":{"enabled":True,"runtime_root":td+"/absent"}},[],Path(td),"t","PRE_ACTION")
            self.assertIn("GUARDIAN_RUNTIME_UNAVAILABLE_FAIL_CLOSED",errors)

class ControllerTests(unittest.TestCase):
    def invoke(self,exitcode=0,lock_error=False,post_error=False,post_block=False):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);adapter=root/"adapter"
            adapter.write_text("#!"+sys.executable+"\nimport sys,json\ne=json.load(sys.stdin)\nprint(json.dumps({'schema':'chacha.dev/task-result/v1','project':e['project'],'task_id':e['task']['id'],'producer':'fixture-adapter','status':'OK','verification':{'status':'UNVERIFIED','method':'none'},'evidence':[],'outputs':[]}))\nraise SystemExit("+str(exitcode)+")\n")
            adapter.chmod(0o700)
            permission="workspace-write" if lock_error else "read"
            docs={
              "graph":{"schema":rc.GRAPH_SCHEMA,"project":"fixture","tasks":[{"id":"t","permission":permission,"capabilities":["x"]}]},
              "plan":{"schema":rc.PLAN_SCHEMA,"project":"fixture","waves":[{"index":1,"tasks":[{"task_id":"t","permission":permission,"provider_bindings":[{"provider":"p","capability":"x","health_state":"HEALTHY"}]}]}]},
              "adapters":{"schema":rc.ADAPTER_SCHEMA,"providers":{"p":{"adapter":"fixture-adapter","execution":"vps"}},"adapters":{"fixture-adapter":{"status":"ENABLED","supports":["read","workspace-write"],"executable":str(adapter)}}},
              "policy":{"schema":rc.POLICY_SCHEMA,"mode":"execute-enabled","guardian":{"enabled":False},"dispatch":{"max_attempts":1},"locking":{"write_permissions":["workspace-write"],"root":str(root/"locks")},"workspace":{"root":str(root/"projects")}},
              "ledger":{"schema":rc.LEDGER_SCHEMA,"project":"fixture"}}
            argv=["fixture-controller"]
            for flag,value in docs.items():
                path=root/(flag+".json");write(path,value);argv += ["--"+flag,str(path)]
            argv += ["--output-dir",str(root/"runs"),"--execute","--workspace",str(root/"projects/fixture")]
            phases=[];actions=[]
            def gate(envelope,ledger,policy,errors,out,name,phase,**kw):
                phases.append(phase);actions.append(envelope["run_id"]+":"+envelope["task"]["id"])
                if phase=="POST_ACTION" and post_error:raise RuntimeError("fixture unavailable")
                return (["GUARDIAN_REMEDIATION_OR_STOP_REQUIRED"] if phase=="POST_ACTION" and post_block else []),{"verdict":"PASS","fixture":True}
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(sys,"argv",argv))
                stack.enter_context(patch.object(rc,"guardian_gate",side_effect=gate))
                stack.enter_context(patch.object(rc,"record_task_learning",return_value={}))
                if lock_error:stack.enter_context(patch.object(rc,"acquire_lock",side_effect=PermissionError("fixture lock")))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                rc.main()
            result=json.loads(next((root/"runs").glob("run-*/run-record.json")).read_text())
            self.assertEqual(phases,["PRE_ACTION","POST_ACTION"])
            self.assertEqual(actions[0],actions[1])
            return result

    def test_valid_json_does_not_override_nonzero_exit(self):
        run=self.invoke(exitcode=7);task=run["waves"][0]["tasks"][0]
        self.assertEqual(task["status"],"FAILED");self.assertEqual(task["failure_class"],"adapter-exit:7")
        self.assertEqual(run["summary"]["succeeded"],0);self.assertEqual(run["summary"]["failed"],1)

    def test_failure_before_dispatch_posts_without_launch(self):
        run=self.invoke(lock_error=True)
        self.assertEqual(run["summary"]["dispatched"],0)
        self.assertEqual(run["waves"][0]["tasks"][0]["status"],"FAILED")

    def test_post_failure_cannot_leave_success(self):
        for kwargs in [{"post_error":True},{"post_block":True}]:
            run=self.invoke(**kwargs)
            self.assertEqual(run["summary"]["succeeded"],0);self.assertEqual(run["summary"]["failed"],1)

    def test_success_counted_only_after_post(self):
        self.assertEqual(self.invoke()["summary"]["succeeded"],1)

class CouncilTests(unittest.TestCase):
    def test_actual_subcomponent_gate_rejects_inconsistent_response(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);client=root/"dev-hub/bin/guardian-client.py";client.parent.mkdir(parents=True)
            write(root/"dev-hub/config/guardian-runtime-policy.v1.json",{})
            for payload,code in [({"verdict":"PASS"},42),({"verdict":"PASS","stop_recommended":True},0),({"verdict":"WARNING","remediation_required":True},0),([],0)]:
                client.write_text("import json\nprint(json.dumps("+repr(payload)+"))\nraise SystemExit("+str(code)+")\n")
                with patch.object(Path,"exists",return_value=True),patch.object(council,"blocks_execution",return_value=False):
                    with self.assertRaisesRegex(RuntimeError,"GUARDIAN_SUBCOMPONENT_BLOCK"):
                        council.guardian_subcomponent(root,"fixture-role","fixture-task","PRE_ACTION","fixture-action")

    def test_subcomponent_stop_unknown_refuses_before_client(self):
        with patch.object(Path,"exists",return_value=True),patch.object(council,"blocks_execution",return_value=True),patch.object(council.subprocess,"run") as client:
            with self.assertRaisesRegex(RuntimeError,"STOP_ACTIVE_OR_UNKNOWN"):
                council.guardian_subcomponent(Path("/fixture"),"fixture-role","fixture-task","PRE_ACTION","fixture-action")
        client.assert_not_called()

    def invoke(self,child_error=None,code=0,pre_error=False,post_error=False):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);out=root/"portfolio.json";write(out,{"decision_ready":True})
            phases=[];ids=[]
            def gate(*args,**kwargs):
                phases.append(args[3]);ids.append(args[4])
                if (pre_error and args[3]=="PRE_ACTION") or (post_error and args[3]=="POST_ACTION"):raise RuntimeError("fixture refusal")
            child=types.SimpleNamespace(returncode=code,stderr="fixture failure",stdout="")
            with patch.object(council,"guardian_subcomponent",side_effect=gate),patch.object(council.subprocess,"run",side_effect=child_error,return_value=child) as execute:
                try:result=council.run_architecture_portfolio(root,root/"pre",root/"branch",root/"agent",root/"db",root/"policy",out)
                except Exception as exc:result=exc
            return result,phases,ids,execute.call_count

    def test_failure_and_timeout_post_without_replay(self):
        for kwargs in [{"code":7},{"child_error":subprocess.TimeoutExpired("fixture",45)},{"child_error":FileNotFoundError("fixture")}]:
            result,phases,ids,calls=self.invoke(**kwargs)
            self.assertEqual(phases,["PRE_ACTION","POST_ACTION"]);self.assertEqual(ids[0],ids[1]);self.assertEqual(calls,1)
            if isinstance(result,dict):self.assertFalse(result["decision_ready"])

    def test_pre_refusal_does_not_launch(self):
        _,phases,_,calls=self.invoke(pre_error=True)
        self.assertEqual(phases,["PRE_ACTION"]);self.assertEqual(calls,0)

    def test_post_refusal_prevents_returning_decision(self):
        result,_,_,_=self.invoke(post_error=True)
        self.assertIsInstance(result,RuntimeError);self.assertIn("POST_ACTION_UNCONFIRMED",str(result))

class EffectiveRegistryTests(unittest.TestCase):
    def test_factory_graph_uses_enriched_plan(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);planning=root/"planning";repo=BIN.parents[1];effective=root/"effective.json"
            registry=json.loads((repo/"dev-hub/config/capability-registry.v1.json").read_text())
            registry["capabilities"]["requirements-analysis"]["providers"]=[{"id":"fixture-new-provider","status":"ADOPT"}]
            write(effective,registry)
            project="fixture";branch="fixture:product:primary"
            plan={"schema":"chacha.dev/domain-plan/v1","project_id":project,"active_capability_registry":str(effective),
                  "packages":[{"id":"domain:product","domain":"product","kind":"primary","runtime_required":True,"branch_id":branch,"agent_id":"product-domain-architect","capabilities":["requirements-analysis"]}]}
            contract={"schema":"chacha.dev/dynamic-component-role-contract/v1","component_kind":"branch","contract_id":"branch:"+branch,
                      "template_contract_id":"role:__branch__","issued_by":"branch-foundry","component_id":branch,"project_id":project,"domain":"product","package_id":"domain:product",
                      "allowed_actions":["INVOKE_COMPONENT","DISPATCH_TASK","REPORT_TASK_RESULT"],"forbidden_actions":["PRODUCTION_DEPLOY"],
                      "allowed_permissions":["read","plan","workspace-write"],"allowed_capabilities":["requirements-analysis"],
                      "production_permissions_allowed":False,"automatic_external_spend_eur":0,"version":"fixture","contract_digest":"fixture"}
            for name,value in [
                ("final-plan.json",plan),("architecture-decision-council.json",{"schema":"chacha.dev/architecture-decision-council/v1","project_id":project,"dispatch_allowed":True,"blocked":[]}),
                ("component-role-contracts.json",{"schema":"chacha.dev/dynamic-component-role-contract-batch/v1","project_id":project,"contracts":[contract]}),
                ("agent-role-contracts.json",{"schema":"chacha.dev/dynamic-agent-role-contract-batch/v1","project_id":project,"contracts":[]})]:write(planning/name,value)
            result=factory_runner.build(repo,planning,root/"factory")
            self.assertEqual(result["status"],"READY")
            req=json.loads((root/"factory/provider-health-requirements.json").read_text())
            self.assertEqual([x["provider"] for x in req["providers"]],["fixture-new-provider"])
            graph=json.loads((root/"factory/domain-execution-graph.json").read_text())
            self.assertEqual(graph["capability_registry"],str(effective))
            self.assertEqual(graph["capability_registry_digest"],result["capability_registry_digest"])

    def test_scheduler_receives_effective_registry(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);effective=root/"effective.json";write(effective,{"capabilities":{}})
            digest="sha256:"+hashlib.sha256(effective.read_bytes()).hexdigest()
            graph=root/"graph.json";write(graph,{"project":"fixture","tasks":[],"capability_registry_digest":digest})
            health=root/"health.json";write(health,{})
            write(root/"runtime/evidence/fixture/ledger.json",{})
            for name in ["agents.json","components.json","dev-hub/config/guardian-role-contracts.v1.json"]:write(root/name,{})
            args=types.SimpleNamespace(repo_root=root,output_dir=root/"out",runtime_root=root/"runtime")
            df={"domain_execution_graph":str(graph),"capability_registry":str(effective),"capability_registry_digest":digest,
                "agent_contracts":str(root/"agents.json"),"component_contracts":str(root/"components.json")}
            ready={"provider_health_snapshot":str(health),"capability_registry":str(effective),"capability_registry_digest":digest}
            write(root/"out/domain-execution-handoff/workspace-materialization.json",{"status":"READY"})
            calls=[]
            def scheduler(argv,**kwargs):
                calls.append(argv);write(Path(argv[argv.index("--output")+1]),{"summary":{"blocked_count":1}})
                return types.SimpleNamespace(returncode=2,stdout="",stderr="")
            with patch.object(interface,"materialize_development_workspaces",return_value={"status":"READY"}),patch.object(interface.subprocess,"run",side_effect=scheduler):
                result=interface.domain_scheduler_run_controller(args,"fixture",{},df,ready)
            self.assertEqual(result["next_action"],"SCHEDULER_BLOCKED")
            self.assertEqual(calls[0][calls[0].index("--registry")+1],str(effective));self.assertEqual(len(calls),1)

    def test_readiness_uses_effective_registry_and_detects_change(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);repo=root/"repo";planning=root/"planning";factory=root/"factory";cfg=repo/"dev-hub/config"
            effective=planning/"effective.json";write(effective,{"schema":"chacha.dev/capability-registry/v1","capabilities":{"new-cap":{"providers":[{"id":"p","status":"ADOPT"}]}}})
            source_digest="sha256:"+hashlib.sha256(effective.read_bytes()).hexdigest()
            write(planning/"final-plan.json",{"active_capability_registry":str(effective)})
            write(planning/"agent-topology.json",{"schema":"chacha.dev/agent-topology/v1","decisions":[]})
            write(cfg/"capability-registry.v1.json",{"schema":"chacha.dev/capability-registry/v1","capabilities":{}})
            write(cfg/"provider-adapters.v1.json",{"schema":rc.ADAPTER_SCHEMA,"providers":{"p":{"adapter":"a","execution":"vps"}},"adapters":{"a":{"status":"ENABLED","executable":"/bin/true"}}})
            write(cfg/"provider-health-probes.v1.json",{"schema":"chacha.dev/provider-health-probes/v1","providers":{"p":{}}})
            write(factory/"domain-execution-graph.json",{"schema":rc.GRAPH_SCHEMA,"project":"fixture","capability_registry_digest":source_digest,"tasks":[{"id":"t","capabilities":["new-cap"],"permission":"read","metadata":{}}]})
            health=root/"health.json";write(health,{"schema":"chacha.dev/provider-health-snapshot/v1","providers":{"p":{"state":"HEALTHY","source":"fixture","checked_at":"2026-10-12T00:00:00Z"}}})
            result=readiness.evaluate(repo,planning,factory,root/"out.json",health)
            self.assertEqual(result["next_stage"],"SCHEDULER_READY")
            self.assertEqual(result["capability_registry"],str(effective));self.assertEqual(result["capability_registry_digest"],source_digest)
            effective.write_text("{}");
            with self.assertRaisesRegex(SystemExit,"CAPABILITY_REGISTRY_CHANGED_SINCE_FACTORY"):
                readiness.evaluate(repo,planning,factory,root/"out.json",health)

    def test_missing_effective_registry_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);write(root/"graph.json",{"project":"fixture"})
            args=types.SimpleNamespace(repo_root=root,output_dir=root/"out")
            df={"domain_execution_graph":str(root/"graph.json"),"capability_registry":str(root/"missing.json")}
            with patch.object(interface.subprocess,"run") as execute:
                result=interface.domain_scheduler_run_controller(args,"fixture",{},df,{})
            self.assertEqual(result["next_action"],"CAPABILITY_REGISTRY_REVALIDATION_REQUIRED");execute.assert_not_called()

if __name__=="__main__":unittest.main()
