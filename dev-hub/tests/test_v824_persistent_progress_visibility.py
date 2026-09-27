from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
progress=json.loads((ROOT/'dev-hub/config/progress-reporting.v1.json').read_text())
assert progress['version']=='1.3.0'
display=progress['display']
for key in ('always_visible_when_scope_is_chacha_dev','global_platform_bar_required','active_work_bar_required','per_module_bars_required','include_in_session_view','include_in_job_view','must_survive_reconnect_and_session_resume'):
    assert display[key] is True,key
inv=progress['invariants']
assert inv['progress_bars_are_permanent_for_chacha_dev_work'] is True
assert inv['all_future_user_visible_long_running_components_inherit_progress_reporting'] is True
assert inv['progress_may_never_fabricate_completion'] is True
required={'direct-operator-service','central-orchestrator','domain-factory','domain-readiness','execution-scheduler','guardian','run-controller','independent-verification','release-lifecycle'}
ids={x['id'] for x in progress['modules']}
assert required <= ids,(required-ids)
op=json.loads((ROOT/'dev-hub/config/operator-directives.v1.json').read_text())
d=next(x for x in op['directives'] if x['directive_id']=='opdir-permanent-progress-visibility')
assert d['status']=='ACTIVE' and d['scope']=='PLATFORM_GLOBAL' and d['backfill_required'] is True
assert {'progress-reporting','direct-operator','all-foundries','universal-materialization-gate','release-qualification'} <= set(d['required_sinks'])
sinks=json.loads((ROOT/'dev-hub/config/operator-directive-sinks.v1.json').read_text())['sinks']
assert 'progress-reporting' in sinks
for rel in ('agent-foundry.v1.json','branch-foundry.v1.json','capability-foundry.v1.json','object-factory.v1.json'):
    x=json.loads((ROOT/'dev-hub/config'/rel).read_text());u=x['universal_materialization']
    assert u['progress_visibility_contract_required'] is True
    assert u['future_user_visible_long_running_components_inherit_progress_reporting'] is True
controller=(ROOT/'dev-hub/bin/progress_state_controller.py').read_text()
direct=(ROOT/'dev-hub/bin/direct-operator-service.py').read_text()
ui=(ROOT/'dev-hub/direct-operator-ui/index.html').read_text()
assert '"display":dict(self.policy.get("display") or {})' in controller
assert 'def progress_stage(next_action:Any)' in direct
assert 'job["progress"]=self.st.progress.snapshot()' in direct
assert '"progress":self.progress.snapshot()' in direct
assert '/api/v1/progress' in ui and 'setInterval(refreshProgress,2000)' in ui
print('CHACHA_DEV_V824_PERMANENT_PROGRESS_VISIBILITY=PASS')
print('CHACHA_DEV_V824_PROGRESS_GLOBAL_AND_MODULE_BARS=PASS')
print('CHACHA_DEV_V824_PROGRESS_FUTURE_COMPONENT_INHERITANCE=PASS')
print('CHACHA_DEV_V824_PROGRESS_CLIENT_SURFACES=PASS')
print('CHACHA_DEV_V824_PROGRESS_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
