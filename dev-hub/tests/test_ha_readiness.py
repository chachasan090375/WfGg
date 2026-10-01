#!/usr/bin/env python3
import copy,importlib.util,json,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin"
POLICY=json.loads((ROOT/"dev-hub/config/ha-readiness.v1.json").read_text())

def mod(name,path):
    spec=importlib.util.spec_from_file_location(name,path);assert spec and spec.loader
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
GATE=mod("ha_readiness_gate",BIN/"ha-readiness-gate.py")
CRYPTO=mod("ha_crypto_test",BIN/"crypto-trust.py")

class HAReadinessTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix="ha-readiness-test-"))
        self.priv=self.root/"private.pem";self.pub=self.root/"public.pem"
        subprocess.run(["openssl","genpkey","-algorithm","Ed25519","-out",str(self.priv)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        subprocess.run(["openssl","pkey","-in",str(self.priv),"-pubout","-out",str(self.pub)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        state={"schema":"chacha.dev/control-plane-state/v1","project":"platform-global","last_event_sequence":7,
               "last_event_digest":"sha256:"+"1"*64,"state":{"active_revision":"abc"}}
        self.checkpoint=CRYPTO.sign_checkpoint(CRYPTO.create_checkpoint(state,"ha-test-key","ha-readiness-test"),self.priv,self.pub)
    def tearDown(self): shutil.rmtree(self.root,ignore_errors=True)
    def manifest(self,**changes):
        x={"schema":"chacha.dev/ha-standby-manifest/v1","mode":"ACTIVE_PASSIVE","checkpoint_project":"platform-global",
           "primary":{"node_id":"node-a","role":"ACTIVE","failure_domain":"provider-a/zone-1","platform_revision":"abc"},
           "standby":{"node_id":"node-b","role":"PASSIVE","failure_domain":"provider-b/zone-2","platform_revision":"abc",
                      "available_memory_mb":4096,"free_disk_mb":12000,"cpu_count":4},
           "runtime_memory_required_mb":2048,"runtime_disk_required_mb":4096,"state_replication":"SIGNED_CHECKPOINT_PULL",
           "single_writer_enforced":True,"fencing_ready":True,"rollback_ready":True,"guardian_required":True,"sentinel_required":True,
           "automatic_external_spend_eur":0}
        x.update(changes);return x
    def health(self,node):
        return {"schema":"chacha.dev/ha-node-health/v1","node_id":node,"state":"HEALTHY","observed_at":"now",
                "services":{s:"READY" for s in POLICY["required_services"]}}
    def restore(self):
        return {"schema":"chacha.dev/storage-restore-verifier-pilot-evidence/v1","status":"PASS",
                "verifier":{"independent":True},"restore":{"sqlite_integrity":"PASS"}}
    def recovery(self):
        return {"schema":"chacha.dev/recovery-drill-report/v1","status":"PASS","summary":{"total":5,"passed":5,"failed":0}}
    def run_gate(self,manifest=None,primary_health=None,standby_health=None,checkpoint=None,restore=None,recovery=None):
        return GATE.check(POLICY,manifest or self.manifest(),primary_health or self.health("node-a"),
                          standby_health or self.health("node-b"),checkpoint or self.checkpoint,self.pub,
                          restore or self.restore(),recovery or self.recovery(),ROOT)
    def test_ready_active_passive_contract_passes_without_failover(self):
        x=self.run_gate();self.assertEqual(x["status"],"PASS",x);self.assertEqual(x["state"],"READY_FOR_GOVERNED_FAILOVER_PILOT")
        self.assertFalse(x["failover_authorized"]);self.assertEqual(x["bastion_failover_state"],"RESERVED_INACTIVE")
    def test_same_failure_domain_blocks(self):
        m=self.manifest();m["standby"]["failure_domain"]=m["primary"]["failure_domain"]
        x=self.run_gate(manifest=m);self.assertIn("FAILURE_DOMAIN_NOT_DISTINCT",x["reasons"])
    def test_missing_service_parity_blocks(self):
        h=self.health("node-b");h["services"]["sentinel"]="MISSING"
        x=self.run_gate(standby_health=h);self.assertTrue(any(r.startswith("STANDBY_SERVICE_PARITY_MISSING:") for r in x["reasons"]))
    def test_tampered_checkpoint_blocks(self):
        cp=copy.deepcopy(self.checkpoint);cp["journal_sequence"]=8
        x=self.run_gate(checkpoint=cp);self.assertTrue(any(r in x["reasons"] for r in ("CHECKPOINT_SIGNATURE_INVALID","CHECKPOINT_CHECKPOINT_DIGEST_MISMATCH")),x)
    def test_resource_headroom_blocks(self):
        m=self.manifest();m["standby"]["available_memory_mb"]=2300
        x=self.run_gate(manifest=m);self.assertIn("STANDBY_MEMORY_HEADROOM_INSUFFICIENT",x["reasons"])
    def test_recovery_failure_blocks(self):
        r=self.recovery();r["status"]="FAIL";r["summary"]["failed"]=1
        x=self.run_gate(recovery=r);self.assertIn("RECOVERY_DRILL_NOT_PASS",x["reasons"]);self.assertIn("RECOVERY_DRILL_FAILURES_PRESENT",x["reasons"])

if __name__=="__main__":unittest.main()
