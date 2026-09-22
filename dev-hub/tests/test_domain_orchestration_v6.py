import importlib.util,json,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

core=module(ROOT/"dev-hub/bin/functional-intent-orchestrator.py","core")
resolver=module(ROOT/"dev-hub/bin/domain-provider-resolver.py","resolver")

class DomainV6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=json.loads((ROOT/"dev-hub/config/domain-orchestration.v1.json").read_text())
        cls.econ=json.loads((ROOT/"dev-hub/config/provider-economics.v1.json").read_text())

    def test_simple_question_routes_one_domain(self):
        p=core.make_plan({"text":"Comment fonctionne le Collector ?","domains":["knowledge-research"]},self.cfg)
        self.assertEqual(p["mode"],"simple_question")
        self.assertEqual(p["primary_domains"],["knowledge-research"])
        self.assertFalse(p["implementation_allowed"])

    def test_multidomain_graphics_animation_backend(self):
        p=core.make_plan({"text":"Ajoute une animation avec de nouveaux graphismes et une API backend documentée"},self.cfg)
        self.assertIn("animation",p["primary_domains"])
        self.assertIn("graphics",p["primary_domains"])
        self.assertIn("development",p["primary_domains"])
        self.assertIn("documentation",p["primary_domains"])
        self.assertTrue(p["implementation_allowed"])

    def test_free_provider_beats_paid_without_approval(self):
        registry={
          "schema":"chacha.dev/capability-registry/v1",
          "capabilities":{"x":{"providers":[
            {"id":"free","status":"ADOPT","cost_class":"free"},
            {"id":"paid","status":"ADOPT","cost_class":"paid"}]}}
        }
        health={"schema":"chacha.dev/provider-health-snapshot/v1","providers":{
          "free":{"state":"HEALTHY","source":"t","checked_at":"now"},
          "paid":{"state":"HEALTHY","source":"t","checked_at":"now"}}}
        r=resolver.resolve("x","development",registry,health,self.econ,{},False)
        self.assertEqual(r["provider"],"free")
        paid=[x for x in r["candidates"] if x["provider"]=="paid"][0]
        self.assertFalse(paid["eligible"])

if __name__=="__main__":unittest.main()
