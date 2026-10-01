#!/usr/bin/env python3
import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
POLICY=json.loads((ROOT/"dev-hub/config/ha-standby-readiness-publisher.v1.json").read_text())
SPEC=importlib.util.spec_from_file_location("ha_pub",ROOT/"dev-hub/bin/ha-standby-readiness-publisher.py")
MOD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)
REV="1"*40

class PublisherTest(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
        self.rp=self.root/"readiness.json";self.mp=self.root/"manifest.json"
        self.readiness={"schema":"chacha.dev/ha-readiness/v1","status":"PASS","state":"READY_FOR_GOVERNED_FAILOVER_PILOT","reasons":[],"checkpoint_id":"chk-1","production_activation_authorized":False,"failover_authorized":False,"bastion_failover_state":"RESERVED_INACTIVE","automatic_external_spend_eur":0}
        self.manifest={"schema":"chacha.dev/ha-standby-manifest/v1","mode":"ACTIVE_PASSIVE","primary":{"node_id":"vps","role":"ACTIVE","platform_revision":REV},"standby":{"node_id":"nas","role":"PASSIVE","platform_revision":REV},"single_writer_enforced":True,"fencing_ready":True,"rollback_ready":True,"automatic_external_spend_eur":0}
    def tearDown(self): self.t.cleanup()
    def invoke(self,r=None,m=None,rev=REV):
        r=copy.deepcopy(r or self.readiness);m=copy.deepcopy(m or self.manifest)
        self.rp.write_text(json.dumps(r));self.mp.write_text(json.dumps(m))
        return MOD.publish(POLICY,r,m,rev,self.rp,self.mp)
    def test_pass_exact_revision(self):
        x=self.invoke();self.assertEqual(x["status"],"PASS",x);self.assertEqual(x["platform_revision"],REV)
        self.assertFalse(x["failover_authorized"]);self.assertTrue(x["single_writer_enforced"])
    def test_stale_standby_revision_blocks(self):
        m=copy.deepcopy(self.manifest);m["standby"]["platform_revision"]="2"*40
        x=self.invoke(m=m);self.assertEqual(x["status"],"BLOCK");self.assertIn("STANDBY_REVISION_MISMATCH",x["reasons"])
    def test_readiness_not_pass_blocks(self):
        r=copy.deepcopy(self.readiness);r["status"]="BLOCK"
        x=self.invoke(r=r);self.assertIn("READINESS_NOT_PASS",x["reasons"])
    def test_failover_authorized_blocks(self):
        r=copy.deepcopy(self.readiness);r["failover_authorized"]=True
        x=self.invoke(r=r);self.assertIn("FAILOVER_MUST_REMAIN_UNAUTHORIZED",x["reasons"])
    def test_fencing_missing_blocks(self):
        m=copy.deepcopy(self.manifest);m["fencing_ready"]=False
        x=self.invoke(m=m);self.assertIn("FENCING_NOT_READY",x["reasons"])

if __name__=="__main__": unittest.main()
