#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import os,re

roots=[
    os.path.expanduser('~/storage/downloads'),
    os.path.expanduser('~/storage/shared/Download'),
    os.path.expanduser('~/storage/shared/Documents'),
    os.path.expanduser('~/storage/shared/PCAPdroid'),
    '/storage/emulated/0/Download',
    '/storage/emulated/0/Documents',
]
exts=('.pcap','.pcapng','.cap')
commands=[
    b'world.get.all.alliance.city.info',
    b'world.get.all.alliance.stronghold.info',
    b'world.get.city.stronghold.effect',
    b'world.get.alliance.city.effect',
    b'world.all.city.reward.info',
    b'world.get.march.infos',
    b'get.alliance.world.mark.info',
    b'meteorite.enter.world',
    b'lw.world',
    b'plane.feature.user.info',
    b'get.player.cross.server.list',
]

seen=set(); files=[]
for root in roots:
    if not os.path.isdir(root):
        continue
    for base,_,names in os.walk(root):
        for name in names:
            if not name.lower().endswith(exts):
                continue
            p=os.path.realpath(os.path.join(base,name))
            if p in seen:
                continue
            seen.add(p)
            try:
                st=os.stat(p)
            except OSError:
                continue
            files.append((st.st_mtime,st.st_size,p))

files=sorted(files, reverse=True)[:6]
if not files:
    print('PCAP_FOUND=0')
    raise SystemExit(0)

print('PCAP_FOUND=',len(files),sep='')

identifier=re.compile(rb'[A-Za-z_][A-Za-z0-9_.]{1,63}')
number=re.compile(rb'(?<![A-Za-z0-9])[0-9]{1,10}(?![A-Za-z0-9])')
interesting=re.compile(r'(server|world|area|block|coord|position|pos|left|right|top|bottom|view|level|\bx\b|\by\b|uid|city|zone|map|current|target|mark|stronghold)',re.I)

for _,size,p in files:
    try:
        data=open(p,'rb').read()
    except OSError:
        continue
    print('\n=== FILE ===')
    print('NAME=',os.path.basename(p),sep='')
    print('BYTES=',size,sep='')
    any_cmd=False
    for cmd in commands:
        positions=[]; start=0
        while True:
            pos=data.find(cmd,start)
            if pos<0: break
            positions.append(pos); start=pos+1
        if not positions:
            continue
        any_cmd=True
        print('\nCOMMAND=',cmd.decode(),sep='')
        print('OCCURRENCES=',len(positions),sep='')
        out=[]; out_seen=set()
        for pos in positions[:4]:
            a=max(0,pos-1800); b=min(len(data),pos+2600)
            chunk=data[a:b]
            for raw in identifier.findall(chunk):
                s=raw.decode('ascii','ignore')
                if interesting.search(s) and s not in out_seen:
                    out_seen.add(s); out.append(s)
            for raw in number.findall(chunk):
                s=raw.decode('ascii','ignore')
                if s not in out_seen:
                    out_seen.add(s); out.append(s)
        for s in out[:120]:
            print(' ',s)
    if not any_cmd:
        print('MAPLIKE_COMMANDS=NONE')
PY
