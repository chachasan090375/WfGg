from pathlib import Path
p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
old='wfgg_bridge=v13'
new='wfgg_bridge=v14'
n=s.count(old)
if not n:
    if new in s:
        print('WFGG_TRAIN_V14 already applied')
        raise SystemExit(0)
    raise SystemExit('v13 cache marker not found')
s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
print(f'WFGG_TRAIN_V14=PATCHED count={n}')
