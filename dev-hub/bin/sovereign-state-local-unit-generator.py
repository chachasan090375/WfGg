#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def load(p):return json.loads(Path(p).read_text())
def unit(s):
 sid=s['id'];port=s['port']
 return f'''[Unit]\nDescription=ChaCha DEV Sovereign State local {sid}\nAfter=network.target\n\n[Service]\nType=simple\nUser=root\nGroup=root\nEnvironment=CHACHA_D1_LOCAL_BIND=127.0.0.1\nEnvironment=CHACHA_D1_LOCAL_PORT={port}\nEnvironment=CHACHA_D1_LOCAL_SERVICE=chacha-dev-{sid}-local\nEnvironment=CHACHA_D1_LOCAL_DB=/opt/chacha-dev/runtime/sovereign-state/current/state/{sid}.db\nEnvironment=CHACHA_D1_LOCAL_WORKER=/opt/chacha-dev/runtime/sovereign-state/current/workers/{sid}.js\nExecStart=/usr/bin/node /opt/chacha-dev/runtime/sovereign-state/current/bin/d1-worker-local-runtime.mjs\nRestart=on-failure\nRestartSec=2\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=true\nReadWritePaths=/opt/chacha-dev/runtime/sovereign-state\nRestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX\nMemoryMax=192M\nTasksMax=32\n\n[Install]\nWantedBy=multi-user.target\n'''
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--policy',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);a=ap.parse_args();p=load(a.policy);a.output_dir.mkdir(parents=True,exist_ok=True)
 for s in p['services']:(a.output_dir/(f"chacha-dev-sovereign-{s['id']}.service")).write_text(unit(s))
 print('CHACHA_DEV_SOVEREIGN_LOCAL_UNIT_GENERATOR=PASS');print('UNIT_COUNT='+str(len(p['services'])))
if __name__=='__main__':raise SystemExit(main())
