#!/usr/bin/env python3
import importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin/adaptive-cognitive-router.py"
POLICY=json.loads((ROOT/"dev-hub/config/adaptive-cognitive-routing.v1.json").read_text())
ECON=json.loads((ROOT/"dev-hub/config/provider-economics.v1.json").read_text())
GATEWAYS=json.loads((ROOT/"dev-hub/config/adaptive-cognitive-gateways.v1.json").read_text())

def mod():
    spec=importlib.util.spec_from_file_location("adaptive_cognitive_router",BIN)
    assert spec and spec.loader
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
R=mod()

def model(mid,gateway,tiers,cost="free",quality=70,latency=70,context=32768,
          locality="external",health="HEALTHY",quota="AVAILABLE",status="ADOPT"):
    return {"id":mid,"gateway":gateway,"provider":"fixture-provider","model":mid,
            "model_tiers":tiers,"cost_class":cost,"quality_score":quality,
            "latency_score":latency,"evidence_score":90,"context_window":context,
            "locality":locality,"health_state":health,"quota_state":quota,"status":status}

class AdaptiveCognitiveRoutingTest(unittest.TestCase):
    def setUp(self):
        self.catalog={"schema":"chacha.dev/cognitive-model-catalog/v1","models":[
            model("local-small","native-local",["local-private","local-light","general-fast"],"owned",55,45,8192,"local"),
            model("fast-general","portkey",["general-fast","general-balanced"],"free",72,95,32768),
            model("reasoning-strong","litellm",["reasoning-strong","general-balanced"],"quota",94,60,131072),
            model("code-specialist","portkey",["code-specialist","reasoning-strong"],"included",91,72,65536),
            model("translation-specialist","portkey",["translation-specialist","general-fast"],"free",88,80,32768),
            model("research-grounded","litellm",["research-grounded","reasoning-strong"],"free",86,65,65536),
            model("multimodal-model","portkey",["multimodal","general-balanced"],"free",90,70,65536),
            model("long-context-model","litellm",["long-context","reasoning-strong"],"free",89,58,262144),
            model("paid-premium","portkey",["reasoning-strong","code-specialist"],"paid",99,90,262144),
            model("quota-exhausted","litellm",["reasoning-strong"],"quota",98,90,131072,quota="EXHAUSTED")
        ]}
    def req(self,**changes):
        x={"schema":"chacha.dev/cognitive-task-request/v1","capabilities":[],"modalities":["text"],
           "privacy":"normal","complexity":"medium","context_tokens":4000,"paid_approved":False}
        x.update(changes);return x
    def route(self,**changes):
        return R.route(self.req(**changes),POLICY,self.catalog,ECON,GATEWAYS)

    def test_architecture_avoids_fast_chat_and_keeps_zero_spend_priority(self):
        x=self.route(capabilities=["architecture-optimization"])
        self.assertEqual(x["status"],"PASS",x)
        self.assertEqual(x["task_class"],"architecture")
        self.assertNotEqual(x["selected"]["model_id"],"fast-general")
        self.assertGreaterEqual(x["selected"]["task_fit"],80)
        self.assertEqual(x["selected"]["cost_class"],"free")

    def test_equal_cost_architecture_prefers_primary_reasoning_tier(self):
        catalog=json.loads(json.dumps(self.catalog))
        for item in catalog["models"]:
            if item["id"]=="reasoning-strong": item["cost_class"]="free"
        x=R.route(self.req(capabilities=["architecture-optimization"]),POLICY,catalog,ECON,GATEWAYS)
        self.assertEqual(x["selected"]["model_id"],"reasoning-strong")

    def test_code_routes_to_code_specialist(self):
        x=self.route(capabilities=["code-edit"])
        self.assertEqual(x["task_class"],"code")
        self.assertEqual(x["selected"]["model_id"],"code-specialist")

    def test_translation_routes_to_translation_specialist(self):
        x=self.route(capabilities=["translation"])
        self.assertEqual(x["task_class"],"translation")
        self.assertEqual(x["selected"]["model_id"],"translation-specialist")

    def test_multimodal_routes_to_multimodal_model(self):
        x=self.route(modalities=["text","image"])
        self.assertEqual(x["task_class"],"multimodal")
        self.assertEqual(x["selected"]["model_id"],"multimodal-model")

    def test_long_context_routes_to_long_context_model(self):
        x=self.route(context_tokens=90000)
        self.assertEqual(x["task_class"],"long-context")
        self.assertEqual(x["selected"]["model_id"],"long-context-model")

    def test_strict_privacy_forces_local_even_if_quality_lower(self):
        x=self.route(privacy="strict")
        self.assertEqual(x["task_class"],"private-local")
        self.assertEqual(x["selected"]["model_id"],"local-small")
        self.assertEqual(x["selected"]["locality"],"local")

    def test_paid_model_is_not_automatic(self):
        x=self.route(capabilities=["uncertainty-resolution"])
        paid=next(c for c in x["candidates"] if c["model_id"]=="paid-premium")
        self.assertFalse(paid["eligible"])
        self.assertIn("COST_APPROVAL_REQUIRED",paid["blockers"])

    def test_exhausted_quota_is_excluded(self):
        x=self.route(capabilities=["uncertainty-resolution"])
        q=next(c for c in x["candidates"] if c["model_id"]=="quota-exhausted")
        self.assertFalse(q["eligible"])
        self.assertIn("QUOTA_EXHAUSTED",q["blockers"])

    def test_gateway_is_not_the_decision_authority(self):
        x=self.route(capabilities=["web-research"])
        self.assertEqual(x["task_class"],"research")
        self.assertEqual(x["selected"]["model_id"],"research-grounded")
        self.assertEqual(x["reason"],"CAPABILITY_HEALTH_COST_PRIVACY_QUALITY_SELECTION")
        self.assertFalse(x["production_activation_authorized"])
        self.assertEqual(x["automatic_external_spend_eur"],0)

    def test_no_eligible_model_blocks_cleanly(self):
        catalog={"schema":"chacha.dev/cognitive-model-catalog/v1","models":[
            model("external-only","portkey",["local-private"],"paid",99,99,8192,"external")
        ]}
        x=R.route(self.req(privacy="offline"),POLICY,catalog,ECON,GATEWAYS)
        self.assertEqual(x["status"],"BLOCK")
        self.assertEqual(x["reason"],"NO_ELIGIBLE_MODEL")

    def test_unavailable_gateway_blocks_model(self):
        gateways=json.loads(json.dumps(GATEWAYS))
        gateways["gateways"]["portkey"]["status"]="UNAVAILABLE"
        x=R.route(self.req(capabilities=["code-edit"]),POLICY,self.catalog,ECON,gateways)
        blocked=[c for c in x["candidates"] if c["gateway"]=="portkey"]
        self.assertTrue(blocked)
        self.assertTrue(all("GATEWAY_NOT_ELIGIBLE" in c["blockers"] for c in blocked))

    def test_private_local_rejects_external_gateway_even_for_local_claim(self):
        catalog=json.loads(json.dumps(self.catalog))
        local=next(c for c in catalog["models"] if c["id"]=="local-small")
        local["gateway"]="portkey"
        x=R.route(self.req(privacy="strict"),POLICY,catalog,ECON,GATEWAYS)
        item=next(c for c in x["candidates"] if c["model_id"]=="local-small")
        self.assertIn("STRICT_LOCAL_EXTERNAL_GATEWAY_FORBIDDEN",item["blockers"])

    def test_gateway_claiming_decision_authority_is_blocked(self):
        gateways=json.loads(json.dumps(GATEWAYS))
        gateways["gateways"]["litellm"]["decision_authority"]=True
        x=R.route(self.req(capabilities=["web-research"]),POLICY,self.catalog,ECON,gateways)
        items=[c for c in x["candidates"] if c["gateway"]=="litellm"]
        self.assertTrue(items)
        self.assertTrue(all("GATEWAY_DECISION_AUTHORITY_FORBIDDEN" in c["blockers"] for c in items))

if __name__=="__main__":
    unittest.main()
