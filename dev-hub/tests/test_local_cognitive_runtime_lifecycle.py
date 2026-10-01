#!/usr/bin/env python3
import hashlib, importlib.util, json, os, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "dev-hub/bin/local-cognitive-runtime-lifecycle.py"
spec = importlib.util.spec_from_file_location("local_cognitive_runtime_lifecycle", TOOL)
assert spec and spec.loader
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


def sha(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


class LocalCognitiveLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="native-local-lifecycle-")
        self.root = Path(self.tmp.name)
        self.releases = self.root / "releases"; self.releases.mkdir()
        self.slot = self.releases / "stable-v1"; (self.slot / "bin").mkdir(parents=True); (self.slot / "model").mkdir()
        self.server = self.slot / "bin/llama-server"; self.server.write_text("#!/bin/sh\nexit 0\n"); self.server.chmod(0o755)
        self.model = self.slot / "model/Qwen3.5-0.8B-Q4_0.gguf"; self.model.write_bytes(b"model")
        (self.slot / "meta").mkdir()
        manifest = {"schema":M.STAGE_SCHEMA,"state":"STAGED_IMMUTABLE_NOT_ACTIVE","slot_path":str(self.slot),
            "runtime":{"version":"v0.5.0","build_is_dev":False,"rpc_built":False},
            "model":{"digest":sha(self.model)},
            "files":[
                {"path":"bin/llama-server","type":"file","digest":sha(self.server)},
                {"path":"model/Qwen3.5-0.8B-Q4_0.gguf","type":"file","digest":sha(self.model)}]}
        (self.slot / "meta/stage-manifest.json").write_text(json.dumps(manifest))
        self.platform = self.root / "platform"; self.platform.mkdir(); (self.platform / ".revision").write_text("a"*40)
        self.stop = self.root / "stop.json"; self.stop.write_text(json.dumps({"active":False}))
        self.watch = self.root / "watch.json"; self.watch.write_text(json.dumps({"recommendation_class":"SHADOW"}))
        self.cfg = {"schema":M.POLICY_SCHEMA,"releases_root":str(self.releases),"current":str(self.root/"current"),
            "platform_current":str(self.platform),"emergency_stop_file":str(self.stop),
            "technology_watch_evaluation":str(self.watch),"allowed_production_recommendations":["ADOPT"],
            "approval_id":"native-local-production-activation",
            "forbidden_approval_actors":["central-orchestrator","guardian","sentinel"],
            "automatic_external_spend_eur":0}
        self.evidence = "operator-approval:test"
        self.ledger = {"schema":M.LEDGER_SCHEMA,"approvals":{"native-local-production-activation":{
            "status":"APPROVED","actor":"human-operator","observed_at":"now","evidence":self.evidence}}}
        self.dual = {"schema":M.DUAL_SCHEMA,"verdict":"PASS","revision":"a"*40}

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_stage_verifies(self):
        out = M.verify_stage(self.cfg, self.slot)
        self.assertEqual(out["slot"], str(self.slot.resolve()))
        self.assertEqual(out["model_digest"], sha(self.model))

    def test_stage_digest_drift_blocks(self):
        self.model.write_bytes(b"drift")
        with self.assertRaisesRegex(ValueError, "STAGE_FILE_DIGEST_MISMATCH"):
            M.verify_stage(self.cfg, self.slot)

    def test_shadow_watch_blocks_production_plan(self):
        out = M.make_plan(self.cfg, self.slot, "a"*40, self.ledger, self.evidence, self.dual)
        self.assertEqual(out["status"], "BLOCK")
        self.assertIn("TECHNOLOGY_WATCH_NOT_PRODUCTION_READY:SHADOW", out["blockers"])
        self.assertFalse((self.root / "current").exists())

    def test_machine_or_missing_approval_blocks(self):
        ledger = {"schema":M.LEDGER_SCHEMA,"approvals":{"native-local-production-activation":{
            "status":"APPROVED","actor":"central-orchestrator","observed_at":"now","evidence":self.evidence}}}
        blockers = M.approval_blockers(self.cfg, ledger, self.evidence)
        self.assertIn("REAL_HUMAN_APPROVAL_REQUIRED", blockers)

    def test_stop_blocks_even_when_adopted(self):
        self.watch.write_text(json.dumps({"recommendation_class":"ADOPT"}))
        self.stop.write_text(json.dumps({"active":True}))
        out = M.make_plan(self.cfg, self.slot, "a"*40, self.ledger, self.evidence, self.dual)
        self.assertEqual(out["status"], "BLOCK")
        self.assertIn("EMERGENCY_STOP_ACTIVE", out["blockers"])

    def test_exact_dual_revision_required(self):
        self.watch.write_text(json.dumps({"recommendation_class":"ADOPT"}))
        bad = dict(self.dual); bad["revision"] = "b"*40
        out = M.make_plan(self.cfg, self.slot, "a"*40, self.ledger, self.evidence, bad)
        self.assertIn("DUAL_ASSURANCE_REVISION_MISMATCH", out["blockers"])

    def test_activation_and_rollback_are_atomic_in_fixture(self):
        self.watch.write_text(json.dumps({"recommendation_class":"ADOPT"}))
        activation = self.root / "activation.json"
        out = M.activate(self.cfg, self.slot, "a"*40, self.ledger, self.evidence, self.dual, activation)
        current = self.root / "current"
        self.assertEqual(out["status"], "PASS"); self.assertTrue(current.is_symlink())
        self.assertEqual(current.resolve(), self.slot.resolve())
        self.assertFalse(out["service_activation_performed"])
        rollback = self.root / "rollback.json"
        rb = M.rollback(self.cfg, activation, rollback)
        self.assertEqual(rb["status"], "PASS"); self.assertFalse(current.exists())


if __name__ == "__main__":
    unittest.main()
