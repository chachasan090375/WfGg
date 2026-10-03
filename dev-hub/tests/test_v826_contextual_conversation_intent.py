#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin';sys.path.insert(0,str(BIN))
def loadmod(name:str,path:Path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(mod);return mod
translator=loadmod('v826_translator',BIN/'functional-translator-agent.py')
intent_router=loadmod('v826_router',BIN/'functional-intent-orchestrator.py')
factory=loadmod('v826_factory',BIN/'domain-factory-runner.py')
cfg=json.loads((ROOT/'dev-hub/config/domain-orchestration.v1.json').read_text())
SELFTEST='''TEST FONCTIONNEL RÉEL CHACHA DEV — AUTO-VALIDATION DE BOUT EN BOUT
Je veux que tu traites cette demande directement comme une demande fonctionnelle utilisateur normale, en utilisant ChaCha DEV lui-même et son chemin de production actif.

OBJECTIF FONCTIONNEL
Crée un petit artefact de validation nommé :
chacha-dev-selftest.txt
Son contenu final doit être exactement :
CHACHA_DEV_SELFTEST_OK

IMPORTANT
Elle doit traverser réellement : traduction / compréhension → Guardian → Sentinel → Run Controller.
En cas d’échec, rollback automatique et aucune dépense externe automatique.
'''
sem=translator.semantic_partition(SELFTEST)
expected='''Crée un petit artefact de validation nommé :
chacha-dev-selftest.txt
Son contenu final doit être exactement :
CHACHA_DEV_SELFTEST_OK'''
assert sem['functional_core']==expected,sem
canonical='Crée un fichier chacha-dev-selftest.txt contenant uniquement "CHACHA_DEV_SELFTEST_OK".'
assert sem['routing_text']==canonical,sem
assert sem['normalization']['applied'] is True,sem
assert sem['normalization']['kind']=='EXACT_TEXT_ARTIFACT',sem
assert factory.workspace_file_spec(sem['routing_text'])=={'action':'write-text','path':'chacha-dev-selftest.txt','content':'CHACHA_DEV_SELFTEST_OK'}
plan=intent_router._preplan({'text':sem['routing_text']},cfg)
assert plan['primary_domains']==['workspace-artifact'],plan['primary_domains']
assert 'translation' not in plan['primary_domains'] and 'platform-release' not in plan['primary_domains']
real='Traduis ce fichier en anglais puis déploie-le en production.'
real_plan=intent_router._preplan({'text':translator.semantic_partition(real)['routing_text']},cfg)
assert 'translation' in real_plan['primary_domains'] and 'platform-release' in real_plan['primary_domains'],real_plan
meta='Crée un fichier preuve.txt contenant OK.\nPasse ensuite par Guardian, Sentinel et le Run Controller, avec rollback automatique en cas d’échec.'
meta_sem=translator.semantic_partition(meta);meta_plan=intent_router._preplan({'text':meta_sem['routing_text']},cfg)
assert meta_plan['primary_domains']==['workspace-artifact'],meta_plan
negative='Crée un fichier local sans traduction et sans déploiement production.'
negative_plan=intent_router._preplan({'text':translator.semantic_partition(negative)['routing_text']},cfg)
assert negative_plan['primary_domains']==['workspace-artifact'],negative_plan
with tempfile.TemporaryDirectory(prefix='v826-translator-') as td:
    p=subprocess.run([sys.executable,str(BIN/'functional-translator-agent.py'),'--repo-root',str(ROOT),'--text',SELFTEST,
      '--project','chacha-dev-platform','--source','test','--operator','test','--request-id','dor-v826','--output-dir',td],
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
    assert p.returncode==0,p.stderr
    interface=json.loads((Path(td)/'interface-intent.json').read_text())
    translation=json.loads((Path(td)/'translation.json').read_text())
    assert interface['user_text']==canonical,interface
    assert interface['raw_user_text']==SELFTEST.strip(),interface
    assert interface['semantic_intent']['routing_text']==canonical
    assert factory.workspace_file_spec(interface['user_text'])=={'action':'write-text','path':'chacha-dev-selftest.txt','content':'CHACHA_DEV_SELFTEST_OK'}
    assert translation['primary_domains']==['workspace-artifact'],translation
central_source=(BIN/'central-interface-controller-core.py').read_text()
assert '"text":str(human_intent.get("user_text") or "")' in central_source
print('CHACHA_DEV_V826_CONTEXTUAL_INTENT_PARTITION=PASS')
print('CHACHA_DEV_V826_META_PROCESS_NOT_BUSINESS_DOMAIN=PASS')
print('CHACHA_DEV_V826_REAL_TRANSLATION_AND_DEPLOY_STILL_ROUTE=PASS')
print('CHACHA_DEV_V826_RAW_TEXT_TRACEABILITY_PRESERVED=PASS')
print('CHACHA_DEV_V826_TRANSLATOR_WRITES_CLEAN_CENTRAL_PROMPT=PASS')
print('CHACHA_DEV_V826_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
