#!/usr/bin/env python3
import importlib.util,json,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'dev-hub/bin'));spec=importlib.util.spec_from_file_location('dos',ROOT/'dev-hub/bin/direct-operator-service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=json.loads((ROOT/'dev-hub/config/direct-operator.v1.json').read_text());c=p['authentication']['roles']['CONSULTANT'];assert c['build'] is True and c['platform_scope'] is False and c['core_scope'] is False and c['agent_scope'] is False;assert c['production_approval_identity'] is False;assert c['core_questions_allowed'] is False and c['infrastructure_questions_allowed'] is False;assert p['authentication']['guest_default_role']=='CONSULTANT'
with tempfile.TemporaryDirectory() as td:
 f=Path(td)/'users.json';f.write_text(json.dumps({'authorized_logins':['owner@example.com','guest@example.com'],'roles':{'guest@example.com':'CONSULTANT'}}));p['authentication']['authorized_users_file']=str(f)
 assert m.authorization_record('owner@example.com',p)['role']=='OWNER';g=m.authorization_record('guest@example.com',p);assert g['role']=='CONSULTANT' and g['permissions']['build'] is True and g['permissions']['platform_scope'] is False
assert m.consultant_platform_question_forbidden('Comment fonctionne le noyau ChaCha DEV ?') is True
assert m.consultant_platform_question_forbidden('Donne-moi les services du VPS et les agents internes') is True
assert m.consultant_platform_question_forbidden('Aide-moi à développer mon application météo') is False
c2=json.loads((ROOT/'dev-hub/config/consultant-access.v1.json').read_text());assert c2['project_scope']['may_build'] is True and c2['platform_boundary']['platform_internal_q_and_a'] is False;assert c2['information_boundary']['technology_watch_context_visible'] is False and c2['information_boundary']['central_memory_context_visible'] is False
print('CHACHA_DEV_DIRECT_OPERATOR_CONSULTANT_ACCESS_TEST=PASS')
