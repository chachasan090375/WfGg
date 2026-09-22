#!/usr/bin/env python3
from pathlib import Path
import struct,re,json

TARGETS={
 "UI/LWSeason1/UILWSeasonServerDetail/Controller/UILWSeasonServerDetailCtrl.luac",
 "UI/LWSeason1/UILWSeasonServerDetail/View/UILWSeasonServerDetailView.luac",
 "UI/LWSeason1/UILWSeasonServerDetail/Config.luac",
}

data=Path('/tmp/LWScripts.data').read_bytes()
if data[:4]!=b'LWLF':
    raise SystemExit('V625_LWLF_MAGIC_INVALID')
_,_,count=struct.unpack_from('<III',data,4)
pos=16

def r7(off):
    value=0; shift=0
    for _ in range(5):
        x=data[off]; off+=1
        value|=(x&0x7f)<<shift
        if not x&0x80:return value,off
        shift+=7
    raise ValueError

report=[]
for i in range(count):
    n,pos=r7(pos)
    name=data[pos:pos+n].decode('utf-8','replace'); pos+=n
    size=struct.unpack_from('<I',data,pos)[0]; pos+=4
    chunk=data[pos:pos+size]; pos+=size
    if name not in TARGETS: continue
    strings=[m.group(0).decode('ascii','replace') for m in re.finditer(rb'[ -~]{3,}',chunk)]
    report.append({'index':i,'name':name,'strings':strings})
    print('===== V625 SERVER DETAIL MODULE '+name+' =====')
    print('V625_SERVER_DETAIL_STRING_COUNT='+str(len(strings)))
    for idx,st in enumerate(strings):
        print(f'{idx:04d}: {st[:500]}')
Path('/tmp/v625-server-detail-strings.json').write_text(json.dumps(report,indent=2))
print('V625_SERVER_DETAIL_MODULES='+str(len(report)))
print('V625_LASTWAR_CONNECTION=NONE')
print('V625_LASTWAR_MUTATION=NO')
