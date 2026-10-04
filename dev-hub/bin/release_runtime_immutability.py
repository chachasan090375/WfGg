#!/usr/bin/env python3
from __future__ import annotations
import hashlib,os,subprocess,tempfile
from pathlib import Path
from typing import Any

SCHEMA='chacha.dev/release-runtime-immutability/v1'
DROPIN_NAME='20-chacha-immutable-release.conf'
DROPIN='[Service]\nEnvironment=PYTHONDONTWRITEBYTECODE=1\n'

def digest_bytes(data:bytes)->str:return 'sha256:'+hashlib.sha256(data).hexdigest()

def platform_python_units(release_root:Path)->list[Path]:
    units=release_root.resolve()/'dev-hub/systemd'
    if not units.is_dir():return []
    out=[]
    for p in sorted(units.glob('*.service')):
        text=p.read_text(encoding='utf-8')
        if any(line.startswith('ExecStart=') and '/usr/bin/python3' in line and '/opt/chacha-dev/platform/current/' in line for line in text.splitlines()):out.append(p)
    return out

def native_guard(text:str)->bool:
    return 'Environment=PYTHONDONTWRITEBYTECODE=1' in text or any(line.startswith('ExecStart=') and '/usr/bin/python3 -B ' in line for line in text.splitlines())

def atomic_text(path:Path,text:str)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def ensure_python_release_guard(release_root:Path,unit_root:Path=Path('/etc/systemd/system'),systemctl:Path=Path('/usr/bin/systemctl'))->dict[str,Any]:
    release_root=release_root.resolve(); units=platform_python_units(release_root); installed=[]
    missing=[p.name for p in units if not native_guard(p.read_text(encoding='utf-8'))]
    if missing:raise ValueError('PYTHON_RELEASE_UNIT_BYTECODE_GUARD_MISSING:'+','.join(missing))
    for p in units:
        target=unit_root.resolve()/f'{p.name}.d'/DROPIN_NAME
        atomic_text(target,DROPIN)
        installed.append({'unit':p.name,'dropin':str(target),'digest':digest_bytes(DROPIN.encode())})
    if installed:
        cp=subprocess.run([str(systemctl),'daemon-reload'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=30)
        if cp.returncode!=0:raise ValueError('SYSTEMD_DAEMON_RELOAD_FAILED:'+(cp.stderr or '')[-300:])
    return {'schema':SCHEMA,'status':'PASS','release_root':str(release_root),'protected_python_unit_count':len(units),
      'native_guard_required':True,'dropins':installed,'daemon_reload':bool(installed),'automatic_external_spend_eur':0}
