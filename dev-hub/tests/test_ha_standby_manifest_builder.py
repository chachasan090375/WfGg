#!/usr/bin/env python3
import importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"dev-hub/bin/ha-standby-manifest-builder.py"

def mod():
    spec=importlib.util.spec_from_file_location("ha_builder",TOOL)
    assert spec and spec.loader
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def profile():
    return json.loads((ROOT/"dev-hub/config/ha-standby-profile.v1.json").read_text(encoding="utf-8"))


class TestHAStandbyManifestBuilder(unittest.TestCase):
    def setUp(self):
        self.m=mod();self.p=profile();self.rev="1"*40
        self.res={"schema":"chacha.dev/ha-node-resources/v1","standby":{"available_memory_mb":4712,"free_disk_mb":3665762,"cpu_count":4}}
    def test_builds_passive_manifest_from_profile(self):
        x=self.m.build(self.p,self.rev,self.res,"chacha-dev-platform",2048,4096)
        self.assertEqual(x["primary"]["platform_revision"],self.rev)
        self.assertEqual(x["standby"]["platform_revision"],self.rev)
        self.assertEqual(x["standby"]["role"],"PASSIVE")
        self.assertTrue(x["single_writer_enforced"]);self.assertTrue(x["fencing_ready"])
        self.assertTrue(x["guardian_required"]);self.assertTrue(x["sentinel_required"])
        self.assertEqual(x["automatic_external_spend_eur"],0)
    def test_resources_are_runtime_inputs(self):
        self.res["standby"]["available_memory_mb"]=5000
        x=self.m.build(self.p,self.rev,self.res,"chacha-dev-platform",2048,4096)
        self.assertEqual(x["standby"]["available_memory_mb"],5000)
    def test_failover_cannot_be_pre_authorized(self):
        self.p["safety"]["failover_authorized"]=True
        with self.assertRaisesRegex(ValueError,"FAILOVER_MUST_REMAIN_DISABLED"):
            self.m.build(self.p,self.rev,self.res,"chacha-dev-platform",2048,4096)
    def test_active_writer_is_forbidden(self):
        self.p["safety"]["active_writer"]=True
        with self.assertRaisesRegex(ValueError,"STANDBY_ACTIVE_WRITER_FORBIDDEN"):
            self.m.build(self.p,self.rev,self.res,"chacha-dev-platform",2048,4096)
    def test_exact_revision_required(self):
        with self.assertRaisesRegex(ValueError,"EXACT_REVISION_REQUIRED"):
            self.m.build(self.p,"abc",self.res,"chacha-dev-platform",2048,4096)
    def test_failure_domains_must_be_distinct(self):
        self.p["standby"]["failure_domain"]=self.p["primary"]["failure_domain"]
        with self.assertRaisesRegex(ValueError,"FAILURE_DOMAIN_NOT_DISTINCT"):
            self.m.build(self.p,self.rev,self.res,"chacha-dev-platform",2048,4096)

if __name__=="__main__":
    unittest.main()
