import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ADAPTER=ROOT/"adapters/collector-knowledge-adapter.py"
spec=importlib.util.spec_from_file_location("cka",ADAPTER)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def envelope(action,permission,extra=None):
    meta={"collector_knowledge":{"action":action}}
    if extra:
        meta["collector_knowledge"].update(extra)
    return {
        "schema":"chacha.dev/dispatch-envelope/v1",
        "project":"wfgg-radar",
        "transition":"OPERATE->OPERATE",
        "run_id":"test",
        "wave":1,
        "task":{
            "id":"collector-knowledge:test",
            "kind":"runtime-test",
            "description":"test",
            "owner_role":"test",
            "permission":permission,
            "outputs":[],
            "verification":{"mode":"machine","self_certification_allowed":False,"required_evidence":[]},
        },
        "bindings":[{
            "capability":"collector-knowledge-inspect",
            "provider":"collector-knowledge-runtime",
            "adapter":"collector-knowledge-adapter",
            "fallback_used":False,
            "health_state":"HEALTHY",
        }],
        "policy_context":{
            "resource_class":"light",
            "requires_storage_preflight":False,
            "human_approval_required":False,
            "approval_id":None,
            "timeout_seconds":20,
        },
        "workspace":None,
        "metadata":meta,
    }

class CollectorKnowledgeAdapterTests(unittest.TestCase):
    def test_status_requires_read(self):
        k,err=mod.validate_request(envelope("status","read"))
        self.assertIsNone(err)
        self.assertEqual(k["action"],"status")

    def test_query_requires_read(self):
        k,err=mod.validate_request(envelope("query","read",{"q":"totalNum"}))
        self.assertIsNone(err)
        self.assertEqual(k["action"],"query")

    def test_install_requires_workspace_write(self):
        k,err=mod.validate_request(envelope("pilot-install","workspace-write",{"revision":"a"*40}))
        self.assertIsNone(err)
        self.assertEqual(k["action"],"pilot-install")

    def test_install_rejects_production_permission(self):
        _k,err=mod.validate_request(envelope("pilot-install","production-deploy",{"revision":"a"*40}))
        self.assertEqual(err,"COLLECTOR_KNOWLEDGE_PERMISSION_REQUIRED:workspace-write")

    def test_probe_requires_read(self):
        k,err=mod.validate_request(envelope("pilot-probe","read",{"revision":"a"*40}))
        self.assertIsNone(err)
        self.assertEqual(k["action"],"pilot-probe")

    def test_binding_is_dedicated(self):
        req=envelope("status","read")
        req["bindings"][0]["provider"]="radar-vps-runtime"
        _k,err=mod.validate_request(req)
        self.assertEqual(err,"COLLECTOR_KNOWLEDGE_BINDING_MISSING")

    def test_download_paths_are_fixed(self):
        self.assertEqual(mod.INSTALLER_PATH,"radar-vps/install-collector-knowledge-v1.sh")
        self.assertEqual(mod.PROBE_PATH,"radar-vps/probe-collector-knowledge-v1-runtime.sh")

    def test_no_game_mutation_primitives(self):
        src=ADAPTER.read_text(encoding="utf-8")
        for forbidden in (
            "SendExtension","mail.reward","building.production.collect",
            "visitor.operate","decryptGameToken","RADAR_CONNECTOR_SHARED_KEY"
        ):
            self.assertNotIn(forbidden,src)

    def test_query_uses_localhost_only(self):
        self.assertEqual(mod.API_BASE,"http://127.0.0.1:8791")

    def test_no_shell_true(self):
        src=ADAPTER.read_text(encoding="utf-8")
        self.assertIn("shell=False",src)
        self.assertNotIn("shell=True",src)
        self.assertNotIn("os.system(",src)

if __name__=="__main__":
    unittest.main()
