#!/usr/bin/env python3
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))
import release_runtime_immutability as rri

def expect(fn,needle):
    try:fn();raise AssertionError('expected '+needle)
    except ValueError as e:assert needle in str(e),(needle,e)

# Every governed Python unit executing code from platform/current carries the native guard.
units=rri.platform_python_units(ROOT)
assert units, 'no platform Python units found'
missing=[p.name for p in units if not rri.native_guard(p.read_text())]
assert not missing,missing
print('CHACHA_DEV_IMMUTABLE_RELEASE_NATIVE_SYSTEMD_GUARDS=PASS')

# Every direct production entrypoint importing sovereign/quota modules self-disables bytecode before local imports.
entrypoints=[]
for p in sorted(BIN.glob('*.py')):
    text=p.read_text()
    if 'import sovereign_state_authority' in text or 'import d1_quota_circuit' in text:
        entrypoints.append(p)
        guard=text.find('sys.dont_write_bytecode=True')
        local=min([i for i in (text.find('import sovereign_state_authority'),text.find('import d1_quota_circuit')) if i>=0])
        assert guard>=0 and guard<local,p.name
assert entrypoints
print('CHACHA_DEV_IMMUTABLE_RELEASE_DIRECT_ENTRYPOINT_GUARDS=PASS')

# Dynamic proof: a direct release-local Guardian client invocation must not create bytecode even without env guards.
with tempfile.TemporaryDirectory() as td:
    t=Path(td)
    for name in ('guardian-client.py','d1_quota_circuit.py','sovereign_state_authority.py'):
        (t/name).write_bytes((BIN/name).read_bytes())
    env={'PATH':'/usr/bin:/bin'}
    cp=subprocess.run(['/usr/bin/python3',str(t/'guardian-client.py'),'-h'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
    assert 'usage:' in cp.stdout.lower()
    assert not list(t.rglob('*.pyc')) and not list(t.rglob('__pycache__'))
    print('CHACHA_DEV_IMMUTABLE_RELEASE_DIRECT_CLIENT_NO_PYC=PASS')

with tempfile.TemporaryDirectory() as td:
    t=Path(td); rel=t/'release'; unitsdir=rel/'dev-hub/systemd'; unitsdir.mkdir(parents=True)
    u=unitsdir/'chacha-dev-test.service'
    u.write_text('[Service]\nExecStart=/usr/bin/python3 /opt/chacha-dev/platform/current/dev-hub/bin/test.py\n')
    expect(lambda:rri.ensure_python_release_guard(rel,t/'systemd',Path('/usr/bin/true')),'PYTHON_RELEASE_UNIT_BYTECODE_GUARD_MISSING')
    u.write_text('[Service]\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nExecStart=/usr/bin/python3 /opt/chacha-dev/platform/current/dev-hub/bin/test.py\n')
    out=rri.ensure_python_release_guard(rel,t/'systemd',Path('/usr/bin/true'))
    assert out['status']=='PASS' and out['protected_python_unit_count']==1 and out['daemon_reload'] is True,out
    drop=t/'systemd/chacha-dev-test.service.d'/rri.DROPIN_NAME
    assert drop.read_text()==rri.DROPIN
    print('CHACHA_DEV_IMMUTABLE_RELEASE_LIVE_DROPIN=PASS')

# Prove the enforced environment prevents local import cache creation.
with tempfile.TemporaryDirectory() as td:
    t=Path(td); (t/'mod.py').write_text('VALUE=7\n'); (t/'main.py').write_text('import mod\nprint(mod.VALUE)\n')
    env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
    cp=subprocess.run(['/usr/bin/python3',str(t/'main.py')],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
    assert cp.stdout.strip()=='7'
    assert not list(t.rglob('*.pyc')) and not list(t.rglob('__pycache__'))
    print('CHACHA_DEV_IMMUTABLE_RELEASE_NO_PYC_RUNTIME=PASS')

policy=json.load(open(ROOT/'dev-hub/config/platform-promotion-transaction.v1.json'))
assert policy['invariants']['python_runtime_must_not_write_bytecode_into_release'] is True
assert policy['invariants']['python_platform_current_units_require_bytecode_guard'] is True
assert policy['invariants']['direct_python_entrypoints_importing_sovereign_modules_must_disable_bytecode_before_import'] is True
ops=json.load(open(ROOT/'dev-hub/config/operator-directives.v1.json'))
d=next(x for x in ops['directives'] if x['directive_id']=='opdir-immutable-release-runtime')
assert d['status']=='ACTIVE' and d['scope']=='PLATFORM_GLOBAL' and d['backfill_required'] is True
sinks=json.load(open(ROOT/'dev-hub/config/operator-directive-sinks.v1.json'))['sinks'];assert all(s in sinks for s in d['required_sinks'])
print('CHACHA_DEV_IMMUTABLE_RELEASE_RUNTIME_INVARIANT=VERIFIED')
