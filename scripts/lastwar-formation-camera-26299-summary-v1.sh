#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JSON="$ROOT/frontend/lab/master-assets-v2/meta/formation-camera-26299-trace-v1.json"
[[ -s "$JSON" ]] || { echo "ERREUR: JSON camera 26299 absent" >&2; exit 1; }
python - "$JSON" <<'PY'
import json,sys
p=sys.argv[1]
d=json.load(open(p,encoding='utf-8'))
print('FORMATION_CAMERA_26299_SUMMARY_V1')
print('objects=',d.get('objectCount'),'cameras=',len(d.get('cameras',[])))
print('--- CAMERAS ---')
for i,c in enumerate(d.get('cameras',[]),1):
    h=c.get('host') or {}
    print(f"CAMERA {i}: pathID={c.get('pathID')} host={h.get('name','?')} hostPathID={h.get('pathID','?')}")
    comps=', '.join(f"{x.get('type')}:{x.get('script','-')}@{x.get('pathID')}" for x in h.get('components',[]))
    print('  components=',comps or 'NONE')
    tt=c.get('targetTexture') or []
    if not tt:
        print('  targetTexture=NO_FIELD_OR_NONE')
    for x in tt:
        print(f"  targetTexture field={x.get('field')} fileID={x.get('fileID')} pathID={x.get('pathID')} resolved={x.get('resolved')} type={x.get('type','?')} name={x.get('name','?')} external={x.get('externalPath','')}")
    fields=c.get('interestingFields') or []
    for x in fields:
        if any(k in str(x.get('field','')).lower() for k in ('enabled','depth','culling','clearflags','orthographic','fieldofview','nearclip','farclip','targetdisplay')):
            print(f"  {x.get('field')}={x.get('value')}")
    chain=' > '.join((x.get('name') or '?') for x in c.get('hierarchy',[]))
    print('  hierarchy=',chain or 'NONE')
print('--- INBOUND TO CAMERA/HOST ---')
rows=d.get('inbound',[])
if not rows: print('NONE')
for r in rows:
    hits=', '.join(f"{x.get('field')}->{x.get('pathID')}" for x in r.get('hits',[]))
    print(f"{r.get('type')} {r.get('name') or '—'} pathID={r.get('pathID')} :: {hits}")
PY
