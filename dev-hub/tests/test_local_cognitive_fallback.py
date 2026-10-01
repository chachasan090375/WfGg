#!/usr/bin/env python3
import hashlib,json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"dev-hub/bin/local-cognitive-fallback-gate.py"
POLICY=ROOT/"dev-hub/config/local-cognitive-fallback.v1.json"

def run(*args): return subprocess.run([sys.executable,str(TOOL),*[str(x) for x in args]],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
def load(p): return json.loads(Path(p).read_text())
def sha(p): return "sha256:"+hashlib.sha256(Path(p).read_bytes()).hexdigest()

class LocalCognitiveFallbackTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix="local-cognitive-fallback-test-"))
        self.exe=self.root/"runtime";self.exe.write_text("#!/bin/sh\nexit 0\n");self.exe.chmod(0o755)
        self.model=self.root/"model.gguf";self.model.write_bytes(b"model-fixture")
        self.health=self.root/"health.json";self.health.write_text(json.dumps({"schema":"chacha.dev/provider-health-snapshot/v1","providers":{"local-cognitive":{"state":"HEALTHY","source":"local-probe","checked_at":"now"}}}))
        self.resources=self.root/"resources.json";self.resources.write_text(json.dumps({"schema":"chacha.dev/local-resource-snapshot/v1","available_memory_mb":4096,"free_disk_mb":10000}))
    def tearDown(self): shutil.rmtree(self.root,ignore_errors=True)
    def manifest(self,**changes):
        x={"schema":"chacha.dev/local-cognitive-provider-manifest/v1","provider_id":"local-cognitive","execution":"vps","inference_network_access":"none","cost_class":"local","automatic_external_spend_eur":0,"executable":str(self.exe),"model_artifact":str(self.model),"model_digest":sha(self.model),"capabilities":["requirements-analysis","architecture-optimization","uncertainty-resolution"],"memory_required_mb":1024,"disk_required_mb":1024,"structured_adapter":True,"rollback_ready":True}
        x.update(changes);p=self.root/"manifest.json";p.write_text(json.dumps(x));return p
    def invoke(self,m):
        out=self.root/"out.json";p=run("--policy",POLICY,"--manifest",m,"--health",self.health,"--resources",self.resources,"--output",out);return p,load(out)
    def test_ready_local_runtime_passes_without_activation(self):
        p,x=self.invoke(self.manifest());self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(x["state"],"READY_FOR_GOVERNED_PILOT");self.assertFalse(x["production_activation_authorized"]);self.assertFalse(x["d1_write_performed"])
    def test_network_dependent_inference_blocks(self):
        p,x=self.invoke(self.manifest(inference_network_access="required"));self.assertEqual(p.returncode,20);self.assertIn("INFERENCE_REQUIRES_NETWORK",x["reasons"])
    def test_resource_headroom_blocks(self):
        self.resources.write_text(json.dumps({"schema":"chacha.dev/local-resource-snapshot/v1","available_memory_mb":1100,"free_disk_mb":10000}))
        p,x=self.invoke(self.manifest());self.assertEqual(p.returncode,20);self.assertIn("MEMORY_HEADROOM_INSUFFICIENT",x["reasons"])
    def test_model_digest_mismatch_blocks(self):
        p,x=self.invoke(self.manifest(model_digest="sha256:"+"0"*64));self.assertEqual(p.returncode,20);self.assertIn("MODEL_DIGEST_MISMATCH",x["reasons"])
    def test_missing_cognitive_capability_blocks(self):
        p,x=self.invoke(self.manifest(capabilities=["requirements-analysis"]));self.assertEqual(p.returncode,20);self.assertTrue(any(r.startswith("CAPABILITIES_MISSING:") for r in x["reasons"]))

if __name__=="__main__": unittest.main()
