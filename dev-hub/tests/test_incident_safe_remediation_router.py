import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'dev-hub/bin/incident-safe-remediation-router.py'
s=importlib.util.spec_from_file_location('m',BIN);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
POL=json.loads((ROOT/'dev-hub/config/incident-safe-remediation-router.v1.json').read_text())
def inc(code='PROGRESS_TERMINAL_STALE',sev='BLOCK',destructive=False,prod=False,spend=0):return {'code':code,'severity':sev,'destructive':destructive,'production_mutation':prod,'automatic_external_spend_eur':spend}
def test_safe_non_destructive_routes(): assert M.route(POL,inc())['status']=='AUTO_ELIGIBLE'
def test_critical_stays_human(): assert M.route(POL,inc(sev='CRITICAL'))['status']=='HUMAN_BOUNDARY'
def test_destructive_stays_human(): assert M.route(POL,inc(destructive=True))['status']=='HUMAN_BOUNDARY'
def test_unknown_stays_human(): assert M.route(POL,inc(code='UNKNOWN'))['status']=='HUMAN_BOUNDARY'
def test_router_never_executes(): assert M.route(POL,inc())['router_executes_remediation'] is False
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print(n+'=PASS')
