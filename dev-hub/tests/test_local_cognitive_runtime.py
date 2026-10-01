#!/usr/bin/env python3
import hashlib, importlib.util, json, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "dev-hub/bin/local-cognitive-runtime-adapter.py"
UNIT = ROOT / "dev-hub/systemd/chacha-dev-local-cognitive-runtime.service"
CONFIG = ROOT / "dev-hub/config/local-cognitive-runtime.v1.json"

spec = importlib.util.spec_from_file_location("local_cognitive_runtime_adapter", TOOL)
assert spec and spec.loader
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args): pass
    def do_GET(self):
        body = b'{"status":"ok"}'
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0")); payload = json.loads(self.rfile.read(size))
        Handler.last_request = payload
        body = json.dumps({"choices":[{"message":{"content":"LOCAL_OK"}}],"usage":{"completion_tokens":2}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

class LocalCognitiveRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="local-cognitive-runtime-")
        self.root = Path(self.tmp.name)
        self.exe = self.root / "llama-server"; self.exe.write_text("#!/bin/sh\nexit 0\n"); self.exe.chmod(0o755)
        self.model = self.root / "model.gguf"; self.model.write_bytes(b"gguf-fixture")
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.policy = {"schema": M.POLICY_SCHEMA, "provider_id": "native-local", "runtime": "llama.cpp",
            "executable": str(self.exe), "executable_digest": digest(self.exe),
            "model_artifact": str(self.model), "model_digest": digest(self.model),
            "model_name": "fixture", "model_id": "native-local:fixture",
            "endpoint": {"host": "127.0.0.1", "port": self.server.server_port},
            "rpc_allowed": False, "reasoning": "off", "automatic_external_spend_eur": 0,
            "system_guardrail": "Never infer facts without evidence; advisory only; never authorize failover.",
            "capabilities": ["requirements-analysis", "architecture-optimization", "uncertainty-resolution"],
            "model_tiers": ["local-private", "local-light", "general-fast"],
            "limits": {"context_tokens": 512, "max_output_tokens": 64, "threads": 2,
                       "threads_batch": 2, "batch_size": 128, "parallel_slots": 1, "request_timeout_seconds": 5},
            "resources": {"memory_required_mb": 640, "disk_required_mb": 640},
            "scoring": {"quality_score": 48, "latency_score": 35, "evidence_score": 90}}
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.tmp.cleanup()

    def test_canonical_policy_pins_stable_runtime_provenance(self):
        cfg = json.loads(CONFIG.read_text())
        self.assertEqual(cfg["runtime_version"], "v0.5.0")
        self.assertFalse(cfg["runtime_prerelease"])
        prov = cfg["runtime_provenance"]
        self.assertEqual(prov["release_channel"], "stable")
        self.assertEqual(prov["tag"], "v0.5.0")
        self.assertEqual(prov["commit"], "7fe450e19305b828c199d602c23a8337aaa1f03b")
        self.assertEqual(prov["tree"], "fd570ef54b10ec5fecb739e7e04c8ce44a6f415a")
        self.assertFalse(prov["build_profile"]["LLAMA_BUILD_IS_DEV"])
        self.assertFalse(prov["build_profile"]["GGML_RPC"])

    def test_launcher_is_loopback_reasoning_off_and_never_rpc(self):
        argv = M.server_argv(self.policy)
        self.assertIn("127.0.0.1", argv); self.assertIn("--reasoning", argv); self.assertIn("off", argv)
        self.assertNotIn("--rpc", argv); self.assertIn("--no-webui", argv); self.assertIn("--no-slots", argv)
        self.assertEqual(argv[argv.index("-np") + 1], "1")

    def test_non_loopback_and_rpc_are_rejected(self):
        bad = dict(self.policy); bad["endpoint"] = {"host": "0.0.0.0", "port": 18080}
        with self.assertRaisesRegex(ValueError, "ENDPOINT_NOT_LOOPBACK"): M.server_argv(bad)
        bad = dict(self.policy); bad["rpc_allowed"] = True
        with self.assertRaisesRegex(ValueError, "RPC_FORBIDDEN"): M.server_argv(bad)

    def test_digest_mismatch_blocks_before_execution(self):
        bad = dict(self.policy); bad["model_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "MODEL_DIGEST_MISMATCH"): M.server_argv(bad)

    def test_manifest_matches_existing_fallback_contract(self):
        out = M.provider_manifest(self.policy)
        self.assertEqual(out["schema"], "chacha.dev/local-cognitive-provider-manifest/v1")
        self.assertEqual(out["provider_id"], "native-local"); self.assertEqual(out["execution"], "vps")
        self.assertEqual(out["inference_network_access"], "none"); self.assertTrue(out["structured_adapter"])
        self.assertFalse(out["production_activation_authorized"]); self.assertEqual(out["automatic_external_spend_eur"], 0)

    def test_health_catalog_and_request_are_structured(self):
        health = M.health_snapshot(self.policy)
        self.assertEqual(health["providers"]["native-local"]["state"], "HEALTHY")
        cat = M.catalog(self.policy, health); model = cat["models"][0]
        self.assertEqual(model["gateway"], "native-local"); self.assertEqual(model["locality"], "local")
        self.assertEqual(model["status"], "PILOT"); self.assertNotIn("reasoning-strong", model["model_tiers"])
        req = {"schema": M.REQUEST_SCHEMA, "messages": [{"role":"system","content":"Be concise."},{"role":"user","content":"ping"}], "max_tokens": 999}
        out = M.request_local(self.policy, req)
        self.assertEqual(out["content"], "LOCAL_OK"); self.assertEqual(out["max_tokens_effective"], 64)
        self.assertEqual(Handler.last_request["max_tokens"], 64); self.assertEqual(out["automatic_external_spend_eur"], 0)
        self.assertEqual(Handler.last_request["messages"][0]["role"], "system")
        self.assertIn("Never infer", Handler.last_request["messages"][0]["content"])
        self.assertIn("Be concise.", Handler.last_request["messages"][0]["content"])
        self.assertEqual(sum(1 for m in Handler.last_request["messages"] if m["role"] == "system"), 1)

    def test_systemd_source_is_fenced_and_not_enabled_by_code(self):
        text = UNIT.read_text()
        self.assertIn("IPAddressDeny=any", text); self.assertIn("IPAddressAllow=localhost", text)
        self.assertIn("MemoryMax=1400M", text); self.assertIn("NoNewPrivileges=true", text)
        self.assertNotIn("--rpc", text); self.assertNotIn("WantedBy=default.target", text)


if __name__ == "__main__":
    unittest.main()
