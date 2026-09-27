#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin';sys.path.insert(0,str(BIN))
def loadmod(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(mod);return mod
translator=loadmod('v828_translator',BIN/'functional-translator-agent.py')
router=loadmod('v828_router',BIN/'functional-intent-orchestrator.py')
cfg=json.loads((ROOT/'dev-hub/config/domain-orchestration.v1.json').read_text())
SELF_DEV="""OBJECTIF FONCTIONNEL
Reprends l'évolution autonome de ChaCha DEV à partir de la production actuellement ACTIVE après V8.2.7.
Audite les travaux déjà amorcés concernant la continuation fiable de l'exécution, le retour conversationnel en cas de dépendance externe et la résilience aux limites ou quotas D1.
Résultat attendu : faire progresser l'autonomie de bout en bout de ChaCha DEV."""
sem=translator.semantic_partition(SELF_DEV)
assert sem['domain_hints']['applied'] is True,sem
assert sem['domain_hints']['domains']==['development'],sem
assert sem['domain_hints']['operational_mentions_are_context_only'] is True
with tempfile.TemporaryDirectory(prefix='v828-translator-') as td:
    p=subprocess.run([sys.executable,str(BIN/'functional-translator-agent.py'),'--repo-root',str(ROOT),'--text',SELF_DEV,
      '--project','chacha-dev-platform','--source','test','--operator','test','--request-id','dor-v828','--output-dir',td],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,p.stderr
    interface=json.loads((Path(td)/'interface-intent.json').read_text())
    translation=json.loads((Path(td)/'translation.json').read_text())
    assert interface['domains']==['development'],interface
    assert translation['primary_domains']==['development'],translation
    assert 'data-backend' not in translation['primary_domains']
    assert 'platform-release' not in translation['primary_domains']
real='Corrige le code de ChaCha DEV puis déploie-le en production.'
real_sem=translator.semantic_partition(real)
assert real_sem['domain_hints']['applied'] is False,real_sem
real_plan=router._preplan({'text':real_sem['routing_text']},cfg)
assert 'development' in real_plan['primary_domains'],real_plan
assert 'platform-release' in real_plan['primary_domains'],real_plan
d1=router._preplan({'text':'Migre la base D1 avec une migration contrôlée.'},cfg)
assert d1['primary_domains']==['data-backend'],d1
pkg=next(x for x in d1['packages'] if x['domain']=='data-backend')
assert 'database-migrate' in pkg['capabilities'],pkg
d1_review=router._preplan({'text':'Analyse le modèle D1 et sa résilience.'},cfg)
pkg=next(x for x in d1_review['packages'] if x['domain']=='data-backend')
assert 'database-migrate' not in pkg['capabilities'],pkg
assert 'data-model-review' in pkg['capabilities'],pkg
prod=router._preplan({'text':'Analyse l’état de la production actuelle sans déploiement.'},cfg)
assert 'platform-release' not in prod['primary_domains'],prod
central=(BIN/'central-interface-controller.py').read_text()
assert '"domains":list(human_intent.get("domains") or [])' in central
assert '"domains":list(ci.get("domains") or [])' in central
print('CHACHA_DEV_V828_SELF_DEVELOPMENT_DOMAIN_HINT=PASS')
print('CHACHA_DEV_V828_COMPONENT_MENTION_NOT_OPERATION=PASS')
print('CHACHA_DEV_V828_REAL_DEPLOY_REMAINS_ROUTABLE=PASS')
print('CHACHA_DEV_V828_D1_MIGRATION_REQUIRES_MIGRATION_INTENT=PASS')
print('CHACHA_DEV_V828_SEMANTIC_HINT_CONTINUATION_PRESERVED=PASS')
print('CHACHA_DEV_V828_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
